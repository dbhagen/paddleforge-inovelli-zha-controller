"""A single sensor exposing the pairing groups (state = count, attrs = groups)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ScenePairingCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the groups sensor from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
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
