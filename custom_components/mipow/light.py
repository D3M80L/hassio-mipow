from .mipow import MipowDevice
from typing import Final

import logging
import random
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.restore_state import RestoreEntity

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGBW_COLOR,
    ATTR_EFFECT,
    ATTR_WHITE,
    ATTR_FLASH,
    ATTR_TRANSITION,
    FLASH_SHORT,
    FLASH_LONG,
    PLATFORM_SCHEMA,
    SUPPORT_EFFECT,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    COLOR_MODE_RGBW,
    COLOR_MODE_WHITE,
    EFFECT_COLORLOOP,
    EFFECT_RANDOM,
    EFFECT_WHITE,
    LightEntity)
from homeassistant.const import (
    CONF_DEVICES,
    CONF_NAME,
    ATTR_BATTERY_LEVEL,
    ATTR_MODEL,
    ATTR_MANUFACTURER,
    ATTR_SW_VERSION)

import homeassistant.util.color as color_util

_LOGGER = logging.getLogger(__name__)

SUPPORT_MIPOW_LED = SUPPORT_EFFECT | SUPPORT_FLASH | SUPPORT_TRANSITION
BATTERY_SCAN_INTERVAL:Final="battery_scan_every"

MIPOW_EFFECT_PULSE:Final = "pulse"
MIPOW_EFFECT_FLASH:Final = "flash"
MIPOW_EFFECT_CANDLE:Final = "candle"
MIPOW_EFFECT_LIGHT:Final = "light"
MIPOW_EFFECT_RAINBOW:Final = "rainbow"

MIPOW_EFFECT_LIGHT_CODE:Final = 255
MAX_FAILED_STATUS_UPDATES_IN_ROW:Final = 3

MIPOW_ATTR_IS_RANDOM:Final = "is_random"
MIPOW_ATTR_IS_WHITE:Final = "is_white"

DEVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(BATTERY_SCAN_INTERVAL, default=10): cv.positive_int
    })

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_DEVICES, default={}): 
        {
            cv.string: DEVICE_SCHEMA
        }
    }
)

CandleEffectsMap = {
    "Flash" : 0,
    MIPOW_EFFECT_FLASH: 0,
    "Fade" : 1,
    MIPOW_EFFECT_PULSE: 1,
    "Jump RGB" : 2,
    MIPOW_EFFECT_RAINBOW: 2,
    "Fade RGB" : 3,
    EFFECT_COLORLOOP: 3,
    "Candle" : 4,
    MIPOW_EFFECT_CANDLE: 4,
    "None" : 255,
    MIPOW_EFFECT_LIGHT: MIPOW_EFFECT_LIGHT_CODE
}

def setup_platform(hass, config, add_entities, discovery_info=None):
    # Add devices
    lights = []
    for address, device_config in config[CONF_DEVICES].items():
        name = device_config[CONF_NAME]
        battery_interval = device_config[BATTERY_SCAN_INTERVAL]
        light = MipowCandle(MipowDevice(address), name, battery_interval)
        lights.append(light)

    add_entities(light for light in lights)

class MipowCandle(LightEntity, RestoreEntity):
    def __init__(self, light, name:str, battery_scan_every:int):
        self._attr_brightness:int = 128
        self._attr_rgbw_color = (0, 0, 0, 128)
        self._attr_effect:str = MIPOW_EFFECT_LIGHT
        self._version:str = None
        self._model:str = None
        self._manufacturer:str = None
        self._is_random:bool = False
        self._is_white:bool = False
        self._first_status_checked:bool = False

        self._transition:int = 0x14
        self._light = light
        self._name:str = name
        self._state:bool = False
        self._unique_id:str = f"{self.__class__}.{light.mac}"
        self._is_connected:bool = False
        self._battery_level = None
        self._failed_updates_count:int = 0
        self._battery_level_update_count:int = 0
        self._battery_scan_every:int = battery_scan_every
        self._attr_supported_color_modes = [COLOR_MODE_WHITE, COLOR_MODE_RGBW]
        self._attr_effect_list = [
            MIPOW_EFFECT_LIGHT, 
            MIPOW_EFFECT_CANDLE, 
            MIPOW_EFFECT_PULSE, 
            MIPOW_EFFECT_FLASH,
            EFFECT_COLORLOOP,
            MIPOW_EFFECT_RAINBOW,
            EFFECT_RANDOM,
            EFFECT_WHITE]

    @property
    def brightness(self) -> int:
        return self._attr_brightness

    @property
    def rgbw_color(self):
        return self._attr_rgbw_color

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_features(self):
        return SUPPORT_MIPOW_LED

    @property
    def is_on(self) -> bool:
        return self._state

    @property
    def effect_list(self):
        return self._attr_effect_list

    @property
    def effect(self) -> str:
        return self._attr_effect

    @property
    def white_value(self) -> int:
        return self.rgbw_color[3]

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_state_attributes(self):
        return {
            (ATTR_BATTERY_LEVEL, self._battery_level),
            (ATTR_MODEL, self._model),
            (ATTR_SW_VERSION, self._version),
            (ATTR_MANUFACTURER, self._manufacturer),
            (MIPOW_ATTR_IS_RANDOM, self._is_random),
            (MIPOW_ATTR_IS_WHITE, self._is_white)
        }

    def turn_on(self, **kwargs):
        brigtnessWasSet:bool = ATTR_BRIGHTNESS in kwargs
        brightness:int = self.brightness
        isWhite:bool = self._is_white
        isRandom:bool = self._is_random
        rgbw_color = self.rgbw_color
        effectSet:bool = False

        effect:str = self.effect
        transition:int = self._transition

        if ATTR_EFFECT in kwargs:
            effect = kwargs.get(ATTR_EFFECT)
            effectSet = True
            if (effect == EFFECT_RANDOM):
                isRandom = not self._is_random
                isWhite = False
                effect = self.effect
            elif (effect == EFFECT_WHITE):
                isWhite = not self._is_white
                isRandom = False
                effect = self.effect
            else:
                if (not effect in CandleEffectsMap):
                    effect = MIPOW_EFFECT_LIGHT

        if ATTR_FLASH in kwargs:
            effect = MIPOW_EFFECT_FLASH
            flash = kwargs.get(ATTR_FLASH)
            if flash == FLASH_LONG:
                transition = 0x30
            elif flash == FLASH_SHORT:
                transition = 0x10

        if ATTR_TRANSITION in kwargs:
            transition = int(kwargs.get(ATTR_TRANSITION, 0x14))
            if (transition > 255):
                transition = 255

        if ATTR_RGBW_COLOR in kwargs:
            rgbw_color = kwargs.get(ATTR_RGBW_COLOR)

        if brigtnessWasSet:
            brightness = kwargs.get(ATTR_BRIGHTNESS, 255)

        if ATTR_WHITE in kwargs:
            brightness = kwargs.get(ATTR_WHITE)
            rgbw_color = (0,0,0, brightness)
            isWhite = False
            isRandom = False
            brigtnessWasSet = True

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

        if (self._is_rgbw_zero(rgbw_color)):
            self.turn_off()
            return

        effectId:int = self._get_effect_id(effect)

        self._retry_connect(lambda: self._set_light(rgbw_color, effectId, transition, set_effect=effectSet))

        self._state = True
        self._battery_level_update_count = 0
        self._attr_effect = effect
        self._transition = transition
        self._is_white = isWhite
        self._is_random = isRandom
        self._attr_effect = effect

        self._set_attributes(rgbw_color)

    def turn_off(self, **kwargs):
        self._retry_connect(lambda: self._light.set_rgbw(0, 0, 0, 0))
        self._state = False
        self._battery_level_update_count = 0

    def update(self):
        if (self._failed_updates_count > MAX_FAILED_STATUS_UPDATES_IN_ROW):
            return

        try:
            self._connect()

            result = self._light.fetch_rgbw()
            self._state = not self._is_rgbw_zero(result)

            if (self._state):
                if (self._is_random):
                    random_rgbw = self._set_random_colors(result[1], result[2], result[3], result[0], self.effect)
                    result = (random_rgbw[3], random_rgbw[0], random_rgbw[1], random_rgbw[2])

                self._set_attributes((result[1], result[2], result[3], result[0]))

            if (self._state or self._battery_level_update_count % self._battery_scan_every == 0):
                self._battery_level = self._light.fetch_battery_level()
                self._battery_level_update_count = 0

            self._battery_level_update_count += 1

            if (not self._first_status_checked):
                self._first_status_checked = True
                if (self._state):
                    self.turn_on() # set effects and colors
                else:
                    self.turn_off()
                
        except:
            self._mark_failed_connection()
            self._battery_level = None
            self._failed_updates_count += 1
            self._battery_level_update_count = 0

            if (self._failed_updates_count > MAX_FAILED_STATUS_UPDATES_IN_ROW):
                _LOGGER.warning('Skipping status update checks for %s. Check battery status and toggle the candle in home assistant.', self._name)

            raise

    @property
    def capability_attributes(self):
        data = super().capability_attributes
        data[ATTR_BRIGHTNESS] = self.brightness
        data[ATTR_EFFECT] = self.effect
        data[ATTR_RGBW_COLOR] = self.rgbw_color
        data[MIPOW_ATTR_IS_RANDOM] = self._is_random
        data[MIPOW_ATTR_IS_WHITE] = self._is_white
        data[ATTR_TRANSITION] = self._transition
        return data

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        
        last_state = await self.async_get_last_state()

        if not last_state:
            return

        if (ATTR_EFFECT in last_state.attributes):
            self._attr_effect = last_state.attributes[ATTR_EFFECT]

        if (ATTR_BRIGHTNESS in last_state.attributes):
            self._attr_brightness = last_state.attributes[ATTR_BRIGHTNESS]

        if (ATTR_RGBW_COLOR in last_state.attributes):
            self._attr_rgbw_color = last_state.attributes[ATTR_RGBW_COLOR]

        if (MIPOW_ATTR_IS_WHITE in last_state.attributes):
            self._is_white = last_state.attributes[MIPOW_ATTR_IS_WHITE]

        if (MIPOW_ATTR_IS_RANDOM in last_state.attributes):
            self._is_random = last_state.attributes[MIPOW_ATTR_IS_RANDOM]

        if (ATTR_TRANSITION in last_state.attributes):
            self._transition = last_state.attributes[ATTR_TRANSITION]

    def _connect(self):
        try:
            if (not self._is_connected):
                self._light.connect()
                self._is_connected = True
                self._failed_updates_count = 0
                if (self._version is None):
                    self._version = self._light.fetch_hardware()

                if (self._model is None):
                    self._model = self._light.fetch_model()

                if (self._manufacturer is None):
                    self._manufacturer = self._light.fetch_manufacturer()
        except:
            self._mark_failed_connection()
            raise

    def _mark_failed_connection(self):
        self._is_connected = False
        self._first_status_checked = False

    def _retry_connect(self, action):
        try:
            self._connect()
            action()
            return
        except:
            self._mark_failed_connection()

        try:
            self._connect()
            action()
        except:
            self._mark_failed_connection()
            raise

    def _is_rgbw_zero(self, rgbw) -> bool:
        return rgbw[0] == 0 and rgbw[1] == 0 and rgbw[2] == 0 and rgbw[3] == 0

    def _is_only_white(self, rgbw) -> bool:
        return rgbw[0] == 0 and rgbw[1] == 0 and rgbw[2] == 0

    def _set_attributes(self, rgbw):
        hsv = color_util.color_RGB_to_hsv(rgbw[0], rgbw[1], rgbw[2])
        self._attr_rgbw_color = rgbw
        self._attr_hs_color = hsv[:2]
        self._attr_brightness = (hsv[2] / 100) * 255
        if (self._is_only_white(rgbw)):
            self._attr_brightness = rgbw[3]

    def _get_effect_id(self, effectName) -> int:
        if (effectName is None):
            return MIPOW_EFFECT_LIGHT_CODE

        return CandleEffectsMap[effectName]

    def _set_light(self, rgbw_color, effectId:int, transition:int, set_effect:bool=False):
        self._light.set_rgbw(rgbw_color[0], rgbw_color[1], rgbw_color[2], rgbw_color[3])
        if (set_effect or effectId != MIPOW_EFFECT_LIGHT_CODE):
            self._light.set_effect(rgbw_color[0], rgbw_color[1], rgbw_color[2], rgbw_color[3], effectId, delay=transition)

    def _set_random_colors(self, r:int, g:int, b:int, w:int, effect:str):
        effectId:int = self._get_effect_id(effect)
        hsv = color_util.color_RGB_to_hsv(r, g, b)
        
        minSaturation:int = 75 
        if (effect == MIPOW_EFFECT_PULSE):
            minSaturation = 100 # Seems that PULSE effect only accepts full saturation

        hsv = (random.randint(0, 359), random.randint(minSaturation, 100), hsv[2])
        rgb = color_util.color_hsv_to_RGB(hsv[0], hsv[1], hsv[2])
        rgbw = (rgb[0], rgb[1], rgb[2], w)
        self._set_light(rgbw, effectId, self._transition)
        return rgbw