# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-07-26

### Added
- Single log line when the Novolto stops sending data for longer than
  `timeout_seconds` (device off, WiFi down, ...), and a single line
  when it starts sending again. The watchdog itself never logged
  repeatedly before this (no log-spam risk either way), but the
  offline/online transition was previously invisible in the log.

## [1.0.0] - 2026-07-26

Initial public release.

### Added
- Display of power, voltage/current per phase, temperatures, and a
  persistent energy counter via `com.victronenergy.acload.novolto`.
- Manual power setpoint and adjustable max. water temperature /
  hysteresis via the SwitchableOutput API (Switch Pane).
- Read-only Ein/Aus (on/off) status derived from `avp > 15 W`, since
  the Novolto has no real on/off — `0 W` power setpoint *is* "off".
- Optional second temperature service for the electronics/rod
  temperature (`avt1`).

### Notes
- Protocol quirks (e.g. `spp` must be sent as JSON integer, while
  `sptw`/`sptwh` must be sent as JSON float) are documented in
  [NOVOLTO-MQTT.md](NOVOLTO-MQTT.md), not duplicated here.
- Development history prior to 1.0.0 (trial-and-error while
  reverse-engineering the protocol) is preserved in the git history
  but not repeated in this changelog.
