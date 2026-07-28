"""Constants for the Paddleforge Inovelli ZHA Controller integration."""

from __future__ import annotations

DOMAIN = "paddleforge_inovelli_zha_controller"

# Home Assistant event fired by ZHA for device scene/button actions.
ZHA_EVENT = "zha_event"

# --- Config-entry kind ----------------------------------------------------------
# One integration, two entry shapes: a single global "controller" entry owns the
# grouping/pairing system (groups sensor, panel, services); each "timer" entry owns
# one physical switch's ventilation timer. Stored in entry.data[CONF_ENTRY_TYPE].
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_CONTROLLER = "controller"
ENTRY_TYPE_TIMER = "timer"

# --- Actions and the (configurable) gesture -> action map -----------------------
# On Inovelli Blue over ZHA: button_3 = config button, button_1/button_2 = down/up
# paddle. Each action can be bound to one or more zha_event commands (comma-separated
# in options), so e.g. double-tap can replace hold for arming.
ACTION_ARM = "arm"  # arm pairing / add a switch to the group
ACTION_COLOR = "color"  # cycle the group LED color (while anchor)
ACTION_REMOVE = "remove"  # remove a switch from its group
ACTION_EXIT = "exit"  # exit pairing early (while anchor)

CONF_CMD_ARM = "cmd_arm"
CONF_CMD_COLOR = "cmd_color"
CONF_CMD_REMOVE = "cmd_remove"
CONF_CMD_EXIT = "cmd_exit"

DEFAULT_CMD_ARM = "button_3_hold"
DEFAULT_CMD_COLOR = "button_3_press"
DEFAULT_CMD_REMOVE = "button_3_double"
DEFAULT_CMD_EXIT = "button_1_press, button_2_press"

# --- Zigbee cluster ids we bind for the bidirectional mirror --------------------
CLUSTER_ONOFF = 0x0006  # 6
CLUSTER_LEVEL = 0x0008  # 8
GROUP_MEMBER_ENDPOINT = 1  # the load endpoint (group membership / receiver side)
BINDING_ENDPOINT_FALLBACK = 2  # Inovelli Blue controller (client) endpoint

# --- Inovelli manufacturer cluster for LED bar effects --------------------------
INOVELLI_MFG_CLUSTER = 0xFC31  # 64561
INOVELLI_MFG_ID = 0x122F  # 4655
LED_EFFECT_CMD = 1  # led_effect command id
LED_FX_FAST_BLINK = 2  # fast-blink effect
LED_FX_CLEAR = 0  # clear/stop effect

# LED bar color hues (0-255). Orange is the idle "ungrouped" color for light
# dimmers and is deliberately excluded from the palette so grouped/ungrouped stay
# distinct. Fan switches idle blue by default (the house convention).
LED_IDLE_HUE = 21  # orange (light default idle)
LED_IDLE_HUE_FAN = 170  # blue (fan default idle)
PALETTE_DEFAULT = [0, 42, 85, 127, 170, 212, 234]  # red,yellow,green,cyan,blue,purple,pink

# LED number-entity suffixes exposed by the ZHA Inovelli quirk.
LED_ON_COLOR_SUFFIX = "_default_all_led_on_color"
LED_OFF_COLOR_SUFFIX = "_default_all_led_off_color"

# --- Group naming ---------------------------------------------------------------
GROUP_NAME_PREFIX_DEFAULT = "Inovelli Link"

# --- Pairing window -------------------------------------------------------------
WINDOW_SECONDS_DEFAULT = 20

# --- Options keys ---------------------------------------------------------------
CONF_WINDOW_SECONDS = "window_seconds"
CONF_PALETTE = "palette"
CONF_PAIR_PREFIX = "pair_prefix"
CONF_ENABLE_DASHBOARD = "enable_dashboard"
CONF_ENABLE_HARDWARE = "enable_hardware"
CONF_HIDE_GROUP_ENTITIES = "hide_group_entities"
CONF_DEFAULT_LIGHT_HUE = "default_light_hue"
CONF_DEFAULT_FAN_HUE = "default_fan_hue"

DEFAULT_ENABLE_DASHBOARD = False
DEFAULT_ENABLE_HARDWARE = True
DEFAULT_HIDE_GROUP_ENTITIES = True

# Known Inovelli Blue zha_event gesture commands, offered as dropdown options in the
# options flow (custom values are still allowed for anything not listed here).
GESTURE_COMMANDS = [
    ("button_3_hold", "Config button — hold"),
    ("button_3_press", "Config button — single tap"),
    ("button_3_double", "Config button — double tap"),
    ("button_3_triple", "Config button — triple tap"),
    ("button_2_press", "Up paddle — single tap"),
    ("button_2_double", "Up paddle — double tap"),
    ("button_2_hold", "Up paddle — hold"),
    ("button_2_release", "Up paddle — release"),
    ("button_1_press", "Down paddle — single tap"),
    ("button_1_double", "Down paddle — double tap"),
    ("button_1_hold", "Down paddle — hold"),
    ("button_1_release", "Down paddle — release"),
]

DEFAULT_CONTROLLER_OPTIONS = {
    CONF_WINDOW_SECONDS: WINDOW_SECONDS_DEFAULT,
    CONF_PALETTE: PALETTE_DEFAULT,
    CONF_PAIR_PREFIX: GROUP_NAME_PREFIX_DEFAULT,
    CONF_CMD_ARM: DEFAULT_CMD_ARM,
    CONF_CMD_COLOR: DEFAULT_CMD_COLOR,
    CONF_CMD_REMOVE: DEFAULT_CMD_REMOVE,
    CONF_CMD_EXIT: DEFAULT_CMD_EXIT,
    CONF_ENABLE_DASHBOARD: DEFAULT_ENABLE_DASHBOARD,
    CONF_ENABLE_HARDWARE: DEFAULT_ENABLE_HARDWARE,
    CONF_HIDE_GROUP_ENTITIES: DEFAULT_HIDE_GROUP_ENTITIES,
    CONF_DEFAULT_LIGHT_HUE: LED_IDLE_HUE,
    CONF_DEFAULT_FAN_HUE: LED_IDLE_HUE_FAN,
}

# --- Dashboard / services -------------------------------------------------------
# Dispatcher signal fired after any group mutation (gesture or service driven).
SIGNAL_GROUPS_UPDATED = f"{DOMAIN}_groups_updated"

SERVICE_CREATE_GROUP = "create_group"
SERVICE_ADD_MEMBER = "add_member"
SERVICE_REMOVE_MEMBER = "remove_member"
SERVICE_SET_COLOR = "set_color"
SERVICE_DELETE_GROUP = "delete_group"
SERVICE_ENTER_PAIRING = "enter_pairing_mode"

# Frontend panel/card
PANEL_URL_PATH = "paddleforge-controller"
PANEL_TITLE = "Paddleforge Controller"
PANEL_ICON = "mdi:led-strip-variant"
PANEL_NAME = "paddleforge-inovelli-zha-controller-panel"
FRONTEND_SCRIPT_URL = f"/{DOMAIN}/paddleforge-inovelli-zha-controller-panel.js"
WS_LIST_GROUPS = f"{DOMAIN}/list_groups"


# ================================================================================
# Ventilation-timer feature (per-device "timer" entries). Folded in from the former
# inovelli-fan-timer integration. Gestures here are the PADDLES; the grouping feature
# above uses the CONFIG BUTTON, so both can run on one switch without colliding.
# ================================================================================

# Per-segment LED painting (the timer fills the bar from the bottom).
LED_EFFECT_INDIVIDUAL_CMD = 3  # individual_led_effect (needs led_number 0-6)
LED_SEGMENTS = 7  # the LED bar has 7 individually-addressable segments

# LED effect ids. 0 (clear) + 2 (fast_blink) confirmed on VZM31; SOLID (1) a best
# guess — verify on hardware. (LED_FX_CLEAR / LED_FX_FAST_BLINK defined above.)
LED_FX_SOLID = 1
LED_FX_SLOW_BLINK = 3
LED_FX_PULSE = 4  # breathing — reserved for the (later) humidity auto-mode

# led_duration LED-effect encoding: 1-60 = s, 61-120 = min, 121-254 = hr, 255 = indefinite.
LED_DURATION_INDEFINITE = 255

LED_HUE_TIMER_DEFAULT = 170  # blue (the house "fan" color)
LED_HUE_WHITE = 255  # Inovelli LED color 255 = white (a special value above the 0-254 hue range)

# --- Timer modes ----------------------------------------------------------------
MODE_IDLE = "idle"
MODE_RUNNING = "running"
MODE_SETTING = "setting"
MODE_EXPIRING = "expiring"

# --- Timer gesture commands (paddle) --------------------------------------------
CONF_CMD_START = "cmd_start"
CONF_CMD_UP_HOLD = "cmd_up_hold"
CONF_CMD_UP_RELEASE = "cmd_up_release"
CONF_CMD_DOWN_HOLD = "cmd_down_hold"
CONF_CMD_DOWN_RELEASE = "cmd_down_release"

DEFAULT_CMD_START = "button_2_double"
DEFAULT_CMD_UP_HOLD = "button_2_hold"
DEFAULT_CMD_UP_RELEASE = "button_2_release"
DEFAULT_CMD_DOWN_HOLD = "button_1_hold"
DEFAULT_CMD_DOWN_RELEASE = "button_1_release"

# --- Timer config-entry data ----------------------------------------------------
CONF_DEVICE_ID = "device_id"

# --- Timer options + defaults ---------------------------------------------------
CONF_MAX_MINUTES = "max_minutes"
CONF_DOUBLE_TAP_MINUTES = "double_tap_minutes"
CONF_HOLD_RAMP_SECONDS = "hold_ramp_seconds_full"
CONF_LED_REFRESH_INTERVAL = "led_refresh_interval"
CONF_LED_COLOR_HUE = "led_color_hue"
CONF_PULSE_HUE = "pulse_hue"
CONF_FLASH_THRESHOLD_SECONDS = "flash_threshold_seconds"

DEFAULT_MAX_MINUTES = 30
DEFAULT_HOLD_RAMP_SECONDS = 6
DEFAULT_LED_REFRESH_INTERVAL = 10
DEFAULT_LED_COLOR_HUE = LED_HUE_TIMER_DEFAULT
DEFAULT_PULSE_HUE = LED_HUE_WHITE  # the breathing active-edge segment (255 = white)
DEFAULT_FLASH_THRESHOLD_SECONDS = 60

# Hidden tuning constants (not exposed as options).
RAMP_TICK_INTERVAL = 0.25  # seconds between hold-ramp recomputes
GESTURE_DEBOUNCE_SECONDS = 0.3  # ignore a repeated identical gesture within this window
LOAD_SUPPRESS_SECONDS = 2.0  # ignore self-inflicted relay state changes within this window

# --- Humidity seam (reserved for the follow-up; not rendered yet) ----------------
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_HUMIDITY_THRESHOLD = "humidity_threshold"
CONF_AUTO_MODE = "auto_mode"

DEFAULT_TIMER_OPTIONS = {
    CONF_MAX_MINUTES: DEFAULT_MAX_MINUTES,
    CONF_DOUBLE_TAP_MINUTES: DEFAULT_MAX_MINUTES,
    CONF_HOLD_RAMP_SECONDS: DEFAULT_HOLD_RAMP_SECONDS,
    CONF_LED_REFRESH_INTERVAL: DEFAULT_LED_REFRESH_INTERVAL,
    CONF_LED_COLOR_HUE: DEFAULT_LED_COLOR_HUE,
    CONF_PULSE_HUE: DEFAULT_PULSE_HUE,
    CONF_FLASH_THRESHOLD_SECONDS: DEFAULT_FLASH_THRESHOLD_SECONDS,
    CONF_CMD_START: DEFAULT_CMD_START,
    CONF_CMD_UP_HOLD: DEFAULT_CMD_UP_HOLD,
    CONF_CMD_UP_RELEASE: DEFAULT_CMD_UP_RELEASE,
    CONF_CMD_DOWN_HOLD: DEFAULT_CMD_DOWN_HOLD,
    CONF_CMD_DOWN_RELEASE: DEFAULT_CMD_DOWN_RELEASE,
}

SERVICE_START_TIMER = "start_timer"
SERVICE_CANCEL_TIMER = "cancel_timer"
SERVICE_SET_MINUTES = "set_minutes"
