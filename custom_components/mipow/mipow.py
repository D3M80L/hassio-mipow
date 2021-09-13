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

from bluepy import btle

class MipowDevice:

    def __init__(self, mac):
        self.mac = mac

        self._rgbwhandle = None
        self._effecthandle = None
        self._batteryhandle = None
        self._hardwarehandle = None
        self._modelhandle = None
        self._manufacturerhandle = None
        self._device = btle.Peripheral()

    def connect(self):
        self._device.disconnect()
        self._device.connect(self.mac)

        self._rgbwhandle = None
        self._effecthandle = None
        self._batteryhandle = None
        self._hardwarehandle = None
        self._modelhandle = None
        self._manufacturerhandle = None
        
        handles = self._device.getCharacteristics()
        for handle in handles:
            if handle.uuid == "fffb":
                self._effecthandle = handle
            elif handle.uuid == "fffc":
                self._rgbwhandle = handle
            elif handle.uuid == "2a19":
                self._batterlyhandle = handle
            elif handle.uuid == "2a26":
                self._hardwarehandle = handle
            elif handle.uuid == "2a25":
                self._modelhandle = handle
            elif handle.uuid == "2a29":
                self._manufacturerhandle = handle

    def fetch_battery_level(self):
        if (not self._batterlyhandle):
            return None

        return self._batterlyhandle.read()[0]

    def fetch_rgbw(self):
        if (not self._rgbwhandle):
            return None

        return self._rgbwhandle.read()

    """
    The effect not always represents current status.
    BTL300 migt send wrgb 0,0,0,0 for effect request when some values are set
    """
    def fetch_effect(self):
        if (not self._effecthandle):
            return None

        return self._effecthandle.read()

    def fetch_hardware(self):
        if (not self._hardwarehandle):
            return None

        return self._hardwarehandle.read().decode("utf-8")

    def fetch_model(self):
        if (not self._modelhandle):
            return None

        return self._modelhandle.read().decode("utf-8")

    def fetch_manufacturer(self):
        if (not self._manufacturerhandle):
            return None

        return self._manufacturerhandle.read().decode("utf-8")

    def send_packet(self, handle, data):
        return handle.write(bytes(data))

    def set_effect(self, red, green, blue, white, effect, delay=0x14, repetitions=0):
        packet = bytearray([white, red, green, blue, effect, repetitions, delay, 0])
        self.send_packet(self._effecthandle, packet)

    def set_rgbw(self, red, green, blue, white):
        packet = bytearray([white, red, green, blue])
        self.send_packet(self._rgbwhandle, packet)
