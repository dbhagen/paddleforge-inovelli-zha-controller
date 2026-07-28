"""Shared base entity for the timer platforms."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import FanTimerCoordinator


class FanTimerEntity(CoordinatorEntity[FanTimerCoordinator]):
    """Base entity; nests under the physical ZHA switch via a shared connection."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FanTimerCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            connections={(dr.CONNECTION_ZIGBEE, coordinator.engine.ieee)},
        )

    @property
    def data(self) -> dict[str, Any]:
        return self.coordinator.data or {}
