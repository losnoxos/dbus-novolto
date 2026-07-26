# dbus-novolto

*[Deutsche Version](README.de.md)*

Venus OS driver (Victron Cerbo GX) for the Novolto electric water heater
(P2300/P3000) via local MQTT — display, manual power setpoint, and
adjustable max. water temperature via the SwitchableOutput API.

## What shows up in Victron

- **Device list / VRM:** "Novolto Heizstab" as an AC load with actual
  power (W), a persistent energy counter (kWh, survives restarts), and
  voltage/current per phase
- **Switch Pane (GUI v2 / Remote Console / VRM):** group "Novolto" with
  - **Ein/Aus** (On/Off) as a read-only status (not switchable!) —
    shows whether the heater is actually heating right now (`avp`
    above a threshold, `HEATING_THRESHOLD_W`). The Novolto has no real
    on/off, control happens via the power field.
  - Numeric input **Leistung** (power) 0–3000 W in 20 W steps (shows
    the live actual power in the field name) — `0 W` = off
  - Numeric input **Max. Temperatur** (target water temperature)
  - Numeric input **Hysterese** (hysteresis) — the heater turns off
    above `sptw + hysteresis/2` and back on below `sptw - hysteresis/2`,
    `enable_sptwh_control`
- **Temperature sensor** "Novolto Speicher" (avtw,
  `enable_temperature_service`), optionally a second sensor "Novolto
  Elektronik" (avt1, `enable_temperature2_service`) — independently
  toggleable, both with VRM history

## How it works

The Novolto publishes a single JSON telegram on `<base_topic>/info`
with all measurements (power, voltage, temperatures, setpoint, ...).
Control commands go out as JSON on `<base_topic>/control`, e.g.
`{"sensor":[{"name":"spp","value":500.0}]}` for a power setpoint.
All topic names and the setpoint-feedback field are configurable in
`config.ini`. Full field and protocol reference: see
[NOVOLTO-MQTT.md](NOVOLTO-MQTT.md).

## Installation

1. Copy the folder to the Cerbo (e.g. via scp to /data/tmp):
   `scp -r dbus-novolto root@<cerbo-ip>:/data/tmp/`
2. Create `config.ini` from `config.ini.example` and adjust it — at
   minimum `host`, `username`, `password`, and `base_topic` (the
   heater's serial prefix, visible in MQTT Explorer, e.g.
   `141.142.9FFED8`).
3. `sh /data/tmp/dbus-novolto/install.sh`

The installer puts everything under `/data/dbus-novolto`, registers
the daemontools service, and adds the symlink to `/data/rc.local`
(survives Venus OS updates).

Restart the driver: `svc -t /service/dbus-novolto`
Log: `tail -f /var/log/dbus-novolto/current | tai64nlocal`
Uninstall: `sh /data/dbus-novolto/uninstall.sh` (removes the service,
the rc.local entry, and `/data/dbus-novolto` entirely)

## Behavior

- The Novolto has no real on/off — a `0 W` power setpoint *is* "off".
  The Ein/Aus status in the Switch Pane is purely informational,
  derived from `avp` (actual power above `HEATING_THRESHOLD_W`, 15 W),
  not switchable. `rod_st` would have been the more obvious choice but
  proved unreliable in testing (got stuck at 1 at low power levels,
  see NOVOLTO-MQTT.md).
- Inputs in the power field are rounded to the configured watt grid
  (`power_step`) and published immediately.
- `spp` is deliberately sent as an integer (20, not 20.0) — the
  firmware rejects floats with `ret=13 "Module SENSOR: SPP -> wrong
  type"`. `sptw`/`sptwh` behave the opposite way: they're deliberately
  sent as floats (34.0, not 34), integers get rejected with `ret=13
  "wrong type"`. Both confirmed for real via MQTT ack (as of v0.11) —
  each field has its own type, not something that transfers across
  fields.
- External setpoint changes (app/Home Assistant) pull the power slider
  along automatically, except briefly after our own publish (echo
  suppression, 10 s). The Ein/Aus status updates independently,
  directly from `avp`.
- All displays (power, temperatures, Ein/Aus status, ...) only update
  as fast as the Novolto itself sends its info telegram (the `msi`
  field, see NOVOLTO-MQTT.md). This can feel noticeably sluggish —
  that's not a bug in dbus-novolto, it's the device's own send interval.
- No MQTT data for `timeout_seconds` (default 120 s) → the device goes
  to "Disconnected", with a single log line on loss and one when data
  resumes (no repeats).
- The energy counter is integrated from actual power and persisted to
  `/data/dbus-novolto/energy.json` every 5 minutes (survives restarts).

## Tuning / checking

- Adjust phase (`phase`) and system position (`position`:
  ac_in/ac_out/ac_in_2) in config.ini to match the actual wiring.
- Toggle `enable_sptw_control`, `enable_sptwh_control`,
  `enable_temperature2_service` as needed if the Novolto doesn't
  provide these values.

## Related project

[victronenergy.heatpump.novolto](https://github.com/losnoxos/victronenergy.heatpump.novolto)
is an experimental fork testing the native `com.victronenergy.heatpump`
device type from the Venus OS beta (the counterpart to
`com.victronenergy.evcharger` for wallboxes). Requires Venus OS beta,
and as of the last tests there, doesn't yet bring any visible GUI
advantage over this repo.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT, see [LICENSE](LICENSE).
