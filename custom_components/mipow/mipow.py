#
# Python module dedicated to control Mipow Playbulb LED candles
# Created by: D3M80L
#
# Inspired by the following projects.
# - https://github.com/amahlaka/python-mipow
# - https://github.com/Phhere/Playbulb/blob/master/protocols/candle.md
# - https://github.com/Heckie75/Mipow-Playbulb-BTL201
# - https://github.com/hohler/hass-mipow-comet/blob/master/mipow_comet.py
# - https://wiki.elvis.science/index.php?title=Mipow_Playbulb:_Bluetooth_Connection_Sniffing
#
# This code is released under the terms of the MIT license. 
#

from bleak import BleakClient
import logging

_LOGGER = logging.getLogger(__name__)

class MipowDevice:

    def __init__(self, mac):
        self.mac = mac

        self._rgbwhandle = None
        self._effecthandle = None
        self._hardwarehandle = None
        self._modelhandle = None
        self._manufacturerhandle = None
        self._mac = mac
        self._device = None

    async def connect(self):
        if (self._device):
            await self._device.disconnect()
            self._device = None

        if (self._device is None):
            self._device = BleakClient(self._mac)
        
        await self._device.connect(timeout = 9)
        self._rgbwhandle = None
        self._effecthandle = None
        self._hardwarehandle = None
        self._modelhandle = None
        self._manufacturerhandle = None
        
        handles = await self._device.get_services()
        for service in handles:
            for char in service.characteristics:
                if "read" in char.properties:
                    if (char.uuid.startswith("0000fffb")):
                        self._effecthandle = char.uuid
                    elif (char.uuid.startswith("0000fffc")):
                        self._rgbwhandle = char.uuid
                    elif (char.uuid.startswith("00002a29")):
                        value = bytes(await self._device.read_gatt_char(char.uuid))
                        self._manufacturerhandle = value.decode("utf-8")
                    elif (char.uuid.startswith("00002a25")):
                        value = bytes(await self._device.read_gatt_char(char.uuid))
                        self._modelhandle = value.decode("utf-8")
                    elif (char.uuid.startswith("00002a26")):
                        value = bytes(await self._device.read_gatt_char(char.uuid))
                        self._hardwarehandle = value.decode("utf-8")

    async def fetch_rgbw(self):
        if (not self._rgbwhandle):
            return None

        return bytes(await self._device.read_gatt_char(self._rgbwhandle))

    """
    The effect not always represents current status.
    BTL300 migt send wrgb 0,0,0,0 for effect request when some values are set
    """
    async def fetch_effect(self):
        if (not self._effecthandle):
            return None

        return bytes(await self._device.read_gatt_char(self._effecthandle))

    def fetch_hardware(self):
        return self._hardwarehandle

    def fetch_model(self):
        return self._modelhandle

    def fetch_manufacturer(self):
        return self._manufacturerhandle

    async def set_effect(self, red, green, blue, white, effect, delay=0x14, repetitions=0):
        packet = bytearray([white, red, green, blue, effect, repetitions, delay, 0])

        await self._device.write_gatt_char(self._effecthandle, packet)

    async def set_rgbw(self, red, green, blue, white):
        packet = bytearray([white, red, green, blue])
        await self._device.write_gatt_char(self._rgbwhandle, packet)
