#
# Python module dedicated to control Mipow Playbulb LED candles
# Created by: D3M80L
#
# Inspired by the following projects.
# - https://github.com/amahlaka/python-mipow
# - https://github.com/Phhere/Playbulb/blob/master/protocols/candle.md
# - https://github.com/Heckie75/Mipow-Playbulb-BTL201
# - https://github.com/hohler/hass-mipow-comet/blob/master/mipow_comet.py
#
# This code is released under the terms of the MIT license. 
#

from bluepy import btle

class MipowDevice:

	def __init__(self, mac):
		self.mac = mac

		self._rgbwhandle = None
		self._effecthandle = None
		self._batteryhandle = None

	def connect(self):
		device = btle.Peripheral(self.mac, addrType=btle.ADDR_TYPE_PUBLIC)

		self._rgbwhandle = None
		self._effecthandle = None
		self._batteryhandle = None
		
		handles = device.getCharacteristics()
		for handle in handles:
			if handle.uuid == "fffb":
				self._effecthandle = handle
			if handle.uuid == "fffc":
				self._rgbwhandle = handle
			if handle.uuid == "2a19":
				self._batterlyhandle = handle

	def fetch_battery_level(self):
		if (not self._batterlyhandle):
			return None

		return self._batterlyhandle.read()[0]

	def fetch_rgbw(self):
		if (not self._rgbwhandle):
			return None

		return self._rgbwhandle.read()

	def fetch_effect(self):
		if (not self._effecthandle):
			return None

		return self._effecthandle.read()

	def send_packet(self, handle, data):
		return handle.write(bytes(data))

	def set_effect(self, red, green, blue, white, effect, delay=0x14, repetitions=0):
		packet = bytearray([white, red, green, blue, effect, repetitions, delay, 0])
		self.send_packet(self._effecthandle, packet)

	def set_rgbw(self, red, green, blue, white):
		packet = bytearray([white, red, green, blue])
		self.send_packet(self._rgbwhandle, packet)
