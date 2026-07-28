"""Sidebar panel + Lovelace card registration.

All of Home Assistant's semi-private frontend surface is confined to this module so
an upstream change is a one-file fix. The bundled ES module is served from a static
path (registered once per HA run — static paths cannot be unregistered) and pulled
in both as the panel's ``module_url`` and as an extra module URL so the companion
card is available in normal dashboards too.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    FRONTEND_SCRIPT_URL,
    PANEL_ICON,
    PANEL_NAME,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

_STATIC_REGISTERED = f"{DOMAIN}_static_registered"
_MODULE_URL = f"{DOMAIN}_module_url"

_URL_ROOT = f"/{DOMAIN}"
_SCRIPT_FILE = "paddleforge-inovelli-zha-controller-panel.js"


def _add_module_url(hass: HomeAssistant, url: str) -> None:
    adder = getattr(frontend, "add_extra_module_url", None) or getattr(
        frontend, "add_extra_js_url", None
    )
    if adder is not None:
        adder(hass, url)


def _remove_module_url(hass: HomeAssistant, url: str) -> None:
    remover = getattr(frontend, "remove_extra_module_url", None) or getattr(
        frontend, "remove_extra_js_url", None
    )
    if remover is not None:
        try:
            remover(hass, url)
        except Exception as err:  # noqa: BLE001 - best-effort cleanup
            _LOGGER.debug("could not remove extra module url: %s", err)


async def async_register(hass: HomeAssistant) -> None:
    """Register the static path (once), the extra module URL, and the sidebar panel."""
    if not hass.data.get(_STATIC_REGISTERED):
        js_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(_URL_ROOT, str(js_dir), False)]
        )
        hass.data[_STATIC_REGISTERED] = True

    integration = await async_get_integration(hass, DOMAIN)
    url = f"{FRONTEND_SCRIPT_URL}?v={integration.version}"
    hass.data[_MODULE_URL] = url
    _add_module_url(hass, url)

    if PANEL_URL_PATH not in hass.data.get("frontend_panels", {}):
        frontend.async_register_built_in_panel(
            hass,
            "custom",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            require_admin=True,
            config={
                "_panel_custom": {
                    "name": PANEL_NAME,
                    "module_url": url,
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
        )


def async_unregister(hass: HomeAssistant) -> None:
    """Remove the panel + extra module URL (the static path stays for this run)."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    if (url := hass.data.get(_MODULE_URL)) is not None:
        _remove_module_url(hass, url)
