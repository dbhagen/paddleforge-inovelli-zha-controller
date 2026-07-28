"""Ventilation-timer control switch (on = start, off = cancel)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import FanTimerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([FanTimerSwitch(coordinator, entry)])


class FanTimerSwitch(FanTimerEntity, SwitchEntity):
    """Turn on to start the timer at the double-tap minutes; turn off to cancel."""

    _attr_name = "Ventilation timer"
    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_ventilation_timer"

    @property
    def is_on(self) -> bool:
        return bool(self.data.get("is_on", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.engine.async_start()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.engine.async_cancel()
