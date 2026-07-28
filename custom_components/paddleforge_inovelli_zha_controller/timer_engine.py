"""Per-switch ventilation-timer state machine for Inovelli Blue switches (ZHA).

The engine reacts (via __init__.py) to ``zha_event`` paddle/config gestures and drives
a countdown timer for one physical switch: it turns the switch's load (a fan) on, renders
the remaining time on the 7-segment LED bar, flashes near expiry, and turns the load off
at zero. Everything is serialized behind one ``asyncio.Lock``; timers are kept purely in
memory on the event loop's monotonic clock.

All Inovelli LED control goes through the ``zha.issue_zigbee_cluster_command`` service (no
ZHA-gateway internals needed — this integration never touches Zigbee groups). The load and
LED entities are resolved from the device registry by the switch's IEEE.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CMD_DOWN_HOLD,
    CONF_CMD_DOWN_RELEASE,
    CONF_CMD_START,
    CONF_CMD_UP_HOLD,
    CONF_CMD_UP_RELEASE,
    CONF_DOUBLE_TAP_MINUTES,
    CONF_FLASH_THRESHOLD_SECONDS,
    CONF_HOLD_RAMP_SECONDS,
    CONF_LED_COLOR_HUE,
    CONF_LED_REFRESH_INTERVAL,
    CONF_MAX_MINUTES,
    DEFAULT_CMD_DOWN_HOLD,
    DEFAULT_CMD_DOWN_RELEASE,
    DEFAULT_CMD_START,
    DEFAULT_CMD_UP_HOLD,
    DEFAULT_CMD_UP_RELEASE,
    DEFAULT_FLASH_THRESHOLD_SECONDS,
    DEFAULT_HOLD_RAMP_SECONDS,
    DEFAULT_LED_COLOR_HUE,
    DEFAULT_LED_REFRESH_INTERVAL,
    DEFAULT_MAX_MINUTES,
    GESTURE_DEBOUNCE_SECONDS,
    INOVELLI_MFG_CLUSTER,
    INOVELLI_MFG_ID,
    LED_DURATION_INDEFINITE,
    LED_EFFECT_CMD,
    LED_EFFECT_INDIVIDUAL_CMD,
    LED_FX_CLEAR,
    LED_FX_FAST_BLINK,
    LED_FX_SOLID,
    LED_SEGMENTS,
    LOAD_SUPPRESS_SECONDS,
    MODE_EXPIRING,
    MODE_IDLE,
    MODE_RUNNING,
    MODE_SETTING,
    RAMP_TICK_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_ACTIVE = (MODE_RUNNING, MODE_SETTING, MODE_EXPIRING)


@dataclass
class _State:
    mode: str = MODE_IDLE
    deadline: datetime | None = None  # wall-clock instant the fan turns off
    minutes: float = 0.0  # current target minutes
    ramp_dir: int = 0
    ramp_started: float = 0.0
    ramp_base: float = 0.0
    suppress_load_until: float = 0.0
    last_command: str = ""
    last_command_ts: float = 0.0


@dataclass
class FanTimerEngine:
    """Owns the ventilation-timer state machine for one Inovelli switch."""

    hass: HomeAssistant
    ieee: str
    options: dict[str, Any]
    on_update: Callable[[], None] | None = None  # coordinator push (set by setup)
    _state: _State = field(default_factory=_State, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _deadline_unsub: Callable[[], None] | None = field(default=None, init=False)
    _refresh_unsub: Callable[[], None] | None = field(default=None, init=False)
    _ramp_timer: asyncio.TimerHandle | None = field(default=None, init=False)
    _load_cache: tuple[str, str] | None = field(default=None, init=False)
    _indicator_entity: str | None = field(default=None, init=False)
    _indicator_original: float | None = field(default=None, init=False)
    _last_segments: list[tuple[int, int] | None] = field(default=None, init=False)
    _cmd_actions: dict[str, str] = field(default_factory=dict, init=False)
    handled_commands: frozenset[str] = field(default_factory=frozenset, init=False)

    def __post_init__(self) -> None:
        self.ieee = self.ieee.lower()
        self._last_segments = [None] * LED_SEGMENTS
        self._cmd_actions = self._build_cmd_map()
        self.handled_commands = frozenset(self._cmd_actions)

    def _build_cmd_map(self) -> dict[str, str]:
        """Map each configured zha_event command → a timer action."""
        opts = self.options
        mapping: dict[str, str] = {}
        for key, action, default in (
            (CONF_CMD_START, "start", DEFAULT_CMD_START),
            (CONF_CMD_UP_HOLD, "up_hold", DEFAULT_CMD_UP_HOLD),
            (CONF_CMD_UP_RELEASE, "release", DEFAULT_CMD_UP_RELEASE),
            (CONF_CMD_DOWN_HOLD, "down_hold", DEFAULT_CMD_DOWN_HOLD),
            (CONF_CMD_DOWN_RELEASE, "release", DEFAULT_CMD_DOWN_RELEASE),
        ):
            cmd = str(opts.get(key, default)).strip()
            if cmd:
                mapping.setdefault(cmd, action)
        return mapping

    # -- option helpers --------------------------------------------------------
    @property
    def _max(self) -> float:
        return float(self.options.get(CONF_MAX_MINUTES, DEFAULT_MAX_MINUTES)) or 1.0

    @property
    def max_minutes(self) -> float:
        return self._max

    @property
    def _double_tap_minutes(self) -> float:
        return float(self.options.get(CONF_DOUBLE_TAP_MINUTES, self._max))

    @property
    def _ramp_rate(self) -> float:
        """Minutes added per second of hold."""
        secs = float(self.options.get(CONF_HOLD_RAMP_SECONDS, DEFAULT_HOLD_RAMP_SECONDS)) or 6.0
        return self._max / secs

    @property
    def _led_refresh(self) -> float:
        return float(self.options.get(CONF_LED_REFRESH_INTERVAL, DEFAULT_LED_REFRESH_INTERVAL))

    @property
    def _led_hue(self) -> int:
        return int(self.options.get(CONF_LED_COLOR_HUE, DEFAULT_LED_COLOR_HUE))

    @property
    def _flash_threshold(self) -> float:
        return float(
            self.options.get(CONF_FLASH_THRESHOLD_SECONDS, DEFAULT_FLASH_THRESHOLD_SECONDS)
        )

    # -- clock/state helpers ---------------------------------------------------
    def _now(self) -> float:
        return self.hass.loop.time()

    def _remaining_seconds(self) -> float:
        if self._state.deadline is None:
            return 0.0
        return (self._state.deadline - dt_util.utcnow()).total_seconds()

    def _remaining_minutes(self) -> float:
        return max(0.0, self._remaining_seconds() / 60.0)

    def _fill_pct(self) -> int:
        minutes = (
            self._state.minutes if self._state.mode == MODE_SETTING else self._remaining_minutes()
        )
        return int(round(min(100.0, max(0.0, minutes / self._max * 100.0))))

    def _notify(self) -> None:
        if self.on_update is not None:
            self.on_update()

    def snapshot(self) -> dict[str, Any]:
        """State surface for the coordinator / entities."""
        remaining = max(0.0, self._remaining_seconds())
        active = self._state.mode in _ACTIVE
        return {
            "mode": self._state.mode,
            "is_on": active,
            "target_minutes": round(self._state.minutes, 1),
            "remaining_seconds": int(remaining),
            "remaining_minutes": round(remaining / 60.0, 1),
            "fill_pct": self._fill_pct(),
            "flashing": self._state.mode == MODE_EXPIRING,
            "finishes_at": (dt_util.utcnow() + timedelta(seconds=remaining)).isoformat()
            if active
            else None,
        }

    # -- lifecycle -------------------------------------------------------------
    async def async_shutdown(self) -> None:
        self._cancel_countdown()
        self._cancel_ramp()
        await self._restore_indicator()

    def _cancel_ramp(self) -> None:
        if self._ramp_timer is not None:
            self._ramp_timer.cancel()
            self._ramp_timer = None

    # -- event entry point -----------------------------------------------------
    async def handle_event(self, command: str) -> None:
        action = self._cmd_actions.get(command)
        if action is None:
            return
        async with self._lock:
            now = self._now()
            if command == self._state.last_command and (now - self._state.last_command_ts) < (
                GESTURE_DEBOUNCE_SECONDS
            ):
                return
            self._state.last_command = command
            self._state.last_command_ts = now
            try:
                if action == "start":
                    await self._start(self._double_tap_minutes)
                elif action == "up_hold":
                    await self._begin_ramp(1)
                elif action == "down_hold":
                    await self._begin_ramp(-1)
                elif action == "release":
                    await self._end_ramp()
            except Exception:  # noqa: BLE001 - never let a bad event kill the listener
                _LOGGER.exception("error handling %s on %s", command, self.ieee)
        self._notify()

    # -- state transitions (lock held by caller) -------------------------------
    async def _start(self, minutes: float) -> None:
        minutes = max(0.0, min(self._max, float(minutes)))
        self._cancel_ramp()
        if minutes <= 0:
            await self._cancel(turn_off=True)
            return
        self._state.mode = MODE_RUNNING
        self._state.minutes = minutes
        self._state.deadline = dt_util.utcnow() + timedelta(minutes=minutes)
        await self._load_on()
        await self._paint()
        self._arm_deadline()

    async def _begin_ramp(self, direction: int) -> None:
        base = self._remaining_minutes() if self._state.mode in _ACTIVE else 0.0
        self._cancel_countdown()
        self._state.mode = MODE_SETTING
        self._state.ramp_base = base
        self._state.ramp_started = self._now()
        self._state.ramp_dir = direction
        if direction > 0:
            await self._load_on()
        await self._ramp_step()
        self._schedule_ramp()

    async def _ramp_step(self) -> None:
        if self._state.mode != MODE_SETTING:
            return
        elapsed = self._now() - self._state.ramp_started
        minutes = self._state.ramp_base + self._state.ramp_dir * self._ramp_rate * elapsed
        self._state.minutes = max(0.0, min(self._max, minutes))
        await self._paint()

    async def _end_ramp(self) -> None:
        if self._state.mode != MODE_SETTING:
            return
        self._cancel_ramp()
        minutes = self._state.minutes
        if minutes <= 0:
            await self._cancel(turn_off=True)
            return
        self._state.mode = MODE_RUNNING
        self._state.deadline = dt_util.utcnow() + timedelta(minutes=minutes)
        await self._load_on()
        await self._paint()
        self._arm_deadline()

    async def _expire(self) -> None:
        self._cancel_countdown()
        await self._load_off()
        await self._clear_led()
        await self._restore_indicator()
        self._state = _State()

    async def _cancel(self, *, turn_off: bool) -> None:
        self._cancel_countdown()
        self._cancel_ramp()
        was_active = self._state.mode in _ACTIVE
        self._state = _State()
        if was_active:
            if turn_off:
                await self._load_off()
            await self._clear_led()
            await self._restore_indicator()

    # -- countdown (native HA scheduler) ---------------------------------------
    def _arm_deadline(self) -> None:
        """Fire once exactly at the deadline (async_track_point_in_time), plus a
        periodic LED-refresh interval — no hand-rolled tick loop."""
        self._cancel_countdown()
        if self._state.deadline is None:
            return
        self._deadline_unsub = async_track_point_in_time(
            self.hass, self._on_deadline, self._state.deadline
        )
        self._refresh_unsub = async_track_time_interval(
            self.hass, self._on_refresh, timedelta(seconds=self._led_refresh)
        )

    def _cancel_countdown(self) -> None:
        if self._deadline_unsub is not None:
            self._deadline_unsub()
            self._deadline_unsub = None
        if self._refresh_unsub is not None:
            self._refresh_unsub()
            self._refresh_unsub = None

    @callback
    def _on_deadline(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_deadline())

    async def _async_deadline(self) -> None:
        async with self._lock:
            if self._state.mode in (MODE_RUNNING, MODE_EXPIRING):
                await self._expire()
        self._notify()

    @callback
    def _on_refresh(self, _now: datetime) -> None:
        self.hass.async_create_task(self._async_refresh())

    async def _async_refresh(self) -> None:
        async with self._lock:
            if self._state.mode not in (MODE_RUNNING, MODE_EXPIRING):
                return
            if self._remaining_seconds() <= 0:
                await self._expire()
            else:
                self._state.mode = (
                    MODE_EXPIRING
                    if self._remaining_seconds() <= self._flash_threshold
                    else MODE_RUNNING
                )
                await self._paint()
        self._notify()

    def _schedule_ramp(self) -> None:
        self._cancel_ramp()
        self._ramp_timer = self.hass.loop.call_later(RAMP_TICK_INTERVAL, self._on_ramp_tick)

    def _on_ramp_tick(self) -> None:
        self.hass.async_create_task(self._async_ramp_tick())

    async def _async_ramp_tick(self) -> None:
        async with self._lock:
            if self._state.mode != MODE_SETTING:
                return
            await self._ramp_step()
            self._schedule_ramp()
        self._notify()

    # -- public API (services + entities) --------------------------------------
    async def async_start(self, minutes: float | None = None) -> None:
        async with self._lock:
            await self._start(self._double_tap_minutes if minutes is None else minutes)
        self._notify()

    async def async_cancel(self) -> None:
        async with self._lock:
            await self._cancel(turn_off=True)
        self._notify()

    async def async_set_minutes(self, minutes: float) -> None:
        async with self._lock:
            if minutes <= 0:
                await self._cancel(turn_off=True)
            else:
                await self._start(minutes)
        self._notify()

    async def async_on_load_change(self, old_state: str | None, new_state: str | None) -> None:
        """A manual on→off (not our own write) cancels the timer."""
        async with self._lock:
            if self._now() < self._state.suppress_load_until:
                return
            if new_state == "off" and self._state.mode in _ACTIVE:
                await self._cancel(turn_off=False)
        self._notify()

    # -- LED + relay -----------------------------------------------------------
    async def _paint(self) -> None:
        """Render the fill from the bottom: light N of 7 segments, clear the rest.

        `led_level` on the all-bar effect is brightness (not fill height), so a real
        fill needs per-segment effects (command 3, led_number 0 = bottom). Only the
        segments that changed since the last paint are re-issued (Zigbee-frugal).
        """
        await self._ensure_indicator_off()
        segments = max(0, min(LED_SEGMENTS, round(self._fill_pct() / 100.0 * LED_SEGMENTS)))
        effect = LED_FX_FAST_BLINK if self._state.mode == MODE_EXPIRING else LED_FX_SOLID
        for i in range(LED_SEGMENTS):
            target = (effect, self._led_hue) if i < segments else (LED_FX_CLEAR, 0)
            if self._last_segments[i] == target:
                continue
            fx, color = target
            await self._issue_led_effect(fx, color, 100 if fx != LED_FX_CLEAR else 0, led_number=i)
            self._last_segments[i] = target

    async def _clear_led(self) -> None:
        # One all-bar clear wipes every segment; reset the diff cache.
        await self._issue_led_effect(LED_FX_CLEAR, 0, 0, duration=0)
        self._last_segments = [None] * LED_SEGMENTS

    async def _issue_led_effect(
        self,
        effect: int,
        color: int,
        level: int,
        duration: int = LED_DURATION_INDEFINITE,
        led_number: int | None = None,
    ) -> None:
        params: dict[str, int] = {
            "led_effect": int(effect),
            "led_color": int(color),
            "led_level": int(level),
            "led_duration": int(duration),
        }
        command = LED_EFFECT_CMD
        if led_number is not None:
            params["led_number"] = int(led_number)
            command = LED_EFFECT_INDIVIDUAL_CMD
        try:
            await self.hass.services.async_call(
                "zha",
                "issue_zigbee_cluster_command",
                {
                    "ieee": self.ieee,
                    "endpoint_id": 1,
                    "cluster_id": INOVELLI_MFG_CLUSTER,
                    "cluster_type": "in",
                    "command": command,
                    "command_type": "server",
                    "manufacturer": INOVELLI_MFG_ID,
                    "params": params,
                },
                blocking=False,  # fire-and-forget: an LED write must never wedge the timer
            )
            _LOGGER.debug("LED %s effect=%s level=%s on %s", command, effect, level, self.ieee)
        except Exception as err:  # noqa: BLE001 - LED failures shouldn't break the timer
            _LOGGER.warning("LED effect failed on %s: %s", self.ieee, err)

    def load_entity_id(self) -> str | None:
        load = self._resolve_load()
        return load[0] if load is not None else None

    def _resolve_load(self) -> tuple[str, str] | None:
        """Find the switch's primary controllable entity (a real switch, else the dimmer light)."""
        if self._load_cache is not None:
            return self._load_cache
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        device = dev_reg.async_get_device(connections={(dr.CONNECTION_ZIGBEE, self.ieee)})
        if device is None:
            return None
        mains = [
            ent
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=False
            )
            if ent.entity_category is None and ent.entity_id.split(".")[0] in ("switch", "light")
        ]
        # Prefer a load switch (on/off model) over the dimmer light (test device).
        mains.sort(key=lambda e: 0 if e.entity_id.startswith("switch.") else 1)
        if not mains:
            return None
        chosen = (mains[0].entity_id, mains[0].entity_id.split(".")[0])
        self._load_cache = chosen
        return chosen

    async def _load_on(self) -> None:
        await self._call_load("turn_on")

    async def _load_off(self) -> None:
        await self._call_load("turn_off")

    async def _call_load(self, service: str) -> None:
        load = self._resolve_load()
        if load is None:
            _LOGGER.warning("no load entity found for %s; cannot %s", self.ieee, service)
            return
        entity_id, domain = load
        self._state.suppress_load_until = self._now() + LOAD_SUPPRESS_SECONDS
        # Fire-and-forget: a ZHA command that never completes must not wedge the timer.
        await self.hass.services.async_call(
            domain, service, {"entity_id": entity_id}, blocking=False
        )

    # -- load-level indicator (so the timer fill owns the bar) -----------------
    def _resolve_indicator(self) -> str | None:
        """The switch's `load_level_indicator_timeout` number entity, if any."""
        if self._indicator_entity is not None:
            return self._indicator_entity or None
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        device = dev_reg.async_get_device(connections={(dr.CONNECTION_ZIGBEE, self.ieee)})
        found = ""
        if device is not None:
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            ):
                if ent.entity_id.endswith("_load_level_indicator_timeout"):
                    found = ent.entity_id
                    break
        self._indicator_entity = found
        return found or None

    async def _ensure_indicator_off(self) -> None:
        """Turn the always-on load-level indicator off so per-segment fills aren't blended.

        Caches the original value (restored when the timer goes idle / on unload).
        """
        ent = self._resolve_indicator()
        if ent is None or self._indicator_original is not None:
            return
        state = self.hass.states.get(ent)
        try:
            self._indicator_original = float(state.state)
        except (AttributeError, ValueError, TypeError):
            self._indicator_original = 11.0  # house default = "always show level"
        if self._indicator_original != 0:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": ent, "value": 0}, blocking=False
            )

    async def _restore_indicator(self) -> None:
        ent = self._resolve_indicator()
        if ent is None or self._indicator_original is None:
            return
        original = self._indicator_original
        self._indicator_original = None
        if original != 0:
            await self.hass.services.async_call(
                "number", "set_value", {"entity_id": ent, "value": original}, blocking=False
            )
