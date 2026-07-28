"""Config and options flow for Paddleforge Inovelli ZHA Controller."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import voluptuous as vol

from .const import (
    CONF_CMD_ARM,
    CONF_CMD_COLOR,
    CONF_CMD_EXIT,
    CONF_CMD_REMOVE,
    CONF_DEFAULT_FAN_HUE,
    CONF_DEFAULT_LIGHT_HUE,
    CONF_ENABLE_DASHBOARD,
    CONF_ENABLE_HARDWARE,
    CONF_HIDE_GROUP_ENTITIES,
    CONF_PAIR_PREFIX,
    CONF_PALETTE,
    CONF_WINDOW_SECONDS,
    DEFAULT_CMD_ARM,
    DEFAULT_CMD_COLOR,
    DEFAULT_CMD_EXIT,
    DEFAULT_CMD_REMOVE,
    DEFAULT_ENABLE_DASHBOARD,
    DEFAULT_ENABLE_HARDWARE,
    DEFAULT_HIDE_GROUP_ENTITIES,
    DEFAULT_OPTIONS,
    DOMAIN,
    GESTURE_COMMANDS,
    GROUP_NAME_PREFIX_DEFAULT,
    LED_IDLE_HUE,
    LED_IDLE_HUE_FAN,
    PALETTE_DEFAULT,
    WINDOW_SECONDS_DEFAULT,
)

_GESTURE_OPTIONS = [SelectOptionDict(value=cmd, label=label) for cmd, label in GESTURE_COMMANDS]


def _gesture_selector(*, multiple: bool) -> SelectSelector:
    """A dropdown of known gesture commands; custom values still allowed."""
    return SelectSelector(
        SelectSelectorConfig(
            options=_GESTURE_OPTIONS,
            multiple=multiple,
            custom_value=True,
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _hue_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=0, max=255, step=1, mode=NumberSelectorMode.SLIDER)
    )


def _to_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value).replace(";", ",").split(",") if p.strip()]


def _palette_to_str(palette: list[int]) -> str:
    return ", ".join(str(x) for x in palette)


def _palette_from_str(value: str) -> list[int]:
    parts = [p.strip() for p in str(value).replace(";", ",").split(",")]
    return [int(p) for p in parts if p != ""]


class InovelliScenePairingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance UI setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Paddleforge Inovelli ZHA Controller", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return InovelliScenePairingOptionsFlow()


class InovelliScenePairingOptionsFlow(OptionsFlow):
    """Tune the pairing window, gestures, LED colors, and dashboard."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_WINDOW_SECONDS: int(user_input[CONF_WINDOW_SECONDS]),
                    CONF_PALETTE: _palette_from_str(user_input[CONF_PALETTE]),
                    CONF_PAIR_PREFIX: user_input[CONF_PAIR_PREFIX],
                    CONF_CMD_ARM: user_input[CONF_CMD_ARM],
                    CONF_CMD_COLOR: user_input[CONF_CMD_COLOR],
                    CONF_CMD_REMOVE: user_input[CONF_CMD_REMOVE],
                    CONF_CMD_EXIT: _to_list(user_input[CONF_CMD_EXIT]),
                    CONF_DEFAULT_LIGHT_HUE: int(user_input[CONF_DEFAULT_LIGHT_HUE]),
                    CONF_DEFAULT_FAN_HUE: int(user_input[CONF_DEFAULT_FAN_HUE]),
                    CONF_ENABLE_HARDWARE: user_input[CONF_ENABLE_HARDWARE],
                    CONF_ENABLE_DASHBOARD: user_input[CONF_ENABLE_DASHBOARD],
                    CONF_HIDE_GROUP_ENTITIES: user_input[CONF_HIDE_GROUP_ENTITIES],
                },
            )

        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WINDOW_SECONDS,
                    default=current.get(CONF_WINDOW_SECONDS, WINDOW_SECONDS_DEFAULT),
                ): vol.All(vol.Coerce(int), vol.Range(min=3, max=120)),
                vol.Required(
                    CONF_PALETTE,
                    default=_palette_to_str(current.get(CONF_PALETTE, PALETTE_DEFAULT)),
                ): str,
                vol.Required(
                    CONF_PAIR_PREFIX,
                    default=current.get(CONF_PAIR_PREFIX, GROUP_NAME_PREFIX_DEFAULT),
                ): str,
                vol.Required(
                    CONF_CMD_ARM, default=current.get(CONF_CMD_ARM, DEFAULT_CMD_ARM)
                ): _gesture_selector(multiple=False),
                vol.Required(
                    CONF_CMD_COLOR, default=current.get(CONF_CMD_COLOR, DEFAULT_CMD_COLOR)
                ): _gesture_selector(multiple=False),
                vol.Required(
                    CONF_CMD_REMOVE, default=current.get(CONF_CMD_REMOVE, DEFAULT_CMD_REMOVE)
                ): _gesture_selector(multiple=False),
                vol.Required(
                    CONF_CMD_EXIT, default=_to_list(current.get(CONF_CMD_EXIT, DEFAULT_CMD_EXIT))
                ): _gesture_selector(multiple=True),
                vol.Required(
                    CONF_DEFAULT_LIGHT_HUE,
                    default=current.get(CONF_DEFAULT_LIGHT_HUE, LED_IDLE_HUE),
                ): _hue_selector(),
                vol.Required(
                    CONF_DEFAULT_FAN_HUE,
                    default=current.get(CONF_DEFAULT_FAN_HUE, LED_IDLE_HUE_FAN),
                ): _hue_selector(),
                vol.Required(
                    CONF_ENABLE_HARDWARE,
                    default=current.get(CONF_ENABLE_HARDWARE, DEFAULT_ENABLE_HARDWARE),
                ): bool,
                vol.Required(
                    CONF_ENABLE_DASHBOARD,
                    default=current.get(CONF_ENABLE_DASHBOARD, DEFAULT_ENABLE_DASHBOARD),
                ): bool,
                vol.Required(
                    CONF_HIDE_GROUP_ENTITIES,
                    default=current.get(CONF_HIDE_GROUP_ENTITIES, DEFAULT_HIDE_GROUP_ENTITIES),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
