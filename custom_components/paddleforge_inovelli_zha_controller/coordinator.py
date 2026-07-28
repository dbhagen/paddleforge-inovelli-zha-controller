"""Coordinator that mirrors the engine's group snapshot to entities/dashboard."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, SIGNAL_GROUPS_UPDATED
from .engine import ScenePairingEngine

_LOGGER = logging.getLogger(__name__)


class ScenePairingCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Push coordinator: refreshes on the engine's dispatcher signal, no polling."""

    def __init__(self, hass: HomeAssistant, engine: ScenePairingEngine) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self.engine = engine

    async def _async_update_data(self) -> list[dict[str, Any]]:
        return self.engine.list_groups()

    @callback
    def async_setup_signal(self) -> None:
        """Subscribe to the engine signal; returns nothing (unsub via config entry)."""

        @callback
        def _updated() -> None:
            self.async_set_updated_data(self.engine.list_groups())

        self._unsub_signal = async_dispatcher_connect(self.hass, SIGNAL_GROUPS_UPDATED, _updated)

    @callback
    def async_teardown_signal(self) -> None:
        if (unsub := getattr(self, "_unsub_signal", None)) is not None:
            unsub()
            self._unsub_signal = None
