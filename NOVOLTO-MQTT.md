# Novolto MQTT Protocol (Reference)

*[Deutsche Version](NOVOLTO-MQTT.de.md)*

Summary of the official Novolto MQTT documentation, supplemented with
how it's actually used in [dbus-novolto.py](dbus-novolto.py). Serves as
a reference in case further fields/settings need to be wired up.

## Info telegram (`<base_topic>/<topic_info>`, default `info`)

A JSON object with all measurements, sent cyclically every `msi`
seconds. All displays in Victron (power, temperatures, Ein/Aus status)
are therefore only as current as the last telegram — noticeable
delay is normal device behavior, not a bug in dbus-novolto.

| Field | Type | Meaning | Used in dbus-novolto |
|---|---|---|---|
| `serial` | String | Device serial number | as `base_topic` in config.ini |
| `unix_time` | Integer | Unix timestamp of the reading | no |
| `msi` | Integer | Measurement interval in seconds | no |
| `avt1` | Float | Board/electronics temperature °C | yes, optional second temp. service (`enable_temperature2_service`) |
| `avtw` | Float | Actual water temperature in the tank °C | yes, temperature service "Novolto Speicher" |
| `sptw` | Float per docs, **actually float when setting** ⚠️ | Target water temperature °C (`sensor.sptw`) | yes, "Max. Temperatur" field |
| `sptwh` | Float per docs, **actually float when setting** ⚠️ | Target temperature hysteresis °C (`sensor.sptwh`) | yes, "Hysterese" field |
| `spp` | Float per docs, **actually integer when setting** ⚠️ | Target power W (`sensor.spp`) | yes, "Leistung" field |
| `avv` | Float | Voltage V, average over 5 s | yes, `/Ac/<Phase>/Voltage` |
| `avp` | Float | Actual power W, average over 5 s | yes, `/Ac/Power`, energy counter, shown in field name |
| `avi` | Float | Current A, average over 5 s | yes, `/Ac/<Phase>/Current` |
| `avf` | Float | Grid frequency Hz | yes, `/Ac/Frequency` |
| `rssi` | Integer | WiFi signal strength | no — diagnostic value, not currently shown |
| `st` | Integer | Bitflags for warnings/errors, see below | no — not currently evaluated |
| `wel` | Float | Energy since device boot, kWh, **estimate** | optional via `energy_source = wel` |
| `rod_st` | Integer | 0/1, supposed to mean "heater active", but proved unreliable (see below) | no |
| `triacon`, `r1on`, `r2on` | — | per manufacturer "miscellaneous diagnostic data", not further documented | no |

⚠️ The Type column is the meaning Novolto documents for the info
telegram — the JSON type actually accepted when **setting** a value
via `<topic_control>` differs for `spp`/`sptw`/`sptwh`, see "Real-world
finding" below.

**`rod_st` tested for real, but unreliable (not covered in the Novolto
docs):** in an initial test, `rod_st` seemed to correlate exactly with
heating status (idle `rod_st:0`/`avp:2.7 W`, heating at high load
`rod_st:1`/`avp:131 W`). A further test at lower power levels (40 W
setpoint) showed: `rod_st` got stuck at `1` even though `avp` had
dropped back to idle level (3–5 W) — likely because `rod_st` reflects
"heating circuit enabled/requested" rather than "current is actually
flowing right now". Since v0.14, dbus-novolto therefore uses
`avp > HEATING_THRESHOLD_W` (15 W) instead of `rod_st` for the Ein/Aus
status. `triacon` is also a plain counter (increases monotonically
even when `rod_st` is back to 0) and doesn't work as a status field
either.

**Important note on `wel`:** according to the manufacturer, this value is
integrated since the last device reboot and is an estimate — it jumps
back to 0 whenever the Novolto reboots and is not persistent. The
default `energy_source = integrate` (own integration from `avp`,
persisted to `/data/dbus-novolto/energy.json`) is therefore the more
reliable choice; `wel` is at best useful for cross-checking.

### Status bitflags (`st`)

Each set bit represents its own warning/error (multiple bits can be
set simultaneously):

| Bit (hex) | Constant | Meaning |
|---|---|---|
| 0x0001 | `STATUS_ERROR_SENSOR_MISSING` | A sensor is missing |
| 0x0002 | `STATUS_ERROR_WATER_TEMP_READ_FAIL` | Water temperature could not be read |
| 0x0004 | `STATUS_ERROR_METER_READING_MISMATCH` | Internal meter readings outside the expected range |
| 0x0008 | `STATUS_WARNING_FAN_RPM_MISMATCH` | Fan RPM outside the expected range |
| 0x0010 | `STATUS_ERROR_BOARD_TEMP_EXCEEDED` | Board temperature above the allowed range |
| 0x0020 | `STATUS_ERROR_BOARD_TEMP_READ_FAIL` | Board temperature could not be read |
| 0x0040 | `STATUS_ERROR_METER_READ_FAIL` | Internal meter could not be read |
| 0x0080 | `STATUS_WARNING_HUB_DISCONNECTED` | Connection to the MQTT broker lost |
| 0x0100 | `STATUS_ERROR_POWER_FREQ_MISMATCH` | Grid frequency outside the expected range |
| 0x0200 | `STATUS_ERROR_MISSING_SETTINGS` | Expected internal settings are missing |
| 0x0400 | `STATUS_ERROR_STB_TRIPPED` | Safety temperature breaker (STB) presumably tripped |

## Changing settings (`<base_topic>/<topic_control>`, default `control`)

JSON format:

```json
{
  "<module>": [
    {"name": "<name>", "value": <value>}
  ]
}
```

Multiple settings in the same module can be set in one call. **The
JSON key is lowercase** (e.g. `sensor`), even though the Novolto docs
capitalize module names (`SENSOR`).

Every change is acknowledged on the info topic:

```json
// Success
{"serial":"...","unix_time":...,"ret":0}

// Error, example
{"serial":"...","unix_time":...,"ret":13,"s_err":"Module SENSOR: SPTW -> wrong type"}
```

dbus-novolto currently does **not** evaluate these acknowledgements —
they arrive on the same topic as the info telegram, but are silently
ignored by `_update()` for lack of known fields (`avp` etc.). A
`ret != 0` only becomes noticeable if you check the log
(`tail -f .../current`) or MQTT Explorer manually.

### Relevant settings (excerpt)

| Module | Name | Type | Description |
|---|---|---|---|
| CORE | `reboot` | bool | Trigger a reboot (not persisted) |
| OTA | `url` | string | URL of the firmware binary |
| OTA | `update` | bool | Trigger a firmware update (not persisted) |
| SIG | `aur_volume` | float | Beeper volume, 0.0 (silent) – 1.0 (full) |
| SENSOR | `sptw` | float | Target water temperature °C |
| SENSOR | `sptwh` | float | Hysteresis °C — heater turns **off** above `sptw + sptwh/2`, **on** below `sptw - sptwh/2` |
| SENSOR | `spp` | float | Target power W (assumes 230 V, actual power may differ) |

**Real-world finding (v0.11):** the Novolto docs uniformly list
`spp`/`sptw`/`sptwh` as type `float` — in reality (per MQTT ack on our
device's firmware) each field behaves differently:

- `spp` requires **integer** (`20`, not `20.0`) — float gets rejected
  with `ret=13 "Module SENSOR: SPP -> wrong type"`.
- `sptw`/`sptwh` require **float** (`34.0`, not `34`) — integer gets
  rejected with `ret=13 "Module SENSOR: SPTWH -> wrong type"`.

dbus-novolto accordingly sends `spp` as an integer, `sptw`/`sptwh` as
floats. Don't generalize this to other settings without verifying each
one individually via the ack.

A complete list of all settings is available in the developer menu of
the Novolto web config.

## Possible extensions (not implemented yet)

- Map `st` to an alarm/status in Victron (e.g. a generic warning
  status or plain-text log of the set bits)
- Evaluate `ret`/`s_err` acknowledgements and log on failure, instead
  of silently discarding them
- Show `rssi` as diagnostic info (e.g. append it to
  `/Mgmt/Connection`)
- `triacon`, `r1on`, `r2on` remain unused, since they're not documented
  in detail by the manufacturer and (for `triacon`) it's a plain
  counter unsuitable for the Switch Pane
