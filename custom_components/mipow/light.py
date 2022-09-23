from homeassistant.config_entries import ConfigEntry
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGBW_COLOR,
    ATTR_EFFECT,
    ATTR_WHITE,
    ATTR_FLASH,
    FLASH_SHORT,
    FLASH_LONG,
    ATTR_COLOR_MODE,
    ColorMode,
    LightEntityFeature,
    LightEntity)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.helpers.restore_state import RestoreEntity
import homeassistant.util.color as color_util
import logging
from typing import Any
from .mipow import MiPow, MIPOW_EFFECT_LIGHT_CODE
from .mipowdata import MiPowData
from .component import MIPOW_DOMAIN, MiPowEffects, map_to_device_info

_LOGGER = logging.getLogger(__name__)

CandleEffectsMap = {
    MiPowEffects.FLASH: 0,
    MiPowEffects.PULSE: 1,
    MiPowEffects.RAINBOW: 2,
    MiPowEffects.COLORLOOP: 3,
    MiPowEffects.CANDLE: 4,
    MiPowEffects.LIGHT: MIPOW_EFFECT_LIGHT_CODE
}

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data: MiPowData = hass.data[MIPOW_DOMAIN][entry.entry_id]
    async_add_entities([MiPowLightEntity(data.coordinator, data.device, entry.title)])

class MiPowLightEntity(CoordinatorEntity, LightEntity, RestoreEntity):
    _attr_has_entity_name = True
    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: MiPow,
        name: str
    ) -> None:
        super().__init__(coordinator)
        self._device = device
        self._attr_unique_id = device.address
        self._attr_effect = MiPowEffects.LIGHT
        self._attr_device_info = map_to_device_info(device)
        self._attr_supported_color_modes = {ColorMode.RGBW, ColorMode.WHITE}
        self._attr_effect_list = [
            MiPowEffects.LIGHT, 
            MiPowEffects.CANDLE, 
            MiPowEffects.PULSE, 
            MiPowEffects.FLASH,
            MiPowEffects.COLORLOOP,
            MiPowEffects.RAINBOW]
        self._attr_supported_features = LightEntityFeature.EFFECT | LightEntityFeature.FLASH
        self._attr_color_mode = ColorMode.RGBW
        self._attr_rgbw_color = (128, 128, 128, 128)
        self._async_update_attrs()
    
    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.turn_off()

    async def async_turn_on(self, **kwargs):
        brigtnessWasSet:bool = ATTR_BRIGHTNESS in kwargs
        brightness:int = self._attr_brightness
        isWhite:bool = False
        rgbw_color = self._attr_rgbw_color
        effect:str = self.effect
        mode:str = self._attr_color_mode
        speed: int = 0x14

        _LOGGER.debug("async_turn_on %s", kwargs)

        if ATTR_EFFECT in kwargs:
            effect = kwargs.get(ATTR_EFFECT)
            if (not effect in CandleEffectsMap):
                effect = MiPowEffects.LIGHT

        if ATTR_FLASH in kwargs:
            effect = MiPowEffects.FLASH
            flash = kwargs.get(ATTR_FLASH)
            if flash == FLASH_LONG:
                speed = 0x30
            elif flash == FLASH_SHORT:
                speed = 0x10

        if ATTR_RGBW_COLOR in kwargs:
            rgbw_color = kwargs.get(ATTR_RGBW_COLOR)
            mode = ColorMode.RGBW

        if brigtnessWasSet:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)

        if ATTR_WHITE in kwargs:
            speed = 0x14
            brightness = kwargs.get(ATTR_WHITE)
            rgbw_color = (0,0,0, brightness)
            isWhite = False
            brigtnessWasSet = True
            mode = ColorMode.WHITE

        if (isWhite):
            if (not brigtnessWasSet):
                if (self._is_only_white(rgbw_color)):
                    brightness = rgbw_color[3]
                elif (rgbw_color[3] != self.rgbw_color[3]):
                    brightness = rgbw_color[3]
                else:
                    hsv = color_util.color_RGB_to_hsv(rgbw_color[0], rgbw_color[1], rgbw_color[2])
                    brightness = int(hsv[2]/100*255)

            rgbw_color = (brightness,brightness,brightness,brightness)
        elif (brigtnessWasSet):
            if (self._is_only_white(rgbw_color)):
                rgbw_color = (0, 0, 0, brightness)
            else:
                hsv = color_util.color_RGB_to_hsv(rgbw_color[0], rgbw_color[1], rgbw_color[2])
                rgb_color = color_util.color_hsv_to_RGB(hsv[0], hsv[1], int(brightness/255*100))
                rgbw_color = (rgb_color[0], rgb_color[1], rgb_color[2], rgbw_color[3])

        effectId:int = self._get_effect_id(effect)
        await self._device.set_light(rgbw_color[0], rgbw_color[1], rgbw_color[2], rgbw_color[3], effect=effectId, delay=speed)
        
        self._attr_color_mode = mode
        self._attr_effect = effect

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._device.register_callback(self._handle_coordinator_update)
        )
        await super().async_added_to_hass()

        last_state = await self.async_get_last_state()
        _LOGGER.debug("Last state for %s: %s", self._attr_unique_id, last_state)
        if (not last_state):
            await self.async_turn_on()
            return

        if (ATTR_RGBW_COLOR in last_state.attributes):
            self._attr_rgbw_color = last_state.attributes[ATTR_RGBW_COLOR]
            _LOGGER.debug("Restored ATTR_RGBW_COLOR %s", self._attr_rgbw_color)

        if (ATTR_EFFECT in last_state.attributes):
            self._attr_effect = last_state.attributes[ATTR_EFFECT]
            _LOGGER.debug("Restored ATTR_EFFECT %s", self._attr_effect)

        if (ATTR_BRIGHTNESS in last_state.attributes):
            self._attr_brightness = last_state.attributes[ATTR_BRIGHTNESS]
            _LOGGER.debug("Restored ATTR_BRIGHTNESS %s", self._attr_brightness)

        if (ATTR_COLOR_MODE in last_state.attributes):
            self._attr_color_mode = last_state.attributes[ATTR_COLOR_MODE]
            _LOGGER.debug("Restored ATTR_COLOR_MODE %s", self._attr_color_mode)
        
        if (last_state.state == STATE_ON):
            await self.async_turn_on()
        else:
            await self.async_turn_off()
    
    # @property
    # def capability_attributes(self):
    #     data = super().capability_attributes
    #     data[ATTR_RGBW_COLOR] = self.rgbw_color
    #     data[ATTR_BRIGHTNESS] = self.brightness
    #     data[ATTR_EFFECT] = self.effect
    #     data[ATTR_COLOR_MODE] = self.color_mode
    #     return data

    @callback
    def _handle_coordinator_update(self, *args: Any) -> None:
        self._async_update_attrs()
        self.async_write_ha_state()

    @callback
    def _async_update_attrs(self) -> None:
        device = self._device
        rgbw = device.rgbw
        _LOGGER.debug(f"Update {device.rgbw} ON:{device.is_on}")

        if (device.is_on):
            hsv = color_util.color_RGB_to_hsv(rgbw[0], rgbw[1], rgbw[2])
            self._attr_rgbw_color = rgbw
            self._attr_brightness = (hsv[2] / 100) * 255
            if (self._is_only_white(rgbw)):
                self._attr_brightness = rgbw[3]

        self._attr_is_on = device.is_on

    def _is_only_white(self, rgbw) -> bool:
        return rgbw[0] == 0 and rgbw[1] == 0 and rgbw[2] == 0

    def _get_effect_id(self, effectName) -> int:
        if (effectName is None):
            return MIPOW_EFFECT_LIGHT_CODE

        return CandleEffectsMap[effectName]
