from homeassistant.components.number import NumberEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import TIME_MINUTES
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import RestoreNumber
import logging

from .component import (
    MIPOW_DOMAIN,
    ATTR_DELAY,
    ATTR_REPETITIONS,
    ATTR_PAUSE,
    ATTR_TIMER,
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
            MiPowDelayEntity(data.device),
            MiPowRepetitionsEntity(data.device),
            MiPowPauseEntity(data.device),
        ]
    )

    if data.device.device_info.has_timer:
        async_add_entities([MiPowTimeOffEntity(data.device)])


class MiPowNumber(RestoreNumber):
    def __init__(self, device: MiPow, key: str) -> None:
        self._device: MiPow = device
        self._attr_device_info = map_to_device_info(device)
        self._attr_name = key
        self._attr_unique_id = f"{device.address}_{key}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_number_data = await self.async_get_last_number_data()
        _LOGGER.debug(
            "Last value of %s = %s", self.__class__.__name__, last_number_data
        )
        if last_number_data and last_number_data.native_value is not None:
            await self.async_set_native_value(last_number_data.native_value)


class MiPowDelayEntity(MiPowNumber):
    def __init__(self, device: MiPow) -> None:
        super().__init__(device, ATTR_DELAY)
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

    @property
    def native_value(self) -> float | None:
        return self._device.delay

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(delay=int(value))


class MiPowRepetitionsEntity(MiPowNumber):
    def __init__(self, device: MiPow) -> None:
        super().__init__(device, ATTR_REPETITIONS)
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

    @property
    def native_value(self) -> float | None:
        return self._device.repetitions

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(repetitions=int(value))


class MiPowPauseEntity(MiPowNumber):
    def __init__(self, device: MiPow) -> None:
        super().__init__(device, ATTR_PAUSE)
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

    @property
    def native_value(self) -> float | None:
        return self._device.pause

    async def async_set_native_value(self, value: float) -> None:
        await self._device.set_light(pause=int(value))


class MiPowTimeOffEntity(MiPowNumber):
    def __init__(self, device: MiPow) -> None:
        super().__init__(device, ATTR_TIMER)
        self.entity_description = NumberEntityDescription(
            key=ATTR_TIMER,
            name="Time off",
            icon="mdi:timer",
            entity_category=EntityCategory.CONFIG,
            native_step=1,
            native_min_value=0,
            native_max_value=24 * 60 - 1,
            native_unit_of_measurement=TIME_MINUTES,
        )
        self._attr_native_value = 0

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        await self._device.set_light(timer=int(value))
