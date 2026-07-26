# Novolto MQTT-Protokoll (Referenz)

Zusammenfassung der offiziellen Novolto-MQTT-Doku, ergänzt um die konkrete
Nutzung in [dbus-novolto.py](dbus-novolto.py). Dient als Nachschlagewerk,
falls weitere Felder/Einstellungen angebunden werden sollen.

## Info-Telegramm (`<base_topic>/<topic_info>`, Standard `info`)

Ein JSON-Objekt mit allen Messwerten, zyklisch alle `msi` Sekunden.

| Feld | Typ | Bedeutung | Genutzt in dbus-novolto |
|---|---|---|---|
| `serial` | String | Seriennummer des Geräts | als `base_topic` in config.ini |
| `unix_time` | Integer | Unix-Timestamp der Messung | nein |
| `msi` | Integer | Messintervall in Sekunden | nein |
| `avt1` | Float | Board-/Elektroniktemperatur °C | ja, optional zweiter Temp.-Service (`enable_temperature2_service`) |
| `avtw` | Float | Ist-Wassertemperatur im Speicher °C | ja, Temperatur-Service "Novolto Speicher" |
| `sptw` | Float | Sollwert Wassertemperatur °C (`sensor.sptw`) | ja, Feld "Max. Temperatur" |
| `sptwh` | Float | Hysterese der Solltemperatur °C (`sensor.sptwh`) | ja, Feld "Hysterese" |
| `spp` | Float | Sollwert Leistung W (`sensor.spp`) | ja, Feld "Leistung" |
| `avv` | Float | Spannung V, Mittelwert über 5 s | ja, `/Ac/<Phase>/Voltage` |
| `avp` | Float | Ist-Leistung W, Mittelwert über 5 s | ja, `/Ac/Power`, Energiezähler, Anzeige im Feldnamen |
| `avi` | Float | Strom A, Mittelwert über 5 s | ja, `/Ac/<Phase>/Current` |
| `avf` | Float | Netzfrequenz Hz | ja, `/Ac/Frequency` |
| `rssi` | Integer | WLAN-Signalstärke | nein — Diagnosewert, aktuell nicht angezeigt |
| `st` | Integer | Bitflags Warnungen/Fehler, siehe unten | nein — aktuell nicht ausgewertet |
| `wel` | Float | Energie seit Geräte-Boot, kWh, **Schätzwert** | optional über `energy_source = wel` |
| `rod_st`, `triacon`, `r1on`, `r2on` | — | laut Hersteller "miscellaneous diagnostic data", nicht weiter dokumentiert | nein |

**Wichtig zu `wel`:** Der Wert wird laut Hersteller seit dem letzten Geräte-Neustart
integriert und ist ein Schätzwert — er springt bei einem Reboot des Novolto auf 0
zurück und ist nicht persistent. Der Standard `energy_source = integrate`
(eigene Integration aus `avp`, persistiert nach `/data/dbus-novolto/energy.json`)
ist deshalb die belastbarere Wahl; `wel` eignet sich höchstens zum Abgleich.

### Status-Bitflags (`st`)

Jedes gesetzte Bit steht für eine eigene Warnung/einen eigenen Fehler
(mehrere Bits können gleichzeitig gesetzt sein):

| Bit (hex) | Konstante | Bedeutung |
|---|---|---|
| 0x0001 | `STATUS_ERROR_SENSOR_MISSING` | Ein Sensor fehlt |
| 0x0002 | `STATUS_ERROR_WATER_TEMP_READ_FAIL` | Wassertemperatur konnte nicht gelesen werden |
| 0x0004 | `STATUS_ERROR_METER_READING_MISMATCH` | Interne Zählerwerte außerhalb des Erwartungsbereichs |
| 0x0008 | `STATUS_WARNING_FAN_RPM_MISMATCH` | Lüfterdrehzahl außerhalb des Erwartungsbereichs |
| 0x0010 | `STATUS_ERROR_BOARD_TEMP_EXCEEDED` | Board-Temperatur über zulässigem Bereich |
| 0x0020 | `STATUS_ERROR_BOARD_TEMP_READ_FAIL` | Board-Temperatur konnte nicht gelesen werden |
| 0x0040 | `STATUS_ERROR_METER_READ_FAIL` | Interner Zähler konnte nicht gelesen werden |
| 0x0080 | `STATUS_WARNING_HUB_DISCONNECTED` | Verbindung zum MQTT-Broker verloren |
| 0x0100 | `STATUS_ERROR_POWER_FREQ_MISMATCH` | Netzfrequenz außerhalb des Erwartungsbereichs |
| 0x0200 | `STATUS_ERROR_MISSING_SETTINGS` | Erwartete interne Einstellungen fehlen |
| 0x0400 | `STATUS_ERROR_STB_TRIPPED` | Sicherheits-Temperaturbegrenzer (STB) vermutlich ausgelöst |

## Einstellungen ändern (`<base_topic>/<topic_control>`, Standard `control`)

JSON-Format:

```json
{
  "<module>": [
    {"name": "<name>", "value": <value>}
  ]
}
```

Mehrere Settings im selben Modul können in einem Aufruf gesetzt werden.
**Der JSON-Key ist kleingeschrieben** (z.B. `sensor`), auch wenn die
Novolto-Doku die Module in Großbuchstaben nennt (`SENSOR`).

Jede Änderung wird auf dem Info-Topic quittiert:

```json
// Erfolg
{"serial":"...","unix_time":...,"ret":0}

// Fehler, Beispiel
{"serial":"...","unix_time":...,"ret":13,"s_err":"Module SENSOR: SPTW -> wrong type"}
```

dbus-novolto wertet diese Quittungen aktuell **nicht aus** — sie landen auf
demselben Topic wie das Info-Telegramm, werden aber mangels bekannter Felder
(`avp` etc.) von `_update()` stillschweigend ignoriert. Ein `ret != 0` fällt
nur auf, wenn man das Log (`tail -f .../current`) oder MQTT Explorer manuell
prüft.

### Relevante Settings (Auszug)

| Modul | Name | Typ | Beschreibung |
|---|---|---|---|
| CORE | `reboot` | bool | Neustart auslösen (nicht persistent) |
| OTA | `url` | string | URL für Firmware-Binary |
| OTA | `update` | bool | Firmware-Update auslösen (nicht persistent) |
| SIG | `aur_volume` | float | Lautstärke Signalton, 0.0 (stumm) – 1.0 (voll) |
| SENSOR | `sptw` | float | Sollwert Wassertemperatur °C |
| SENSOR | `sptwh` | float | Hysterese °C — Heizstab schaltet **aus** oberhalb `sptw + sptwh/2`, **ein** unterhalb `sptw - sptwh/2` |
| SENSOR | `spp` | float | Sollwert Leistung W (Annahme 230 V, reale Leistung kann abweichen) |

Eine vollständige Liste aller Settings liefert das Entwickler-Menü im
Novolto-Web-Config.

## Mögliche Erweiterungen (noch nicht umgesetzt)

- `st` als Alarm/Status im Victron abbilden (z.B. generischer Warn-Status
  oder Klartext-Log der gesetzten Bits)
- `ret`/`s_err`-Quittungen auswerten und bei Fehlern loggen, statt sie
  stillschweigend zu verwerfen
- `rssi` als Diagnoseinfo anzeigen (z.B. an `/Mgmt/Connection` anhängen)
- `rod_st`, `triacon`, `r1on`, `r2on` bleiben ungenutzt, da herstellerseitig
  nicht im Detail dokumentiert
