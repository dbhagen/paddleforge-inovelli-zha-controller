"""Shared runtime lookups (single-instance engine access for services/websocket)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .engine import ScenePairingEngine


def get_engine(hass: HomeAssistant) -> ScenePairingEngine | None:
    """Return the live engine for the (single) config entry, or None if unloaded."""
    for value in hass.data.get(DOMAIN, {}).values():
        if isinstance(value, dict) and "engine" in value:
            return value["engine"]
    return None
