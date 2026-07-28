"""Services mirroring the physical gestures (create/add/remove/recolor/delete)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
import voluptuous as vol

from .const import (
    DOMAIN,
    SERVICE_ADD_MEMBER,
    SERVICE_CREATE_GROUP,
    SERVICE_DELETE_GROUP,
    SERVICE_ENTER_PAIRING,
    SERVICE_REMOVE_MEMBER,
    SERVICE_SET_COLOR,
)
from .runtime import get_engine

_HUE = vol.All(vol.Coerce(int), vol.Range(min=0, max=255))
_GID = vol.All(vol.Coerce(int), vol.Range(min=1))

_CREATE_SCHEMA = vol.Schema(
    {
        vol.Required("switches"): vol.All(cv.ensure_list, [cv.string], vol.Length(min=2)),
        vol.Optional("color_hue"): _HUE,
        vol.Optional("name"): cv.string,
    }
)
_ADD_SCHEMA = vol.Schema({vol.Required("group_id"): _GID, vol.Required("switch"): cv.string})
_REMOVE_SCHEMA = _ADD_SCHEMA
_COLOR_SCHEMA = vol.Schema({vol.Required("group_id"): _GID, vol.Required("color_hue"): _HUE})
_DELETE_SCHEMA = vol.Schema({vol.Required("group_id"): _GID})
_PAIR_SCHEMA = vol.Schema({vol.Required("switch"): cv.string})


def _ieee_from_device(hass: HomeAssistant, device_id: str) -> str:
    """Map a ZHA device_id to its IEEE address via the device registry."""
    device = dr.async_get(hass).async_get(device_id)
    if device is not None:
        for domain, ident in device.connections:
            if domain == dr.CONNECTION_ZIGBEE:
                return str(ident).lower()
    raise ServiceValidationError(f"Device {device_id} is not a ZHA/Zigbee device.")


def _engine_or_raise(hass: HomeAssistant) -> Any:
    engine = get_engine(hass)
    if engine is None:
        raise HomeAssistantError("Paddleforge Inovelli ZHA Controller is not loaded.")
    return engine


@callback
def async_register(hass: HomeAssistant) -> None:
    """Register all services (idempotent per HA run)."""

    async def _create(call: ServiceCall) -> ServiceResponse:
        engine = _engine_or_raise(hass)
        ieees = [_ieee_from_device(hass, d) for d in call.data["switches"]]
        try:
            gid = await engine.async_create_group(
                ieees, call.data.get("color_hue"), call.data.get("name")
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        return {"group_id": gid}

    async def _add(call: ServiceCall) -> None:
        engine = _engine_or_raise(hass)
        try:
            await engine.async_add_member(
                call.data["group_id"], _ieee_from_device(hass, call.data["switch"])
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

    async def _remove(call: ServiceCall) -> None:
        engine = _engine_or_raise(hass)
        await engine.async_remove_member(
            call.data["group_id"], _ieee_from_device(hass, call.data["switch"])
        )

    async def _color(call: ServiceCall) -> None:
        engine = _engine_or_raise(hass)
        await engine.async_set_group_color(call.data["group_id"], call.data["color_hue"])

    async def _delete(call: ServiceCall) -> None:
        engine = _engine_or_raise(hass)
        await engine.async_delete_group(call.data["group_id"])

    async def _pair(call: ServiceCall) -> None:
        engine = _engine_or_raise(hass)
        await engine.async_enter_pairing_mode(_ieee_from_device(hass, call.data["switch"]))

    hass.services.async_register(
        DOMAIN, SERVICE_CREATE_GROUP, _create, _CREATE_SCHEMA, SupportsResponse.OPTIONAL
    )
    hass.services.async_register(DOMAIN, SERVICE_ADD_MEMBER, _add, _ADD_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_MEMBER, _remove, _REMOVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_COLOR, _color, _COLOR_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_GROUP, _delete, _DELETE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ENTER_PAIRING, _pair, _PAIR_SCHEMA)


@callback
def async_unregister(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_CREATE_GROUP,
        SERVICE_ADD_MEMBER,
        SERVICE_REMOVE_MEMBER,
        SERVICE_SET_COLOR,
        SERVICE_DELETE_GROUP,
        SERVICE_ENTER_PAIRING,
    ):
        hass.services.async_remove(DOMAIN, service)
