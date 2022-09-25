from __future__ import annotations

from dataclasses import dataclass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.backports.enum import StrEnum
from homeassistant.components.light import EFFECT_COLORLOOP
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from .mipow import MiPow

MIPOW_DOMAIN = "mipow"
UPDATE_SECONDS = 30
ATTR_DELAY = "delay"
ATTR_REPETITIONS = "repetitions"
ATTR_PAUSE = "pause"

class MiPowEffects(StrEnum):
    PULSE: str = "pulse"
    FLASH: str = "flash"
    CANDLE: str = "candle"
    LIGHT: str = "light"
    RAINBOW: str = "rainbow"
    COLORLOOP: str = EFFECT_COLORLOOP

@dataclass
class MiPowData:
    title: str
    device: MiPow
    coordinator: DataUpdateCoordinator

def map_to_device_info(device: MiPow) -> DeviceInfo:
    model: str = device.device_info.model
    if device.device_info.serial is not None:
        model += " " + device.device_info.serial
    return DeviceInfo(
        name=device.name,
        manufacturer=device.device_info.manufacturer,
        hw_version=device.device_info.hw_version,
        sw_version=device.device_info.sw_version,
        model=model,
        identifiers={(MIPOW_DOMAIN, device.address)},
        connections={(dr.CONNECTION_BLUETOOTH, device.address)},
    )
