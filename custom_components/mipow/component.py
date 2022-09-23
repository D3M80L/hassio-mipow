from homeassistant.backports.enum import StrEnum
from homeassistant.components.light import EFFECT_COLORLOOP
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from .mipow import MiPow

MIPOW_DOMAIN = "mipow"
UPDATE_SECONDS = 30

class MiPowEffects(StrEnum):
    PULSE:str = "pulse"
    FLASH:str = "flash"
    CANDLE:str = "candle"
    LIGHT:str = "light"
    RAINBOW:str = "rainbow"
    COLORLOOP:str = EFFECT_COLORLOOP

def map_to_device_info(device: MiPow) -> DeviceInfo:
    return DeviceInfo(
        name = device.name,
        manufacturer = device.device_info.manufacturer,
        hw_version = device.device_info.hw_version,
        sw_version = device.device_info.sw_version,
        model=f"{device.device_info.model} {device.device_info.serial}",
        identifiers = {
            (MIPOW_DOMAIN, device.address)
        },
        connections={
            (dr.CONNECTION_BLUETOOTH, device.address)
        }
    )