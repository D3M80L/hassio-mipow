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

MIPOW_EFFECT_LIGHT_CODE: int = 255


@dataclass(frozen=True)
class State:
    power: bool = False
    red: int = 0
    green: int = 0
    blue: int = 0
    white: int = 0
    battery_level: int | None = None


class MiPowDeviceInfo:
    manufacturer: str | None
    hw_version: str | None
    sw_version: str | None
    model: str | None
    serial: str | None
    battery_powered: bool


class MiPow:
    def __init__(self, device: BLEDevice) -> None:
        self._state: State = State()
        self._device: BLEDevice = device
        self._services: BleakGATTServiceCollection | None = None
        self._connection_padlock: asyncio.Lock = asyncio.Lock()
        self._update_padlock: asyncio.Lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._expected_disconnect: bool = False
        self._loop = asyncio.get_running_loop()
        self._rgbw_characteristic: BleakGATTCharacteristic | None = None
        self._effect_characteristic: BleakGATTCharacteristic | None = None
        self._battery_characteristic: BleakGATTCharacteristic | None = None
        self._callbacks: list[Callable[[State], None]] = []
        self._device_info: MiPowDeviceInfo | None = None
        self._delay: int = 0x14
        self._repetitions: int = 0
        self._pause: int = 0
        self._effect: int = MIPOW_EFFECT_LIGHT_CODE

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
        state: State = self._state
        return (state.red, state.green, state.blue, state.white)

    @property
    def battery_level(self) -> int | None:
        return self._state.battery_level

    @property
    def delay(self) -> int:
        return self._delay

    @property
    def repetitions(self) -> int:
        return self._repetitions

    @property
    def pause(self) -> int:
        return self._pause

    @property
    def device_info(self) -> MiPowDeviceInfo | None:
        return self._device_info

    async def stop(self):
        await self._execute_disconnect()

    async def update(self):
        await self._ensure_connected()
        _LOGGER.debug("Update locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            rgbw = await self._fetch_rgbw()

            is_on = rgbw[0] != 0 or rgbw[1] != 0 or rgbw[2] != 0 or rgbw[3] != 0

            self._state = replace(
                self._state,
                power=is_on,
                red=rgbw[0],
                green=rgbw[1],
                blue=rgbw[2],
                white=rgbw[3],
            )

            if self._battery_characteristic:
                level = bytes(
                    await self._client.read_gatt_char(self._battery_characteristic)
                )
                if level and level[0] != self._state.battery_level:
                    self._state = replace(self._state, battery_level=level[0])

            self._fire_callbacks()

    async def turn_off(self):
        assert self._rgbw_characteristic
        _LOGGER.debug("Turn off locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            await self._turn_off()

    async def _turn_off(self):
        await self._send_rgbw_command(red=0, green=0, blue=0, white=0)
        self._state = replace(self._state, red=0, green=0, blue=0, white=0, power=False)
        self._fire_callbacks()

    async def _ensure_connected(self):
        if self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return

        _LOGGER.debug("_ensure_connected locked %s", self._connection_padlock.locked())
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

            self._services = client.services
            self._client = client
            deviceInfo = MiPowDeviceInfo()
            deviceInfo.manufacturer = await self._get_characteristic_str(
                "00002a29-0000-1000-8000-00805f9b34fb"
            )
            deviceInfo.hw_version = await self._get_characteristic_str(
                "00002a27-0000-1000-8000-00805f9b34fb"
            )
            deviceInfo.sw_version = await self._get_characteristic_str(
                "00002a28-0000-1000-8000-00805f9b34fb"
            )
            deviceInfo.model = await self._get_characteristic_str(
                "00002a26-0000-1000-8000-00805f9b34fb"
            )
            deviceInfo.serial = await self._get_characteristic_str(
                "00002a25-0000-1000-8000-00805f9b34fb"
            )
            deviceInfo.battery_powered = not self._battery_characteristic is None
            self._device_info = deviceInfo
            self._reset_disconnect_timer()

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        self._rgbw_characteristic = services.get_characteristic(
            "0000fffc-0000-1000-8000-00805f9b34fb"
        )
        self._effect_characteristic = services.get_characteristic(
            "0000fffb-0000-1000-8000-00805f9b34fb"
        )
        self._battery_characteristic = services.get_characteristic(
            "00002a19-0000-1000-8000-00805f9b34fb"
        )

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        msg: str = "%s: Disconnected; RSSI: %s"
        arg = [self.name, self.rssi]
        if self._execute_disconnect:
            _LOGGER.debug(msg, *arg)
        else:
            _LOGGER.warn(msg, *arg)

    def _reset_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._expected_disconnect = False
        self._disconnect_timer = self._loop.call_later(120, self._disconnect)

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

    async def set_light(
        self,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        white: int | None = None,
        effect: int | None = None,
        delay: int | None = None,
        repetitions: int | None = None,
        pause: int | None = None,
    ):
        assert self._rgbw_characteristic
        _LOGGER.debug("Set light locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            if delay is not None:
                self._delay = delay

            if effect is not None:
                self._effect = effect

            if repetitions is not None:
                self._repetitions = repetitions

            if pause is not None:
                self._pause = pause

            red = red if red is not None else self._state.red
            green = green if green is not None else self._state.green
            blue = blue if blue is not None else self._state.blue
            white = white if white is not None else self._state.white

            if red == 0 and green == 0 and blue == 0 and white == 0:
                await self._turn_off()
                return

            await self._send_rgbw_command(red, green, blue, white)
            self._state = replace(
                self._state, power=True, red=red, green=green, blue=blue, white=white
            )

            if self._effect != MIPOW_EFFECT_LIGHT_CODE:
                assert self._effect_characteristic
                packet = bytearray(
                    [
                        white,
                        red,
                        green,
                        blue,
                        self._effect,
                        self._repetitions,
                        self._delay,
                        self._pause,
                    ]
                )

                await self._client.write_gatt_char(self._effect_characteristic, packet)

            self._fire_callbacks()

    async def _send_rgbw_command(self, red: int, green: int, blue: int, white: int):
        packet = bytearray([white, red, green, blue])
        await self._client.write_gatt_char(self._rgbw_characteristic, packet)

    def register_callback(
        self, callback: Callable[[State], None]
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
        return (result[1], result[2], result[3], result[0])

    async def _get_characteristic_str(self, characteristicGuid: str) -> str | None:
        characteristic = self._services.get_characteristic(characteristicGuid)
        if characteristic:
            return bytes(await self._client.read_gatt_char(characteristic)).decode(
                "utf-8"
            )
        return None
