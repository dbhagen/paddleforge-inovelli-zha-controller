"""Scene-button group-pairing state machine for Inovelli Blue switches (ZHA).

The engine listens (via __init__.py) to ``zha_event`` button gestures and drives
Zigbee groups + LED bar colors entirely through Home Assistant / ZHA internals —
no external websocket, script, or long-lived token.

All ZHA-private access is isolated in the ``_Zha`` adapter so an upstream rename is
caught in one place. Everything is serialized behind a single asyncio.Lock and the
pairing window is kept purely in memory.
"""

from __future__ import annotations

import asyncio
import colorsys
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTION_ARM,
    ACTION_COLOR,
    ACTION_EXIT,
    ACTION_REMOVE,
    BINDING_ENDPOINT_FALLBACK,
    CLUSTER_LEVEL,
    CLUSTER_ONOFF,
    CONF_CMD_ARM,
    CONF_CMD_COLOR,
    CONF_CMD_EXIT,
    CONF_CMD_REMOVE,
    CONF_DEFAULT_FAN_HUE,
    CONF_DEFAULT_LIGHT_HUE,
    CONF_HIDE_GROUP_ENTITIES,
    CONF_PAIR_PREFIX,
    CONF_PALETTE,
    CONF_WINDOW_SECONDS,
    DEFAULT_CMD_ARM,
    DEFAULT_CMD_COLOR,
    DEFAULT_CMD_EXIT,
    DEFAULT_CMD_REMOVE,
    GROUP_MEMBER_ENDPOINT,
    INOVELLI_MFG_CLUSTER,
    INOVELLI_MFG_ID,
    LED_EFFECT_CMD,
    LED_FX_CLEAR,
    LED_FX_FAST_BLINK,
    LED_IDLE_HUE,
    LED_IDLE_HUE_FAN,
    LED_OFF_COLOR_SUFFIX,
    LED_ON_COLOR_SUFFIX,
    SIGNAL_GROUPS_UPDATED,
)

_LOGGER = logging.getLogger(__name__)


class ZhaUnavailable(RuntimeError):
    """Raised when the ZHA gateway is not (yet) available."""


class _Zha:
    """Thin adapter over ZHA-private internals (the only version-coupled surface)."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    def _gateway(self) -> Any:
        from homeassistant.components.zha.helpers import get_zha_gateway

        try:
            return get_zha_gateway(self._hass)
        except Exception as err:  # ZHA reloading / not set up
            raise ZhaUnavailable(str(err)) from err

    @staticmethod
    def _eui64(ieee: str) -> Any:
        from zigpy.types.named import EUI64

        return EUI64.convert(ieee)

    def _device(self, gw: Any, ieee: str) -> Any | None:
        eui = self._eui64(ieee)
        getter = getattr(gw, "get_device", None)
        if getter is not None:
            return getter(eui)
        return getattr(gw, "devices", {}).get(eui)

    # -- groups ----------------------------------------------------------------
    def list_groups(self) -> list[Any]:
        return list(self._gateway().groups.values())

    def get_group(self, group_id: int) -> Any | None:
        return self._gateway().groups.get(group_id)

    @staticmethod
    def group_member_ieees(group: Any) -> list[str]:
        out: list[str] = []
        for m in getattr(group, "members", []):
            if getattr(m, "endpoint_id", None) != GROUP_MEMBER_ENDPOINT:
                continue
            dev = getattr(m, "device", None)
            ieee = getattr(dev, "ieee", None)
            if ieee is not None:
                out.append(str(ieee).lower())
        return out

    async def create_group(self, name: str, ieee: str) -> Any:
        from zha.zigbee.group import GroupMemberReference

        gw = self._gateway()
        member = GroupMemberReference(ieee=self._eui64(ieee), endpoint_id=GROUP_MEMBER_ENDPOINT)
        return await gw.async_create_zigpy_group(name, [member], None)

    async def add_member(self, group_id: int, ieee: str) -> None:
        from zha.zigbee.group import GroupMemberReference

        group = self.get_group(group_id)
        if group is None:
            return
        await group.async_add_members(
            [GroupMemberReference(ieee=self._eui64(ieee), endpoint_id=GROUP_MEMBER_ENDPOINT)]
        )

    async def remove_member(self, group_id: int, ieee: str) -> None:
        from zha.zigbee.group import GroupMemberReference

        group = self.get_group(group_id)
        if group is None:
            return
        await group.async_remove_members(
            [GroupMemberReference(ieee=self._eui64(ieee), endpoint_id=GROUP_MEMBER_ENDPOINT)]
        )

    async def remove_group(self, group_id: int) -> None:
        gw = self._gateway()
        remover = getattr(gw, "async_remove_zigpy_group", None) or getattr(
            gw, "async_remove_group", None
        )
        if remover is not None:
            await remover(group_id)

    # -- binding ---------------------------------------------------------------
    async def _binding_endpoint(self, device: Any) -> int:
        try:
            clusters = device.async_get_clusters()
            if asyncio.iscoroutine(clusters):
                clusters = await clusters
            eps = [
                ep
                for ep, by_type in clusters.items()
                if CLUSTER_ONOFF in (by_type.get("out") or {})
            ]
            if eps:
                return min(eps)
        except Exception as err:  # noqa: BLE001 - defensive around private API
            _LOGGER.debug("cluster discovery failed, using fallback endpoint: %s", err)
        return BINDING_ENDPOINT_FALLBACK

    def _bindings(self, ep: int) -> list[Any]:
        from zha.zigbee.device import ClusterBinding

        return [
            ClusterBinding(name="on_off", type="out", id=CLUSTER_ONOFF, endpoint_id=ep),
            ClusterBinding(name="level", type="out", id=CLUSTER_LEVEL, endpoint_id=ep),
        ]

    async def bind(self, ieee: str, group_id: int, *, unbind: bool = False) -> None:
        gw = self._gateway()
        device = self._device(gw, ieee)
        if device is None:
            return
        ep = await self._binding_endpoint(device)
        bindings = self._bindings(ep)
        if unbind:
            await device.async_unbind_from_group(group_id, bindings)
        else:
            await device.async_bind_to_group(group_id, bindings)


@dataclass
class _State:
    anchor: str | None = None
    group_id: int | None = None
    ts: float = 0.0
    color: int = 0
    cidx: int = 0


@dataclass
class ScenePairingEngine:
    """Owns the pairing state machine for one config entry."""

    hass: HomeAssistant
    options: dict[str, Any]
    _zha: _Zha = field(init=False)
    _state: _State = field(default_factory=_State, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _timer: asyncio.TimerHandle | None = field(default=None, init=False)
    _color_cache: dict[str, tuple[str | None, str | None]] = field(default_factory=dict, init=False)
    _type_cache: dict[str, str] = field(default_factory=dict, init=False)
    _cmd_actions: dict[str, str] = field(default_factory=dict, init=False)
    handled_commands: frozenset[str] = field(default_factory=frozenset, init=False)

    def __post_init__(self) -> None:
        self._zha = _Zha(self.hass)
        self._cmd_actions = self._build_cmd_map()
        self.handled_commands = frozenset(self._cmd_actions)

    def _build_cmd_map(self) -> dict[str, str]:
        """Build {zha_event command -> action} from options (comma-separated commands)."""
        opts = self.options
        mapping: dict[str, str] = {}
        for cmds, action in (
            (opts.get(CONF_CMD_ARM, DEFAULT_CMD_ARM), ACTION_ARM),
            (opts.get(CONF_CMD_COLOR, DEFAULT_CMD_COLOR), ACTION_COLOR),
            (opts.get(CONF_CMD_REMOVE, DEFAULT_CMD_REMOVE), ACTION_REMOVE),
            (opts.get(CONF_CMD_EXIT, DEFAULT_CMD_EXIT), ACTION_EXIT),
        ):
            for cmd in self._as_commands(cmds):
                mapping.setdefault(cmd, action)
        return mapping

    @staticmethod
    def _as_commands(value: Any) -> list[str]:
        """Normalize a gesture option (list from a multi-select, or comma string)."""
        items = (
            value if isinstance(value, (list, tuple)) else str(value).replace(";", ",").split(",")
        )
        return [str(c).strip() for c in items if str(c).strip()]

    # -- config helpers --------------------------------------------------------
    @property
    def _window(self) -> int:
        return int(self.options.get(CONF_WINDOW_SECONDS, 20))

    @property
    def _palette(self) -> list[int]:
        pal = self.options.get(CONF_PALETTE) or []
        return [int(x) for x in pal] or [0]

    @property
    def _prefix(self) -> str:
        return str(self.options.get(CONF_PAIR_PREFIX, "Inovelli Link"))

    @property
    def _light_idle_hue(self) -> int:
        return int(self.options.get(CONF_DEFAULT_LIGHT_HUE, LED_IDLE_HUE))

    @property
    def _fan_idle_hue(self) -> int:
        return int(self.options.get(CONF_DEFAULT_FAN_HUE, LED_IDLE_HUE_FAN))

    @property
    def _hide_group_entities(self) -> bool:
        return bool(self.options.get(CONF_HIDE_GROUP_ENTITIES, True))

    def _device_type(self, ieee: str) -> str:
        """'fan' for VZM35 fan switches, else 'light' (cached per ieee)."""
        if ieee in self._type_cache:
            return self._type_cache[ieee]
        device = dr.async_get(self.hass).async_get_device(
            connections={(dr.CONNECTION_ZIGBEE, ieee)}
        )
        model = (getattr(device, "model", "") or "") if device is not None else ""
        kind = "fan" if "vzm35" in model.lower() else "light"
        self._type_cache[ieee] = kind
        return kind

    def _idle_hue(self, ieee: str) -> int:
        return self._fan_idle_hue if self._device_type(ieee) == "fan" else self._light_idle_hue

    async def _set_idle_color(self, ieee: str) -> None:
        """Reset a switch's LED bar to its type-appropriate ungrouped color."""
        await self._set_color(ieee, self._idle_hue(ieee))

    # -- lifecycle -------------------------------------------------------------
    async def async_shutdown(self) -> None:
        self._cancel_timer()

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _arm_timer(self) -> None:
        self._cancel_timer()
        self._timer = self.hass.loop.call_later(self._window, self._on_expire)

    def _on_expire(self) -> None:
        self.hass.async_create_task(self._async_expire())

    async def _async_expire(self) -> None:
        async with self._lock:
            anchor = self._state.anchor
            self._state = _State()
            if anchor:
                # Setup mode: any color chosen by tapping sticks (no idle revert);
                # just stop the pairing-window flash.
                await self._led_clear(anchor)

    # -- event entry point -----------------------------------------------------
    async def handle_event(self, command: str, ieee: str) -> None:
        action = self._cmd_actions.get(command)
        if action is None:
            return
        ieee = ieee.lower()
        try:
            async with self._lock:
                self._expire_if_stale()
                if action == ACTION_ARM:
                    await self._hold(ieee)
                elif action == ACTION_COLOR:
                    await self._tap(ieee)
                elif action == ACTION_REMOVE:
                    await self._leave(ieee)
                elif action == ACTION_EXIT:
                    await self._exit(ieee)
            self._notify()
        except ZhaUnavailable:
            _LOGGER.warning("ZHA gateway unavailable; ignoring %s from %s", command, ieee)
        except Exception:  # noqa: BLE001 - never let a bad event kill the listener
            _LOGGER.exception("Error handling %s from %s", command, ieee)

    def _active(self, ieee: str, *, is_anchor: bool) -> bool:
        st = self._state
        if not st.anchor or (self.hass.loop.time() - st.ts) >= self._window:
            return False
        return st.anchor == ieee if is_anchor else st.anchor != ieee

    def _expire_if_stale(self) -> None:
        st = self._state
        if st.anchor and (self.hass.loop.time() - st.ts) >= self._window:
            self._state = _State()

    # -- state machine (ported from inovelli_pair.py) --------------------------
    async def _hold(self, ieee: str) -> None:
        st = self._state
        if self._active(ieee, is_anchor=False):  # window open, X is not the anchor
            anchor, gid, color = st.anchor, st.group_id, st.color
            if gid is None:
                group = await self._zha.create_group(self._next_group_name(), anchor)
                gid = getattr(group, "group_id", None)
                await self._zha.bind(anchor, gid)
                await self._set_color(anchor, color)
                if gid is not None:
                    self.hass.async_create_task(self._async_hide_new_group(gid))
            existing = await self._pairing_group_of(ieee)
            if existing is not None and getattr(existing, "group_id", None) == gid:
                await self._led(ieee, color, 2)  # ADD-ONLY: already in -> no-op
                act = "already in"
            else:
                if existing is not None:
                    await self._leave_group(ieee, existing.group_id)  # move
                await self._zha.bind(ieee, gid)
                await self._zha.add_member(gid, ieee)
                await self._set_color(ieee, color)
                await self._led(ieee, color, 3)
                act = "joined"
            self._state = _State(
                anchor=anchor, group_id=gid, ts=self.hass.loop.time(), color=color, cidx=st.cidx
            )
            self._arm_timer()
            _LOGGER.debug("%s: %s -> group %s", act, ieee, gid)
            return

        # arm pairing for X's group (existing or new)
        existing = await self._pairing_group_of(ieee)
        gid = getattr(existing, "group_id", None) if existing is not None else None
        if gid is not None:
            cur = self._get_color(ieee)
            cidx = self._palette.index(cur) if cur in self._palette else 0
        else:
            cidx = 0
        color = self._palette[cidx]
        self._state = _State(
            anchor=ieee, group_id=gid, ts=self.hass.loop.time(), color=color, cidx=cidx
        )
        if gid is None:
            await self._set_idle_color(ieee)
        await self._led(ieee, color, self._window)
        self._arm_timer()
        _LOGGER.debug("arm: %s opened group %s (hue %s)", ieee, gid, color)

    async def _tap(self, ieee: str) -> None:
        if not self._active(ieee, is_anchor=True):
            _LOGGER.debug("tap ignored (not the pairing anchor): %s", ieee)
            return
        pal = self._palette
        cidx = (self._state.cidx + 1) % len(pal)
        color = pal[cidx]
        self._state.cidx = cidx
        self._state.color = color
        self._state.ts = self.hass.loop.time()
        if self._state.group_id is not None:
            for member in await self._group_ieees(self._state.group_id):
                await self._set_color(member, color)
        else:
            # Setup mode: recolor just this standalone switch (sticks after expiry).
            await self._set_color(ieee, color)
        await self._led(ieee, color, self._window)
        self._arm_timer()
        _LOGGER.debug("color: %s -> hue %s (group=%s)", ieee, color, self._state.group_id)

    async def _leave(self, ieee: str) -> None:
        group = await self._pairing_group_of(ieee)
        if group is None:
            _LOGGER.debug("leave: %s not in a pairing group", ieee)
            return
        await self._leave_group(ieee, group.group_id)
        await self._led(ieee, self._idle_hue(ieee), 3)
        if self._state.anchor == ieee:
            self._state = _State()
            self._cancel_timer()
        _LOGGER.debug("leave: %s removed from group %s", ieee, group.group_id)

    async def _exit(self, ieee: str) -> None:
        if not self._active(ieee, is_anchor=True):
            return
        self._state = _State()
        self._cancel_timer()
        await self._led_clear(ieee)
        _LOGGER.debug("exit: %s left pairing mode", ieee)

    # -- group helpers ---------------------------------------------------------
    def _next_group_name(self) -> str:
        used = []
        for g in self._zha.list_groups():
            name = str(getattr(g, "name", ""))
            if name.startswith(self._prefix) and name.split()[-1].isdigit():
                used.append(int(name.split()[-1]))
        return f"{self._prefix} {1 + max(used or [0])}"

    async def _pairing_group_of(self, ieee: str) -> Any | None:
        for g in self._zha.list_groups():
            if not str(getattr(g, "name", "")).startswith(self._prefix):
                continue
            if ieee in self._zha.group_member_ieees(g):
                return g
        return None

    async def _group_ieees(self, group_id: int) -> list[str]:
        group = self._zha.get_group(group_id)
        return self._zha.group_member_ieees(group) if group is not None else []

    async def _leave_group(self, ieee: str, group_id: int) -> None:
        await self._zha.bind(ieee, group_id, unbind=True)
        await self._zha.remove_member(group_id, ieee)
        await self._set_idle_color(ieee)
        remaining = await self._group_ieees(group_id)
        if len(remaining) < 2:
            await self._dissolve(group_id)

    async def _dissolve(self, group_id: int) -> None:
        for member in await self._group_ieees(group_id):
            await self._zha.bind(member, group_id, unbind=True)
            await self._set_idle_color(member)
        await self._zha.remove_group(group_id)

    # -- public API (services + dashboard) -------------------------------------
    def _notify(self) -> None:
        """Tell listeners (coordinator/sensor/dashboard) that groups changed."""
        async_dispatcher_send(self.hass, SIGNAL_GROUPS_UPDATED)

    def _device_name(self, ieee: str) -> str:
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device(connections={(dr.CONNECTION_ZIGBEE, ieee)})
        if device is not None:
            return device.name_by_user or device.name or ieee
        return ieee

    @staticmethod
    def _hue_to_hex(hue: int) -> str:
        """Inovelli LED hue (0-255) -> web hex, at full saturation/value."""
        r, g, b = colorsys.hsv_to_rgb((int(hue) % 256) / 255.0, 1.0, 1.0)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    def list_groups(self) -> list[dict[str, Any]]:
        """Snapshot of the pairing groups for the dashboard / sensor (sync-safe)."""
        try:
            groups = self._zha.list_groups()
        except ZhaUnavailable:
            return []
        out: list[dict[str, Any]] = []
        for g in groups:
            name = str(getattr(g, "name", ""))
            if not name.startswith(self._prefix):
                continue
            ieees = self._zha.group_member_ieees(g)
            hue = self._get_color(ieees[0]) if ieees else self._palette[0]
            out.append(
                {
                    "group_id": getattr(g, "group_id", None),
                    "name": name,
                    "members": [{"ieee": i, "name": self._device_name(i)} for i in ieees],
                    "color_hue": hue,
                    "color_hex": self._hue_to_hex(hue),
                }
            )
        out.sort(key=lambda x: x["name"])
        return out

    async def async_create_group(
        self, member_ieees: list[str], hue: int | None = None, name: str | None = None
    ) -> int | None:
        members = [i.lower() for i in member_ieees]
        if len(members) < 2:
            raise ValueError("A pairing group needs at least two switches.")
        color = self._palette[0] if hue is None else int(hue)
        # Groups are re-discovered by name prefix, so every created group must carry
        # it — a custom label becomes a suffix ("Inovelli Link Kitchen").
        if name:
            gname = name if name.startswith(self._prefix) else f"{self._prefix} {name}"
        else:
            gname = self._next_group_name()
        async with self._lock:
            group = await self._zha.create_group(gname, members[0])
            gid = getattr(group, "group_id", None)
            await self._zha.bind(members[0], gid)
            for ieee in members[1:]:
                await self._zha.bind(ieee, gid)
                await self._zha.add_member(gid, ieee)
            for ieee in members:
                await self._set_color(ieee, color)
        self._notify()
        if gid is not None:
            self.hass.async_create_task(self._async_hide_new_group(gid))
        return gid

    async def async_add_member(self, group_id: int, ieee: str) -> None:
        ieee = ieee.lower()
        async with self._lock:
            group = self._zha.get_group(group_id)
            if group is None:
                raise ValueError(f"No pairing group with id {group_id}.")
            existing = self._zha.group_member_ieees(group)
            color = self._get_color(existing[0]) if existing else self._palette[0]
            prior = await self._pairing_group_of(ieee)
            if prior is not None and getattr(prior, "group_id", None) != group_id:
                await self._leave_group(ieee, prior.group_id)
            await self._zha.bind(ieee, group_id)
            await self._zha.add_member(group_id, ieee)
            await self._set_color(ieee, color)
        self._notify()

    async def async_remove_member(self, group_id: int, ieee: str) -> None:
        ieee = ieee.lower()
        async with self._lock:
            await self._leave_group(ieee, group_id)
        self._notify()

    async def async_set_group_color(self, group_id: int, hue: int) -> None:
        async with self._lock:
            for member in await self._group_ieees(group_id):
                await self._set_color(member, int(hue))
        self._notify()

    async def async_delete_group(self, group_id: int) -> None:
        async with self._lock:
            await self._dissolve(group_id)
        self._notify()

    async def async_enter_pairing_mode(self, ieee: str) -> None:
        ieee = ieee.lower()
        async with self._lock:
            self._expire_if_stale()
            await self._hold(ieee)
        self._notify()

    # -- ZHA group-entity visibility -------------------------------------------
    def _zha_group_entities(self, group_id: int) -> list[str]:
        """The light/switch entities ZHA auto-creates for a group.

        Their registry unique_id is ``<domain>_zha_group_0x{group_id:04x}`` — a stable
        anchor, so we never match on the (renameable) friendly entity_id.
        """
        reg = er.async_get(self.hass)
        suffix = f"_zha_group_0x{group_id:04x}"
        return [
            entry.entity_id
            for entry in reg.entities.values()
            if entry.platform == "zha" and entry.unique_id.endswith(suffix)
        ]

    async def async_apply_group_visibility(self, group_ids: list[int] | None = None) -> None:
        """Disable (or, when the option is off, re-enable) redundant ZHA group entities.

        These duplicate the bound switches and otherwise leak to HomeKit/Google/etc.
        Only entities we disabled ourselves are re-enabled when the option is turned off.
        """
        reg = er.async_get(self.hass)
        hide = self._hide_group_entities
        if group_ids is None:
            group_ids = [g["group_id"] for g in self.list_groups()]
        for gid in group_ids:
            if gid is None:
                continue
            for entity_id in self._zha_group_entities(gid):
                entry = reg.async_get(entity_id)
                if entry is None:
                    continue
                if hide and entry.disabled_by is None:
                    reg.async_update_entity(
                        entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION
                    )
                elif not hide and entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                    reg.async_update_entity(entity_id, disabled_by=None)

    async def _async_hide_new_group(self, group_id: int) -> None:
        """Hide a freshly-created group's entities once ZHA has registered them."""
        if not self._hide_group_entities:
            return
        for _ in range(8):
            if self._zha_group_entities(group_id):
                await self.async_apply_group_visibility([group_id])
                return
            await asyncio.sleep(1)

    # -- LED helpers -----------------------------------------------------------
    def _color_entities(self, ieee: str) -> tuple[str | None, str | None]:
        if ieee in self._color_cache:
            return self._color_cache[ieee]
        dev_reg = dr.async_get(self.hass)
        ent_reg = er.async_get(self.hass)
        device = dev_reg.async_get_device(connections={(dr.CONNECTION_ZIGBEE, ieee)})
        on = off = None
        if device is not None:
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            ):
                if ent.entity_id.endswith(LED_ON_COLOR_SUFFIX):
                    on = ent.entity_id
                elif ent.entity_id.endswith(LED_OFF_COLOR_SUFFIX):
                    off = ent.entity_id
        self._color_cache[ieee] = (on, off)
        return on, off

    async def _set_color(self, ieee: str, hue: int) -> None:
        on, off = self._color_entities(ieee)
        for entity_id in (on, off):
            if entity_id:
                await self.hass.services.async_call(
                    "number",
                    "set_value",
                    {"entity_id": entity_id, "value": hue},
                    blocking=True,
                )

    def _get_color(self, ieee: str) -> int:
        on, _ = self._color_entities(ieee)
        if on and (state := self.hass.states.get(on)) is not None:
            try:
                return int(float(state.state))
            except (ValueError, TypeError):
                return self._palette[0]
        return self._palette[0]

    async def _led(self, ieee: str, color: int, duration: int) -> None:
        await self._issue_led_effect(ieee, LED_FX_FAST_BLINK, color, 100, duration)

    async def _led_clear(self, ieee: str) -> None:
        await self._issue_led_effect(ieee, LED_FX_CLEAR, 0, 0, 0)

    async def _issue_led_effect(
        self, ieee: str, effect: int, color: int, level: int, duration: int
    ) -> None:
        await self.hass.services.async_call(
            "zha",
            "issue_zigbee_cluster_command",
            {
                "ieee": ieee,
                "endpoint_id": 1,
                "cluster_id": INOVELLI_MFG_CLUSTER,
                "cluster_type": "in",
                "command": LED_EFFECT_CMD,
                "command_type": "server",
                "manufacturer": INOVELLI_MFG_ID,
                "params": {
                    "led_effect": effect,
                    "led_color": color,
                    "led_level": level,
                    "led_duration": duration,
                },
            },
            blocking=True,
        )
