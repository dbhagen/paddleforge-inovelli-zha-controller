"""Paddleforge Inovelli ZHA Controller.

One integration, two entry shapes:
- a single "controller" entry drives the grouping/pairing system (config-button
  gestures), the groups sensor, the dashboard panel, and the services;
- each "timer" entry drives one switch's ventilation timer (paddle gestures).

A single component-level zha_event router dispatches every event to both the
grouping engine (config-button commands) and the per-IEEE timer engine (paddle
commands). The two gesture sets are disjoint, so both can run on one switch.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType

from . import frontend as frontend_panel
from . import services, websocket
from .const import (
    CONF_DEVICE_ID,
    CONF_ENABLE_DASHBOARD,
    CONF_ENABLE_HARDWARE,
    CONF_ENTRY_TYPE,
    DEFAULT_CONTROLLER_OPTIONS,
    DEFAULT_TIMER_OPTIONS,
    DOMAIN,
    ENTRY_TYPE_TIMER,
    ZHA_EVENT,
)
from .coordinator import FanTimerCoordinator, ScenePairingCoordinator
from .engine import ScenePairingEngine
from .runtime import get_engine, get_engine_by_ieee, ieee_for_device
from .timer_engine import FanTimerEngine

_LOGGER = logging.getLogger(__name__)

CONTROLLER_PLATFORMS = [Platform.SENSOR]
TIMER_PLATFORMS = [Platform.SWITCH, Platform.NUMBER, Platform.SENSOR]

_ROUTER_UNSUB = "_router_unsub"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services, websocket, and the one shared zha_event router."""
    services.async_register(hass)
    websocket.async_register(hass)

    store = hass.data.setdefault(DOMAIN, {})

    @callback
    def _on_zha_event(event: Event) -> None:
        data = event.data
        ieee = data.get("device_ieee")
        command = data.get("command")
        if not ieee or not command:
            return
        # Grouping (config-button gestures) — the single controller engine.
        group_engine = get_engine(hass)
        if (
            group_engine is not None
            and group_engine.options.get(CONF_ENABLE_HARDWARE, True)
            and command in group_engine.handled_commands
        ):
            hass.async_create_task(group_engine.handle_event(command, ieee))
        # Timer (paddle gestures) — the per-IEEE timer engine, if this switch has one.
        timer_engine = get_engine_by_ieee(hass, ieee)
        if timer_engine is not None and command in timer_engine.handled_commands:
            hass.async_create_task(timer_engine.handle_event(command))

    if _ROUTER_UNSUB not in store:
        store[_ROUTER_UNSUB] = hass.bus.async_listen(ZHA_EVENT, _on_zha_event)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry (grouping controller or per-device timer)."""
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TIMER:
        return await _async_setup_timer(hass, entry)
    return await _async_setup_controller(hass, entry)


async def _async_setup_controller(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    options = {**DEFAULT_CONTROLLER_OPTIONS, **entry.options}
    engine = ScenePairingEngine(hass=hass, options=options)
    coordinator = ScenePairingCoordinator(hass, engine)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_setup_signal()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "kind": entry.data.get(CONF_ENTRY_TYPE),
        "engine": engine,
        "coordinator": coordinator,
    }

    entry.async_on_unload(engine.async_shutdown)
    entry.async_on_unload(coordinator.async_teardown_signal)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, CONTROLLER_PLATFORMS)

    if options.get(CONF_ENABLE_DASHBOARD):
        await frontend_panel.async_register(hass)

    await engine.async_apply_group_visibility()
    return True


async def _async_setup_timer(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    device_id = entry.data[CONF_DEVICE_ID]
    ieee = ieee_for_device(hass, device_id)
    if ieee is None:
        raise ConfigEntryNotReady(f"ZHA device {device_id} not available yet")

    options = {**DEFAULT_TIMER_OPTIONS, **entry.options}
    engine = FanTimerEngine(hass=hass, ieee=ieee, options=options)
    coordinator = FanTimerCoordinator(hass, engine)
    engine.on_update = coordinator.async_push
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "kind": entry.data.get(CONF_ENTRY_TYPE),
        "engine": engine,
        "coordinator": coordinator,
        "ieee": ieee,
    }

    # Cancel the timer on a MANUAL load off (ignore attribute-only changes).
    load_entity = engine.load_entity_id()
    if load_entity:

        @callback
        def _on_load_change(event: Event) -> None:
            old = event.data.get("old_state")
            new = event.data.get("new_state")
            if old is None or new is None or old.state == new.state:
                return
            hass.async_create_task(engine.async_on_load_change(old.state, new.state))

        entry.async_on_unload(async_track_state_change_event(hass, [load_entity], _on_load_change))
    else:
        _LOGGER.warning("no load entity resolved for %s; manual-off cancel disabled", ieee)

    entry.async_on_unload(engine.async_shutdown)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, TIMER_PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (engine shutdown + listeners via async_on_unload)."""
    if entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TIMER:
        platforms = TIMER_PLATFORMS
    else:
        platforms = CONTROLLER_PLATFORMS
        frontend_panel.async_unregister(hass)
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change so the engine picks up new settings."""
    await hass.config_entries.async_reload(entry.entry_id)
