"""Sensor platform for both entry kinds.

Controller entry -> a single groups sensor (state = count, attrs = groups).
Timer entry -> a time-remaining sensor for that switch's ventilation timer.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ENTRY_TYPE, DOMAIN, ENTRY_TYPE_TIMER
from .coordinator import ScenePairingCoordinator
from .entity import FanTimerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Add the sensor(s) appropriate to this entry's kind."""
    data = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TIMER:
        async_add_entities([FanTimerRemainingSensor(data["coordinator"], entry)])
    else:
        async_add_entities([ScenePairingGroupsSensor(data["coordinator"], entry)])


class ScenePairingGroupsSensor(CoordinatorEntity[ScenePairingCoordinator], SensorEntity):
    """Reports how many pairing groups exist and their full detail as attributes."""

    _attr_has_entity_name = False
    _attr_name = "Paddleforge Inovelli ZHA Controller Groups"
    _attr_icon = "mdi:led-strip-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: ScenePairingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_groups"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"groups": self.coordinator.data or []}


class FanTimerRemainingSensor(FanTimerEntity, SensorEntity):
    """Minutes remaining on the timer (0 when idle)."""

    _attr_name = "Time remaining"
    _attr_icon = "mdi:fan-clock"
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_time_remaining"

    @property
    def native_value(self) -> float:
        return self.data.get("remaining_minutes", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.data
        return {
            "mode": d.get("mode"),
            "target_minutes": d.get("target_minutes"),
            "fill_pct": d.get("fill_pct"),
            "flashing": d.get("flashing"),
            "finishes_at": d.get("finishes_at"),
        }
