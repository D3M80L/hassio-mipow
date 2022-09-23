from __future__ import annotations
import asyncio
import async_timeout
from bleak.exc import BleakError
from datetime import timedelta
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback, Event, HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import logging

from .mipow import MiPow
from .component import MIPOW_DOMAIN, UPDATE_SECONDS
from .mipowdata import MiPowData

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant, 
        entry: ConfigEntry
    ) -> bool:
    address: str = entry.data[CONF_ADDRESS]
    _LOGGER.debug("async_setup_entry %s", address)
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)
    if not ble_device:
        raise ConfigEntryNotReady(f"Could not find MiPow device with address {address}")

    mipow = MiPow(ble_device)

    @callback
    def _async_update_mipow(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        _LOGGER.debug("_async_update_mipow %s", service_info)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_update_mipow,
            BluetoothCallbackMatcher({ADDRESS: address}),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    async def _async_update():
        try:
            await mipow.update()
        except (AttributeError, BleakError, asyncio.exceptions.TimeoutError) as ex:
            raise UpdateFailed(str(ex)) from ex

    startup_event = asyncio.Event()
    cancel_first_update = mipow.register_callback(lambda *_: startup_event.set())
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=mipow.name,
        update_method=_async_update,
        update_interval=timedelta(seconds=UPDATE_SECONDS),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady:
        _LOGGER.debug("Config entry not ready for %s", mipow.address)
        cancel_first_update()
        raise

    try:
        async with async_timeout.timeout(30):
            await startup_event.wait()
    except asyncio.TimeoutError as ex:
        raise ConfigEntryNotReady(
            f"Unable to communicate with the device {mipow.name} {mipow.address}"
        ) from ex
    finally:
        cancel_first_update()

    hass.data.setdefault(MIPOW_DOMAIN, {})[entry.entry_id] = MiPowData(
        entry.title, mipow, coordinator
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _async_stop(event: Event) -> None:
        await mipow.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data: MiPowData = hass.data[MIPOW_DOMAIN][entry.entry_id]
    if entry.title != data.title:
        await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(
        hass: HomeAssistant, 
        entry: ConfigEntry
    ) -> bool:
    if result := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data: MiPowData = hass.data[MIPOW_DOMAIN].pop(entry.entry_id)
        await data.device.stop()

    return result
