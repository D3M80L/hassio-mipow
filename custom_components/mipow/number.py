from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.restore_state import RestoreEntity
import logging

from .component import (
    MIPOW_DOMAIN,
    ATTR_DELAY,
    ATTR_REPETITIONS,
    ATTR_PAUSE,
    map_to_device_info,
    MiPowData,
)
from .mipow import MiPow

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: MiPowData = hass.data[MIPOW_DOMAIN][entry.entry_id]

    async_add_entities(
        [
            MiPowDelayEntity(data.coordinator, data.device),
            MiPowRepetitionsEntity(data.coordinator, data.device),
            MiPowPauseEntity(data.coordinator, data.device),
        ]
    )


class MiPowDelayEntity(CoordinatorEntity, NumberEntity, RestoreEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, device: MiPow) -> None:
        super().__init__(coordinator)
        self.entity_description = NumberEntityDescription(
            key=ATTR_DELAY,
            name="Delay",
            icon="mdi:speedometer-slow",
            entity_category=EntityCategory.CONFIG,
            native_step=1,
            native_min_value=0,
            native_max_value=255,
        )
        self._attr_native_value = 0x14
        self._device: MiPow = device
        self._attr_device_info = map_to_device_info(device)
        self._attr_unique_id = f"{device.address}_delay"

    @property
    def native_value(self) -> float | None:
        return self._device.delay

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(delay=int(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        _LOGGER.debug("Number last state %s", last_state)
        if not last_state:
            return
        await self.async_set_native_value(int(last_state.state))

class MiPowRepetitionsEntity(CoordinatorEntity, NumberEntity, RestoreEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, device: MiPow) -> None:
        super().__init__(coordinator)
        self.entity_description = NumberEntityDescription(
            key=ATTR_REPETITIONS,
            name="Repetitions",
            icon="mdi:repeat",
            entity_category=EntityCategory.CONFIG,
            native_step=1,
            native_min_value=0,
            native_max_value=255,
        )
        self._attr_native_value = 0
        self._device: MiPow = device
        self._attr_device_info = map_to_device_info(device)
        self._attr_unique_id = f"{device.address}_repetitions"

    @property
    def native_value(self) -> float | None:
        return self._device.repetitions

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(repetitions=int(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        _LOGGER.debug("Repetitions last state %s", last_state)
        if not last_state:
            return

        await self.async_set_native_value(int(last_state.state))


class MiPowPauseEntity(CoordinatorEntity, NumberEntity, RestoreEntity):
    def __init__(self, coordinator: DataUpdateCoordinator, device: MiPow) -> None:
        super().__init__(coordinator)
        self.entity_description = NumberEntityDescription(
            key=ATTR_PAUSE,
            name="Pause",
            icon="mdi:motion-pause",
            entity_category=EntityCategory.CONFIG,
            native_step=1,
            native_min_value=0,
            native_max_value=255,
        )
        self._attr_native_value = 0
        self._device: MiPow = device
        self._attr_device_info = map_to_device_info(device)
        self._attr_unique_id = f"{device.address}_pause"

    @property
    def native_value(self) -> float | None:
        return self._device.pause

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(pause=int(value))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        _LOGGER.debug("Pause last state %s", last_state)
        if not last_state:
            return

        await self.async_set_native_value(int(last_state.state))
