"""Read-only websocket command backing the dashboard's live group list."""

from __future__ import annotations

from typing import Any

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import WS_LIST_GROUPS
from .runtime import get_engine


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register the websocket command (idempotent per HA run)."""
    websocket_api.async_register_command(
        hass, WS_LIST_GROUPS, _handle_list_groups, _LIST_GROUPS_SCHEMA
    )


_LIST_GROUPS_SCHEMA = websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend({"type": WS_LIST_GROUPS})


@websocket_api.require_admin
@callback
def _handle_list_groups(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    engine = get_engine(hass)
    groups = engine.list_groups() if engine is not None else []
    connection.send_result(msg["id"], {"groups": groups})
