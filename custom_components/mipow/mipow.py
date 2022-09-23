#
# Python module dedicated to control Mipow Playbulb LED candles
# Created by: D3M80L
#
# Inspired by the following projects.
# - https://github.com/Heckie75/Mipow-Playbulb-BTL201
# - https://github.com/amahlaka/python-mipow
# - https://github.com/Phhere/Playbulb/blob/master/protocols/candle.md
# - https://github.com/hohler/hass-mipow-comet/blob/master/mipow_comet.py
# - https://wiki.elvis.science/index.php?title=Mipow_Playbulb:_Bluetooth_Connection_Sniffing
#
# This code is released under the terms of the MIT license. 
#
from __future__ import annotations
import asyncio
from bleak.backends.device import BLEDevice
from bleak.backends.service import BleakGATTCharacteristic, BleakGATTServiceCollection
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
import logging

_LOGGER = logging.getLogger(__name__)

MIPOW_EFFECT_LIGHT_CODE:int = 255

@dataclass(frozen=True)
class State:
    power: bool = False
    rgbw: tuple[int, int, int, int] = (0, 0, 0, 0)
    battery_level: int | None = None

class MiPowDeviceInfo:
    manufacturer: str | None
    hw_version: str | None
    sw_version: str | None
    model: str | None
    serial: str | None
    battery_powered: bool

class MiPow:

    def __init__(
        self,
        device: BLEDevice
    ) -> None:
        self._state: State = State()
        self._device: BLEDevice = device
        self._services: BleakGATTServiceCollection | None = None
        self._connection_padlock: asyncio.Lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._expected_disconnect: bool = False
        self._loop = asyncio.get_running_loop()
        self._rgbw_characteristic: BleakGATTCharacteristic | None = None
        self._effect_characteristic: BleakGATTCharacteristic | None = None
        self._battery_characteristic: BleakGATTCharacteristic | None = None
        self._callbacks: list[Callable[[State], None]] = []
        self._device_info: MiPowDeviceInfo | None = None

    @property
    def address(self) -> str:
        return self._device.address

    @property
    def name(self) -> str:
        return self._device.name or self._device.address

    @property
    def rssi(self) -> str:
        return self._device.rssi

    @property
    def is_on(self) -> bool:
        return self._state.power

    @property
    def rgbw(self) -> tuple[int, int, int, int]:
        return self._state.rgbw

    @property
    def battery_level(self) -> int | None:
        return self._state.battery_level

    @property
    def device_info(self) -> MiPowDeviceInfo | None:
        return self._device_info

    async def stop(self):
        await self._execute_disconnect()

    async def update(self):
        await self._ensure_connected()
        rgbw = await self._fetch_rgbw()

        is_on = (rgbw[0] != 0 or rgbw[1] != 0 or rgbw[2] != 0 or rgbw[3] != 0)
        if (not is_on):
            rgbw = self._state.rgbw
        self._state = replace(self._state, 
            power=is_on,
            rgbw = rgbw
        )

        if (self._battery_characteristic):
            level = bytes(await self._client.read_gatt_char(self._battery_characteristic))
            if (level and level[0] != self._state.battery_level):
                self._state = replace(self._state, battery_level=level[0])

        self._fire_callbacks()

    async def turn_off(self):
        assert self._rgbw_characteristic
        await self._send_rgbw_command(
            red = 0,
            green = 0,
            blue = 0,
            white = 0
        )
        self._state = replace(self._state, power=False)
        self._fire_callbacks()

    async def _ensure_connected(self):
        if self._connection_padlock.locked():
            _LOGGER.debug('Already locked')
        
        if self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return

        async with self._connection_padlock:
            if self._client and self._client.is_connected:
                self._reset_disconnect_timer()
                return

            client = await establish_connection(
                BleakClientWithServiceCache,
                self._device,
                self.name,
                self._disconnected,
                cached_services=self._services,
                ble_device_callback=lambda: self._device,
            )

            self._resolve_characteristics(client.services)

            if (_LOGGER.isEnabledFor(logging.DEBUG)):
                for service in client.services:
                    _LOGGER.debug("Service: %s %s", service.uuid, service.description)
                    for characteristic in service.characteristics:
                        _LOGGER.debug(f" Characteristic: {characteristic.uuid} - {characteristic.description}")
                        for property in characteristic.properties:
                            _LOGGER.debug(f"  Property: {property}")
                            if (property == "read"):
                                value = bytes(await client.read_gatt_char(characteristic))
                                _LOGGER.debug(f"   Value: {value}")
                        for descriptor in characteristic.descriptors:
                            _LOGGER.debug(f"  Descriptor: {descriptor.uuid} - {descriptor.description}")

            self._services = client.services
            self._client = client
            deviceInfo = MiPowDeviceInfo()
            deviceInfo.manufacturer = await self._get_characteristic_str("00002a29-0000-1000-8000-00805f9b34fb")
            deviceInfo.hw_version = await self._get_characteristic_str("00002a27-0000-1000-8000-00805f9b34fb")
            deviceInfo.sw_version = await self._get_characteristic_str("00002a28-0000-1000-8000-00805f9b34fb")
            deviceInfo.model = await self._get_characteristic_str("00002a26-0000-1000-8000-00805f9b34fb")
            deviceInfo.serial = await self._get_characteristic_str("00002a25-0000-1000-8000-00805f9b34fb")
            deviceInfo.battery_powered = not self._battery_characteristic is None
            self._device_info = deviceInfo
            self._reset_disconnect_timer()

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        self._rgbw_characteristic = services.get_characteristic("0000fffc-0000-1000-8000-00805f9b34fb")
        self._effect_characteristic = services.get_characteristic("0000fffb-0000-1000-8000-00805f9b34fb")
        self._battery_characteristic = services.get_characteristic("00002a19-0000-1000-8000-00805f9b34fb")

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        _LOGGER.warning(
            "%s: Disconnected; RSSI: %s",
            self.name,
            self.rssi,
        )
    
    def _reset_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._expected_disconnect = False
        self._disconnect_timer = self._loop.call_later(
            120,
            self._disconnect
        )
    
    def _disconnect(self) -> None:
        self._disconnect_timer = None
        asyncio.create_task(self._execute_timed_disconnect())

    async def _execute_timed_disconnect(self) -> None:
        await self._execute_disconnect()

    async def _execute_disconnect(self) -> None:
        async with self._connection_padlock:
            client = self._client
            self._expected_disconnect = True
            self._client = None
            self._rgbw_characteristic = None
            self._effect_characteristic = None
            self._battery_characteristic = None
            self._device_info = None
            self._services = None
            if client and client.is_connected:
                await client.disconnect()

    async def set_light(self, red: int, green: int, blue: int, white: int, effect: int = MIPOW_EFFECT_LIGHT_CODE, delay=0x14, repetitions=0):
        assert self._rgbw_characteristic
        if (red == 0 and green == 0 and blue == 0 and white == 0):
            await self.turn_off()
            return

        await self._send_rgbw_command(red, green, blue, white)
        self._state = replace(self._state, 
            power=True,
            rgbw = [red, green, blue, white]
        )

        if (effect != MIPOW_EFFECT_LIGHT_CODE):
            assert self._effect_characteristic
            packet = bytearray([white, red, green, blue, effect, repetitions, delay, 0])

            await self._client.write_gatt_char(self._effect_characteristic, packet)

        self._fire_callbacks()

    async def _send_rgbw_command(self, red: int, green: int, blue: int, white: int):
        packet = bytearray([white, red, green, blue])
        await self._client.write_gatt_char(self._rgbw_characteristic, packet)

    async def _send_effect(self, red, green, blue, white, effect, delay=0x14, repetitions=0):
        packet = bytearray([white, red, green, blue, effect, repetitions, delay, 0])
        await self._client.write_gatt_char(self._effecthandle, packet)

    def register_callback(
        self, 
        callback: Callable[[State], None]
    ) -> Callable[[], None]:

        def unregister_callback() -> None:
            self._callbacks.remove(callback)

        self._callbacks.append(callback)
        return unregister_callback

    def _fire_callbacks(self) -> None:
        state = self._state
        for callback in self._callbacks:
            callback(state)

    async def _fetch_rgbw(self):
        result = bytes(await self._client.read_gatt_char(self._rgbw_characteristic))
        return [result[1], result[2], result[3], result[0]]

    async def _get_characteristic_str(self, characteristicGuid: str) -> str | None:
        services = self._services
        characteristic = services.get_characteristic(characteristicGuid)
        if (characteristic):
            return bytes(await self._client.read_gatt_char(characteristic)).decode('utf-8')
        return None
            