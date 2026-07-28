"""Config and options flow for Paddleforge Inovelli ZHA Controller.

Two entry shapes under one domain:
- "controller" (single instance): the grouping/pairing system + dashboard + services.
- "device_timer" (one per switch): a per-device ventilation timer.
The first step is a menu to pick which kind to add.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
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
    CONF_CMD_DOWN_HOLD,
    CONF_CMD_DOWN_RELEASE,
    CONF_CMD_EXIT,
    CONF_CMD_REMOVE,
    CONF_CMD_START,
    CONF_CMD_UP_HOLD,
    CONF_CMD_UP_RELEASE,
    CONF_DEFAULT_FAN_HUE,
    CONF_DEFAULT_LIGHT_HUE,
    CONF_DEVICE_ID,
    CONF_DOUBLE_TAP_MINUTES,
    CONF_ENABLE_DASHBOARD,
    CONF_ENABLE_HARDWARE,
    CONF_ENTRY_TYPE,
    CONF_FLASH_THRESHOLD_SECONDS,
    CONF_HIDE_GROUP_ENTITIES,
    CONF_HOLD_RAMP_SECONDS,
    CONF_LED_COLOR_HUE,
    CONF_LED_REFRESH_INTERVAL,
    CONF_MAX_MINUTES,
    CONF_PAIR_PREFIX,
    CONF_PALETTE,
    CONF_PULSE_HUE,
    CONF_WINDOW_SECONDS,
    DEFAULT_CMD_ARM,
    DEFAULT_CMD_COLOR,
    DEFAULT_CMD_DOWN_HOLD,
    DEFAULT_CMD_DOWN_RELEASE,
    DEFAULT_CMD_EXIT,
    DEFAULT_CMD_REMOVE,
    DEFAULT_CMD_START,
    DEFAULT_CMD_UP_HOLD,
    DEFAULT_CMD_UP_RELEASE,
    DEFAULT_CONTROLLER_OPTIONS,
    DEFAULT_ENABLE_DASHBOARD,
    DEFAULT_ENABLE_HARDWARE,
    DEFAULT_FLASH_THRESHOLD_SECONDS,
    DEFAULT_HIDE_GROUP_ENTITIES,
    DEFAULT_HOLD_RAMP_SECONDS,
    DEFAULT_LED_COLOR_HUE,
    DEFAULT_LED_REFRESH_INTERVAL,
    DEFAULT_MAX_MINUTES,
    DEFAULT_PULSE_HUE,
    DEFAULT_TIMER_OPTIONS,
    DOMAIN,
    ENTRY_TYPE_CONTROLLER,
    ENTRY_TYPE_TIMER,
    GESTURE_COMMANDS,
    GROUP_NAME_PREFIX_DEFAULT,
    LED_IDLE_HUE,
    LED_IDLE_HUE_FAN,
    PALETTE_DEFAULT,
    WINDOW_SECONDS_DEFAULT,
)

_GESTURE_OPTIONS = [SelectOptionDict(value=cmd, label=label) for cmd, label in GESTURE_COMMANDS]


def _gesture_selector(*, multiple: bool = False) -> SelectSelector:
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


def _minutes_selector(max_value: int = 240) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=1, max=max_value, step=1, mode=NumberSelectorMode.BOX)
    )


def _box(minimum: int, maximum: int, step: int = 1) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX)
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


class PaddleforgeControllerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Menu-driven setup: one grouping controller, plus per-device timers."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["controller", "device_timer"])

    async def async_step_controller(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add the single grouping controller entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Paddleforge Inovelli ZHA Controller",
            data={CONF_ENTRY_TYPE: ENTRY_TYPE_CONTROLLER},
        )

    async def async_step_device_timer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add one per-switch ventilation timer."""
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            device = dr.async_get(self.hass).async_get(device_id)
            title = (device.name_by_user or device.name) if device else "Ventilation Timer"
            return self.async_create_entry(
                title=title,
                data={CONF_ENTRY_TYPE: ENTRY_TYPE_TIMER, CONF_DEVICE_ID: device_id},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DeviceSelector(
                    DeviceSelectorConfig(integration="zha", manufacturer="Inovelli")
                )
            }
        )
        return self.async_show_form(step_id="device_timer", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        if config_entry.data.get(CONF_ENTRY_TYPE) == ENTRY_TYPE_TIMER:
            return TimerOptionsFlow()
        return ControllerOptionsFlow()


class ControllerOptionsFlow(OptionsFlow):
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

        current = {**DEFAULT_CONTROLLER_OPTIONS, **self.config_entry.options}
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
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_COLOR, default=current.get(CONF_CMD_COLOR, DEFAULT_CMD_COLOR)
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_REMOVE, default=current.get(CONF_CMD_REMOVE, DEFAULT_CMD_REMOVE)
                ): _gesture_selector(),
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


class TimerOptionsFlow(OptionsFlow):
    """Tune the timer limits, LED, and paddle-gesture mapping."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**DEFAULT_TIMER_OPTIONS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MAX_MINUTES, default=current.get(CONF_MAX_MINUTES, DEFAULT_MAX_MINUTES)
                ): _minutes_selector(),
                vol.Required(
                    CONF_DOUBLE_TAP_MINUTES,
                    default=current.get(CONF_DOUBLE_TAP_MINUTES, DEFAULT_MAX_MINUTES),
                ): _minutes_selector(),
                vol.Required(
                    CONF_HOLD_RAMP_SECONDS,
                    default=current.get(CONF_HOLD_RAMP_SECONDS, DEFAULT_HOLD_RAMP_SECONDS),
                ): _box(1, 60),
                vol.Required(
                    CONF_LED_REFRESH_INTERVAL,
                    default=current.get(CONF_LED_REFRESH_INTERVAL, DEFAULT_LED_REFRESH_INTERVAL),
                ): _box(2, 60),
                vol.Required(
                    CONF_LED_COLOR_HUE,
                    default=current.get(CONF_LED_COLOR_HUE, DEFAULT_LED_COLOR_HUE),
                ): _hue_selector(),
                vol.Required(
                    CONF_PULSE_HUE,
                    default=current.get(CONF_PULSE_HUE, DEFAULT_PULSE_HUE),
                ): _hue_selector(),
                vol.Required(
                    CONF_FLASH_THRESHOLD_SECONDS,
                    default=current.get(
                        CONF_FLASH_THRESHOLD_SECONDS, DEFAULT_FLASH_THRESHOLD_SECONDS
                    ),
                ): _box(0, 600, 5),
                vol.Required(
                    CONF_CMD_START, default=current.get(CONF_CMD_START, DEFAULT_CMD_START)
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_UP_HOLD, default=current.get(CONF_CMD_UP_HOLD, DEFAULT_CMD_UP_HOLD)
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_UP_RELEASE,
                    default=current.get(CONF_CMD_UP_RELEASE, DEFAULT_CMD_UP_RELEASE),
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_DOWN_HOLD,
                    default=current.get(CONF_CMD_DOWN_HOLD, DEFAULT_CMD_DOWN_HOLD),
                ): _gesture_selector(),
                vol.Required(
                    CONF_CMD_DOWN_RELEASE,
                    default=current.get(CONF_CMD_DOWN_RELEASE, DEFAULT_CMD_DOWN_RELEASE),
                ): _gesture_selector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
