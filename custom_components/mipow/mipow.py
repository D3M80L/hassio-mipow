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
    has_timer: bool


class MiPow:
    def __init__(self, device: BLEDevice) -> None:
        self._state: State = State()
        self._device: BLEDevice = device
        self._services: BleakGATTServiceCollection | None = None
        self._update_padlock: asyncio.Lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._expected_disconnect: bool = False
        self._loop = asyncio.get_running_loop()
        self._rgbw_characteristic: BleakGATTCharacteristic | None = None
        self._effect_characteristic: BleakGATTCharacteristic | None = None
        self._battery_characteristic: BleakGATTCharacteristic | None = None
        self._timer_characteristic: BleakGATTCharacteristic | None = None
        self._callbacks: list[Callable[[State], None]] = []
        self._device_info: MiPowDeviceInfo | None = None
        self._delay: int = 0x14
        self._repetitions: int = 0
        self._pause: int = 0
        self._effect: int = MIPOW_EFFECT_LIGHT_CODE
        self._timer: int = 0
        self._timer_set: bool | None = None
        self._reconnect: bool = False
        self._update_counter: int = 0

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
        _LOGGER.debug("Update locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            reconnected: bool = await self._ensure_connected()
            if reconnected:
                if self._state.power:
                    # We are reconnecting, so ensure if the timer was already set on the device
                    # when set, then we do not want to reset the timer
                    timer: int | None = None if self._timer_set else self._timer
                    await self._set_light(
                        red=self._state.red,
                        green=self._state.green,
                        blue=self._state.blue,
                        white=self._state.white,
                        delay=self._delay,
                        pause=self._pause,
                        effect=self._effect,
                        timer=timer,
                    )
                else:
                    await self._turn_off()

                return

            rgbw = await self._fetch_rgbw()

            is_on = rgbw[0] != 0 or rgbw[1] != 0 or rgbw[2] != 0 or rgbw[3] != 0

            # Tapping some candles causes they can toggle the state
            powerStateChanged: bool = is_on != self._state.power

            self._state = replace(
                self._state,
                power=is_on,
                red=rgbw[0],
                green=rgbw[1],
                blue=rgbw[2],
                white=rgbw[3],
            )

            if powerStateChanged:
                if not is_on:
                    await self._disable_timer()
                else:
                    await self._enable_timer()

            if self._battery_characteristic:
                if (
                    powerStateChanged
                    or reconnected
                    or is_on
                    or self._update_counter % 10 == 0
                ):
                    level = bytes(
                        await self._client.read_gatt_char(self._battery_characteristic)
                    )
                    _LOGGER.debug("Battery checked %s", level)
                    if level and level[0] != self._state.battery_level:
                        self._state = replace(self._state, battery_level=level[0])

            self._update_counter += 1
            self._fire_callbacks()

    async def turn_off(self):
        assert self._rgbw_characteristic
        _LOGGER.debug("Turn off locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            await self._turn_off()

    async def _turn_off(self):
        await self._send_rgbw_command(red=0, green=0, blue=0, white=0)
        self._state = replace(self._state, red=0, green=0, blue=0, white=0, power=False)
        await self._disable_timer()
        self._fire_callbacks()

    async def _ensure_connected(self) -> bool:
        if not self._reconnect and self._client and self._client.is_connected:
            self._reset_disconnect_timer()
            return False

        reconnected: bool = self._reconnect

        self._reconnect = False

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
        deviceInfo.has_timer = not self._timer_characteristic is None
        self._device_info = deviceInfo

        if self._timer_characteristic:
            result = await self._client.read_gatt_char(self._timer_characteristic)
            self._timer_set = result[0] != 4

        self._reset_disconnect_timer()
        return reconnected

    def _resolve_characteristics(self, services: BleakGATTServiceCollection) -> None:
        self._rgbw_characteristic = self._require_read_property(
            services.get_characteristic("0000fffc-0000-1000-8000-00805f9b34fb")
        )
        self._rgbw_characteristic = self._require_property(
            "write", self._rgbw_characteristic
        )
        self._effect_characteristic = self._require_read_property(
            services.get_characteristic("0000fffb-0000-1000-8000-00805f9b34fb")
        )
        self._effect_characteristic = self._require_property(
            "write", self._effect_characteristic
        )
        self._battery_characteristic = self._require_read_property(
            services.get_characteristic("00002a19-0000-1000-8000-00805f9b34fb")
        )
        self._timer_characteristic = self._require_read_property(
            services.get_characteristic("0000fffe-0000-1000-8000-00805f9b34fb")
        )
        self._timer_characteristic = self._require_property(
            "write", self._timer_characteristic
        )

    def _require_read_property(
        self, characteristic: BleakGATTCharacteristic | None
    ) -> BleakGATTCharacteristic | None:
        return self._require_property("read", characteristic)

    def _require_property(
        self, property: str, characteristic: BleakGATTCharacteristic | None
    ) -> BleakGATTCharacteristic | None:
        if characteristic:
            for characteristicProperty in characteristic.properties:
                if characteristicProperty.startswith(property):
                    return characteristic
        return None

    def _disconnected(self, client: BleakClientWithServiceCache) -> None:
        msg: str = "%s: Disconnected; RSSI: %s"
        arg = [self.name, self.rssi]
        if self._expected_disconnect:
            _LOGGER.debug(msg, *arg)
        else:
            _LOGGER.warn(msg, *arg)
            self._reconnect = True

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
        _LOGGER.debug("_execute_disconnect locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            client = self._client
            self._expected_disconnect = True
            self._client = None
            self._rgbw_characteristic = None
            self._effect_characteristic = None
            self._battery_characteristic = None
            self._timer_characteristic = None
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
        timer: int | None = None,
    ):
        assert self._rgbw_characteristic

        if timer is not None:
            assert self._timer_characteristic

        _LOGGER.debug("Set light locked %s", self._update_padlock.locked())
        async with self._update_padlock:
            await self._set_light(
                red=red,
                green=green,
                blue=blue,
                white=white,
                effect=effect,
                delay=delay,
                repetitions=repetitions,
                pause=pause,
                timer=timer,
            )

    async def _set_light(
        self,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        white: int | None = None,
        effect: int | None = None,
        delay: int | None = None,
        repetitions: int | None = None,
        pause: int | None = None,
        timer: int | None = None,
    ):
        if delay is not None:
            self._delay = delay

        if effect is not None:
            self._effect = effect

        if repetitions is not None:
            self._repetitions = repetitions

        if pause is not None:
            self._pause = pause

        timerSet: bool = timer is not None
        self._timer = timer if timer is not None else self._timer

        red = red if red is not None else self._state.red
        green = green if green is not None else self._state.green
        blue = blue if blue is not None else self._state.blue
        white = white if white is not None else self._state.white

        if red == 0 and green == 0 and blue == 0 and white == 0:
            await self._turn_off()
            return

        await self._send_rgbw_command(red, green, blue, white)

        turnedOn: bool = self._state.power == False
        self._state = replace(
            self._state, power=True, red=red, green=green, blue=blue, white=white
        )

        if turnedOn or timerSet:
            if self._timer == 0:
                await self._disable_timer()
            else:
                await self._enable_timer()

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
        characteristic = self._require_read_property(
            self._services.get_characteristic(characteristicGuid)
        )
        if characteristic:
            return bytes(await self._client.read_gatt_char(characteristic)).decode(
                "utf-8"
            )
        return None

    async def _disable_timer(self):
        if not self._timer_characteristic:
            return

        if self._timer_set == False:
            return

        packet = bytearray([0, 4, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0])
        _LOGGER.debug("Disabling timer %s", packet)
        await self._client.write_gatt_char(self._timer_characteristic, packet)
        self._timer_set = False

    async def _enable_timer(self):
        if not self._timer_characteristic:
            return

        timer: int = self._timer + 1
        packet = bytearray(
            [
                0,  # Timer ID
                2,  # Turn OFF
                1,  # Second
                1,  # Minute start
                0,  # Hour start
                0,  # ?
                timer % 60,  # Minute end
                timer // 60,  # Hour end
                0,  # W
                0,  # R
                0,  # G
                0,  # B
                0,  # ?
            ]
        )
        _LOGGER.debug("Enabling timer %s", packet)
        await self._client.write_gatt_char(self._timer_characteristic, packet)
        self._timer_set = True
