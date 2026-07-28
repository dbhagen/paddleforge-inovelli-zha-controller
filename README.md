# Paddleforge Inovelli ZHA Controller

[![License: MIT](https://img.shields.io/github/license/dbhagen/paddleforge-inovelli-zha-controller?color=blue)](LICENSE)
[![Release](https://img.shields.io/github/v/release/dbhagen/paddleforge-inovelli-zha-controller?display_name=tag&sort=semver)](https://github.com/dbhagen/paddleforge-inovelli-zha-controller/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Validate](https://github.com/dbhagen/paddleforge-inovelli-zha-controller/actions/workflows/validate.yml/badge.svg)](https://github.com/dbhagen/paddleforge-inovelli-zha-controller/actions/workflows/validate.yml)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dbhagen&repository=paddleforge-inovelli-zha-controller&category=integration)

> Pair Inovelli Blue switches into **bidirectionally-mirrored Zigbee groups** and set
> **per-group LED bar colors** — entirely from the switch's scene button, over **ZHA**.
> No hand-written automations, no hub round-trip: grouped switches mirror each other at
> the Zigbee level.

## Why

Inovelli Blue switches expose rich multi-tap/hold scene events over Zigbee. This
integration turns those gestures into a live "grouping" workflow: hold a switch to open a
group, hold others to add them, single-tap to color the group, double-tap to remove one,
paddle-tap to finish. Under the hood it creates ZHA groups and binds each switch's control
clusters to the group, so **operating any switch drives all of them** — even if Home
Assistant is offline.

## Supported devices

- **Inovelli Blue 2-in-1 Dimmer — VZM31-SN**
- **Inovelli Blue Fan Switch — VZM35-SN**
- Requires the **ZHA** (Zigbee Home Automation) integration. **Zigbee2MQTT is not supported.**

## Gestures

Use the small **config button** below the paddle (unless noted):

| Gesture | Action |
| --- | --- |
| **Hold** (config button) | Arm pairing / add this switch to the open group (add-only — a hold never removes) |
| **Single-tap** (while pairing) | Cycle the group's LED bar color through the palette |
| **Double-tap** (config button) | Remove this switch from its group |
| **Paddle up or down** (while pairing) | Exit pairing mode immediately |

To pair: **hold** switch A (its bar flashes for the pairing window), then **hold** switch B
within the window — they're now grouped and mirror each other. Keep holding more switches to
add a 3rd/4th. **Single-tap** the switch you're holding to pick a color. **Double-tap** any
switch to drop it from its group.

Each gesture is **remappable** in the options (e.g. use double-tap to arm instead of hold),
and the whole physical sequence can be turned off for a **dashboard-only** setup.

### Setup mode (color a single switch)

The pairing gesture doubles as a per-switch LED setup: **hold** a switch to arm it, then
**single-tap** to cycle its LED bar color. If you never join it to a group, the color you
land on **sticks** — so `hold → tap → walk away` sets any switch's standalone color.

## Dashboard

Enable **Management dashboard** in the options to add an **Paddleforge Controller** sidebar panel
(and a matching Lovelace card) that mirrors every physical action: create groups from a
device picker, add/remove switches, recolor a group with a live-preview hue slider, and
delete groups — all kept in sync with the switches. A `sensor.paddleforge_inovelli_zha_controller_groups`
entity exposes the current groups, and services (`paddleforge_inovelli_zha_controller.create_group`,
`add_member`, `remove_member`, `set_color`, `delete_group`, `enter_pairing_mode`) back the UI
for use in your own automations.

## Requirements

- Home Assistant **2024.8.0** or newer
- The **ZHA** integration with Inovelli Blue switches paired
- [HACS](https://hacs.xyz/)

## Installation

1. In HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/dbhagen/paddleforge-inovelli-zha-controller`, category **Integration**
   (or click the **My Home Assistant** badge above).
3. Install **Paddleforge Inovelli ZHA Controller**, then **restart Home Assistant**.
4. **Settings → Devices & Services → Add Integration →** search "Paddleforge Inovelli ZHA Controller".

## Options

**Settings → Devices & Services → Paddleforge Inovelli ZHA Controller → Configure:**

- **Pairing window (seconds)** — how long a switch stays in pairing mode after a hold (default 20).
- **LED color palette** — comma-separated hues (0–255) cycled by a single tap.
- **Group name prefix** — Zigbee groups are named `"<prefix> N"` (default `Inovelli Link`).
- **Gesture mapping** — pick which button events arm / cycle-color / remove / exit (dropdowns of
  hold, single/double/triple tap, and paddle presses; custom values allowed). Exit accepts several.
- **Default light idle color** / **Default fan idle color** — the LED hue a switch shows when it
  is *not* in a group, chosen per device type (defaults: lights orange `21`, fans blue `170`).
  VZM35 fan switches are detected automatically.
- **Enable physical scene-button pairing** — turn the hardware gestures on/off (default on). Off =
  dashboard-only.
- **Enable management dashboard** — add the sidebar panel + card (default off). Hard-refresh the
  browser after toggling.
- **Hide ZHA group entities** — ZHA auto-creates a `light` + `switch` entity for every Zigbee group.
  They duplicate the bound switches and leak to HomeKit/Google. On (default) disables them in the
  entity registry; turning it off re-enables the ones this integration disabled. The switches still
  mirror each other, so you lose nothing.

## How it works

- Listens to `zha_event` button events; no automations to write.
- Group membership = each switch's **endpoint 1** joins the ZHA group (receiver side).
- Bidirectional mirror = each switch's **endpoint 2** OnOff + LevelControl client clusters
  are bound to the group (sender side), so any switch drives the whole group.
- LED colors use the switch's `default_all_led_*_color` numbers; flashes use the Inovelli
  manufacturer cluster.

## Troubleshooting

- **Nothing happens on a hold** — this reads events from **ZHA**. If your switches are on
  **Zigbee2MQTT**, they are not supported. Confirm the model is VZM31-SN / VZM35-SN.
- **One switch's config button does nothing (but its paddle works)** — a fresh ZHA pairing can
  leave the Inovelli manufacturer cluster (`0xFC31`) unbound, so scene events never reach Home
  Assistant. Fix it with **Settings → Devices & Services → ZHA → the device → ⋮ → Reconfigure
  device** (this re-binds the cluster). Commonly needed on VZM35 fan switches.
- **Enable debug logging:**
  ```yaml
  logger:
    logs:
      custom_components.paddleforge_inovelli_zha_controller: debug
  ```
- This integration relies on ZHA internal APIs. If a Home Assistant upgrade breaks it, please
  open an issue with your HA version and a debug log.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This repo uses
[Conventional Commits](https://www.conventionalcommits.org/) and automated semver releases.

## License

MIT — see [LICENSE](LICENSE).
