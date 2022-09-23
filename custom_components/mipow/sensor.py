from __future__ import annotations

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .component import MIPOW_DOMAIN, map_to_device_info
from .mipowdata import MiPowData

import logging
from .mipow import MiPow

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    data: MiPowData = hass.data[MIPOW_DOMAIN][entry.entry_id]
    if (data.device.device_info.battery_powered):
        async_add_entities([MiPowBatterySensor(data.coordinator, data.device, entry.title)])


class MiPowBatterySensor(SensorEntity):

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: MiPow,
        name: str
    ) -> None:
        super().__init__()
        self._attr_device_info = map_to_device_info(device)
        self._device = device
        self._attr_unique_id = f"{device.address}_battery"
    
    @property
    def native_value(self) -> float | None:
        return self._device.battery_level