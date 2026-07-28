"""Shared runtime lookups.

Two entry shapes live under one domain: the single "controller" entry (grouping)
and N per-device "timer" entries. Each is stored at ``hass.data[DOMAIN][entry_id]``
as ``{"kind": ..., "engine": ..., "coordinator": ...}``; component-level keys such
as the zha_event router unsub are plain (non-dict) values and are skipped here.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, ENTRY_TYPE_CONTROLLER, ENTRY_TYPE_TIMER
from .engine import ScenePairingEngine
from .timer_engine import FanTimerEngine


def _iter(hass: HomeAssistant, kind: str):
    for value in hass.data.get(DOMAIN, {}).values():
        if isinstance(value, dict) and value.get("kind") == kind and "engine" in value:
            yield value["engine"]


def get_engine(hass: HomeAssistant) -> ScenePairingEngine | None:
    """Return the single grouping engine (controller entry), or None if unloaded."""
    return next(_iter(hass, ENTRY_TYPE_CONTROLLER), None)


def get_engine_by_ieee(hass: HomeAssistant, ieee: str) -> FanTimerEngine | None:
    """Return the timer engine whose switch matches this IEEE, or None."""
    ieee = str(ieee).lower()
    for engine in _iter(hass, ENTRY_TYPE_TIMER):
        if engine.ieee == ieee:
            return engine
    return None


def get_engine_for_device(hass: HomeAssistant, device_id: str) -> FanTimerEngine | None:
    """Return the timer engine for a ZHA device_id (via the device registry)."""
    ieee = ieee_for_device(hass, device_id)
    return get_engine_by_ieee(hass, ieee) if ieee else None


def ieee_for_device(hass: HomeAssistant, device_id: str) -> str | None:
    """Resolve a ZHA device_id to its IEEE address."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, ident in device.connections:
        if domain == dr.CONNECTION_ZIGBEE:
            return str(ident).lower()
    return None
