"""Paddleforge Inovelli ZHA Controller — pair Inovelli Blue switches into ZHA groups by gesture."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType

from . import frontend as frontend_panel
from . import services, websocket
from .const import (
    CONF_ENABLE_DASHBOARD,
    CONF_ENABLE_HARDWARE,
    DEFAULT_OPTIONS,
    DOMAIN,
    ZHA_EVENT,
)
from .coordinator import ScenePairingCoordinator
from .engine import ScenePairingEngine

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services + websocket once for the component."""
    services.async_register(hass)
    websocket.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    options = {**DEFAULT_OPTIONS, **entry.options}
    engine = ScenePairingEngine(hass=hass, options=options)
    coordinator = ScenePairingCoordinator(hass, engine)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_setup_signal()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "engine": engine,
        "coordinator": coordinator,
    }

    @callback
    def _on_zha_event(event: Event) -> None:
        data = event.data
        ieee = data.get("device_ieee")
        command = data.get("command")
        if not ieee or command not in engine.handled_commands:
            return
        hass.async_create_task(engine.handle_event(command, ieee))

    # The physical scene-button pairing sequence can be turned off (dashboard-only).
    if options.get(CONF_ENABLE_HARDWARE, True):
        entry.async_on_unload(hass.bus.async_listen(ZHA_EVENT, _on_zha_event))

    entry.async_on_unload(engine.async_shutdown)
    entry.async_on_unload(coordinator.async_teardown_signal)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if options.get(CONF_ENABLE_DASHBOARD):
        await frontend_panel.async_register(hass)

    # Hide (or, if the option was turned off, re-show) the redundant ZHA group entities.
    await engine.async_apply_group_visibility()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (bus unsub + timer cancel run via async_on_unload)."""
    frontend_panel.async_unregister(hass)
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change so the engine picks up new settings."""
    await hass.config_entries.async_reload(entry.entry_id)
