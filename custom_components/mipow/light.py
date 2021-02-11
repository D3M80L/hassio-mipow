"""Platform for light integration."""
from .mipow import MipowDevice

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import async_generate_entity_id
# Import the device class from the component that you want to support
from homeassistant.components.light import (
	ATTR_BRIGHTNESS,
	ATTR_HS_COLOR,
	ATTR_EFFECT,
	ATTR_WHITE_VALUE,
	ATTR_FLASH,
	FLASH_SHORT,
	FLASH_LONG,
	PLATFORM_SCHEMA,
	SUPPORT_BRIGHTNESS,
	SUPPORT_COLOR,
	SUPPORT_EFFECT,
	SUPPORT_WHITE_VALUE,
	LightEntity)
from homeassistant.const import CONF_DEVICES, CONF_NAME, ATTR_BATTERY_LEVEL
import homeassistant.util.color as color_util

_LOGGER = logging.getLogger(__name__)

SUPPORT_MIPOW_LED = SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_EFFECT | SUPPORT_WHITE_VALUE

DEVICE_SCHEMA = vol.Schema({vol.Optional(CONF_NAME): cv.string})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
	{vol.Optional(CONF_DEVICES, default={}): {cv.string: DEVICE_SCHEMA}}
)

CandleEffectsMap = {
	"Flash" : 0,
	"Fade" : 1,
	"Jump RGB" : 2,
	"Fade RGB" : 3,
	"Candle" : 4,
	"None" : 255
}

def setup_platform(hass, config, add_entities, discovery_info=None):
	# Add devices
	lights = []
	for address, device_config in config[CONF_DEVICES].items():
		name = device_config[CONF_NAME];
		light = MipowCandle(MipowDevice(address), name)
		lights.append(light)

	add_entities(light for light in lights)

class MipowCandle(LightEntity):
	def __init__(self, light, name):
		self._light = light
		self._name = name
		self._state = False
		self._brightness = 128
		self._hs_color = (1, 0)
		self._white = 0
		self._effect = None
		self._unique_id = f"{self.__class__}.{light.mac}"
		self._is_connected = False
		self._battery_level = None
		self._failed_updates_count = 0

	@property
	def name(self):
		return self._name

	@property
	def brightness(self):
		return self._brightness

	@property
	def hs_color(self):
		return self._hs_color

	@property
	def supported_features(self):
		return SUPPORT_MIPOW_LED

	@property
	def is_on(self):
		return self._state

	@property
	def effect_list(self):
		return [x for x in CandleEffectsMap.keys()]

	@property
	def effect(self):
		return self._effect

	@property
	def white_value(self):
		return self._white

	@property
	def unique_id(self):
		return self._unique_id

	@property
	def device_state_attributes(self):
		return {
			(ATTR_BATTERY_LEVEL, self._battery_level)
		}

	def turn_on(self, **kwargs):
		brightness = self._brightness
		hsColor = self._hs_color
		white = self._white
		effect = self._effect
		effect_delay = 0x14

		if ATTR_BRIGHTNESS in kwargs:
			brightness = kwargs.get(ATTR_BRIGHTNESS, 255)

		if ATTR_HS_COLOR in kwargs:
			hsColor = kwargs.get(ATTR_HS_COLOR)

		if ATTR_WHITE_VALUE in kwargs:
			white = kwargs.get(ATTR_WHITE_VALUE)

		if ATTR_EFFECT in kwargs:
			effect = kwargs.get(ATTR_EFFECT)
			if (not effect in CandleEffectsMap):
				effect = None

		if ATTR_FLASH in kwargs:
			effect = 'Flash'
			flash = kwargs.get(ATTR_FLASH)
			if flash == FLASH_LONG:
				effect_delay = 0x30
			elif flash == FLASH_SHORT:
				effect_delay = 0x10

		rgbColor = color_util.color_hsv_to_RGB(
		  hsColor[0], hsColor[1], brightness / 255 * 100
		)

		effectId = None
		if (not effect is None):
			effectId = CandleEffectsMap[effect]
			if (effectId == 255):
				effectId = None

		self._connect()
		if (effectId is None):
			self._light.set_rgbw(rgbColor[0], rgbColor[1], rgbColor[2], white)
		else:
			self._light.set_effect(rgbColor[0], rgbColor[1], rgbColor[2], white, effectId, delay=effect_delay)
			
		self._hs_color = hsColor
		self._brightness = brightness
		self._white = white
		self._effect = effect
		self._state = True

	def turn_off(self, **kwargs):
		self._connect()
		self._light.set_rgbw(0, 0, 0, 0)
		self._state = False

	def _connect(self):
		if (not self._is_connected):
			self._light.connect()
			self._is_connected = True
			self._failed_updates_count = 0

	def update(self):
		if (self._failed_updates_count > 10):
			return

		try:
			self._connect()
			result = self._light.fetch_rgbw()
			self._state = result[0] != 0 or result[1] != 0 or result[2] != 0 or result[3] != 0
			if (self._state):
				self._white = result[0]
				hsv = color_util.color_RGB_to_hsv(result[1], result[2], result[3])
				self._hs_color = hsv[:2]
				self._brightness = (hsv[2] / 100) * 255

			self._battery_level = self._light.fetch_battery_level()		
		except:
			self._is_connected = False
			self._battery_level = None
			self._failed_updates_count += 1