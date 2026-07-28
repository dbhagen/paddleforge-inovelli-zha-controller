"""Timer-minutes number: set/see the timer, 0 cancels."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import FanTimerEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([FanTimerMinutesNumber(coordinator, entry)])


class FanTimerMinutesNumber(FanTimerEntity, NumberEntity):
    """Remaining timer minutes; writing starts/adjusts the timer (0 cancels)."""

    _attr_name = "Timer minutes"
    _attr_icon = "mdi:timer-cog-outline"
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_timer_minutes"
        self._attr_native_max_value = float(coordinator.engine.max_minutes)

    @property
    def native_value(self) -> float:
        return round(self.data.get("remaining_minutes", 0))

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.engine.async_set_minutes(value)
