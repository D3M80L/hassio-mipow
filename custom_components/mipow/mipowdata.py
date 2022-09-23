"""The led ble integration models."""
from __future__ import annotations

from dataclasses import dataclass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .mipow import MiPow

@dataclass
class MiPowData:
    """Data for the led ble integration."""

    title: str
    device: MiPow
    coordinator: DataUpdateCoordinator