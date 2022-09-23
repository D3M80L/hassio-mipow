import logging
from bleak.backends.device import BLEDevice
from homeassistant.config_entries import ConfigFlow
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import AbortFlow, FlowResult
from homeassistant.const import CONF_ADDRESS
import voluptuous as vol
from .mipow import MiPow
from bleak.exc import BleakError
import asyncio
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)
BLEAK_EXCEPTIONS = (AttributeError, BleakError, asyncio.exceptions.TimeoutError)

class MiPowConfigFlow(ConfigFlow, domain="mipow"):

    def __init__(self) -> None:
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._discovered_devices[discovery_info.address] = discovery_info
        _LOGGER.info("Discovered MiPow device: %s", discovery_info)
        return await self.async_step_user()
    
    async def async_step_user(
        self, 
        user_input = None
    ) -> FlowResult:
        _LOGGER.debug("async_step_user user_input=%s", user_input)

        if (not self._discovered_devices):
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                
                if (discovery.address not in current_addresses):
                    self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="no_unconfigured_devices")

        errors: dict[str, str] = {}

        if (user_input is not None):
            address:str = user_input[CONF_ADDRESS]
            device:BLEDevice = self._discovered_devices[address].device
            await self.async_set_unique_id(device.address, raise_on_progress=False)
            self._abort_if_unique_id_configured()

            mipow = MiPow(device)
            try:
                await mipow.update()
            except BLEAK_EXCEPTIONS:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await mipow.stop()
                return self.async_create_entry(
                        title=f"MiPow {device.name}({device.address})",
                        data={
                            CONF_ADDRESS: device.address,
                        },
                    )
        
        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: f"{service_info.name} ({service_info.address})"
                        for service_info in self._discovered_devices.values()
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
