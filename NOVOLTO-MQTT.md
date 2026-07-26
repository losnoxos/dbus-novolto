# Novolto MQTT-Protokoll (Referenz)

Zusammenfassung der offiziellen Novolto-MQTT-Doku, ergänzt um die konkrete
Nutzung in [dbus-novolto.py](dbus-novolto.py). Dient als Nachschlagewerk,
falls weitere Felder/Einstellungen angebunden werden sollen.

## Info-Telegramm (`<base_topic>/<topic_info>`, Standard `info`)

Ein JSON-Objekt mit allen Messwerten, zyklisch alle `msi` Sekunden.
Sämtliche Anzeigen in Victron (Leistung, Temperaturen, Ein/Aus-Status)
sind dadurch nur so aktuell wie das letzte Telegramm — spürbare
Verzögerung ist normales Geräteverhalten, kein Bug in dbus-novolto.

| Feld | Typ | Bedeutung | Genutzt in dbus-novolto |
|---|---|---|---|
| `serial` | String | Seriennummer des Geräts | als `base_topic` in config.ini |
| `unix_time` | Integer | Unix-Timestamp der Messung | nein |
| `msi` | Integer | Messintervall in Sekunden | nein |
| `avt1` | Float | Board-/Elektroniktemperatur °C | ja, optional zweiter Temp.-Service (`enable_temperature2_service`) |
| `avtw` | Float | Ist-Wassertemperatur im Speicher °C | ja, Temperatur-Service "Novolto Speicher" |
| `sptw` | Float lt. Doku, **beim Setzen tatsächlich Float** ⚠️ | Sollwert Wassertemperatur °C (`sensor.sptw`) | ja, Feld "Max. Temperatur" |
| `sptwh` | Float lt. Doku, **beim Setzen tatsächlich Float** ⚠️ | Hysterese der Solltemperatur °C (`sensor.sptwh`) | ja, Feld "Hysterese" |
| `spp` | Float lt. Doku, **beim Setzen tatsächlich Integer** ⚠️ | Sollwert Leistung W (`sensor.spp`) | ja, Feld "Leistung" |
| `avv` | Float | Spannung V, Mittelwert über 5 s | ja, `/Ac/<Phase>/Voltage` |
| `avp` | Float | Ist-Leistung W, Mittelwert über 5 s | ja, `/Ac/Power`, Energiezähler, Anzeige im Feldnamen |
| `avi` | Float | Strom A, Mittelwert über 5 s | ja, `/Ac/<Phase>/Current` |
| `avf` | Float | Netzfrequenz Hz | ja, `/Ac/Frequency` |
| `rssi` | Integer | WLAN-Signalstärke | nein — Diagnosewert, aktuell nicht angezeigt |
| `st` | Integer | Bitflags Warnungen/Fehler, siehe unten | nein — aktuell nicht ausgewertet |
| `wel` | Float | Energie seit Geräte-Boot, kWh, **Schätzwert** | optional über `energy_source = wel` |
| `rod_st` | Integer | 0/1, sollte "Heizstab aktiv" bedeuten, erwies sich aber als unzuverlässig (siehe unten) | nein |
| `triacon`, `r1on`, `r2on` | — | laut Hersteller "miscellaneous diagnostic data", nicht weiter dokumentiert | nein |

⚠️ Die Typ-Spalte ist die von Novolto dokumentierte Bedeutung im
Info-Telegramm — welcher JSON-Typ beim **Setzen** über `<topic_control>`
tatsächlich akzeptiert wird, weicht bei `spp`/`sptw`/`sptwh` davon ab,
siehe "Real-World-Erkenntnis" weiter unten.

**`rod_st` real getestet, aber unzuverlässig (nicht in der Novolto-Doku
enthalten):** bei einem ersten Test schien `rod_st` exakt mit dem
Heizstatus zu korrelieren (Leerlauf `rod_st:0`/`avp:2.7 W`, Heizen bei
hoher Last `rod_st:1`/`avp:131 W`). Ein weiterer Test bei niedrigeren
Leistungsstufen (40 W Sollwert) zeigte aber: `rod_st` blieb auf `1`
hängen, obwohl `avp` wieder auf Leerlaufniveau (3–5 W) gefallen war —
vermutlich weil `rod_st` eher "Heizkreis aktiviert/angefordert" als
"gerade tatsächlich Strom fließt" abbildet. dbus-novolto verwendet daher
seit v0.14 `avp > HEATING_THRESHOLD_W` (15 W) statt `rod_st` für die
Ein/Aus-Statusanzeige. `triacon` ist zudem ein reiner Zähler (steigt
monoton, auch wenn `rod_st` wieder 0 ist) und taugt ebenfalls nicht als
Statusfeld.

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

**Real-World-Erkenntnis (v0.11):** Die Novolto-Doku nennt `spp`/`sptw`/
`sptwh` einheitlich als Typ `float` — real (per MQTT-Ack auf unserem
Gerätestand) verhält sich aber jedes Feld anders:

- `spp` verlangt **Integer** (`20` statt `20.0`) — Float wird mit
  `ret=13 "Module SENSOR: SPP -> wrong type"` abgelehnt.
- `sptw`/`sptwh` verlangen **Float** (`34.0` statt `34`) — Integer wird
  mit `ret=13 "Module SENSOR: SPTWH -> wrong type"` abgelehnt.

dbus-novolto sendet dementsprechend `spp` als Integer, `sptw`/`sptwh`
als Float. Nicht pauschal auf weitere Settings übertragen, ohne es
einzeln per Ack zu verifizieren.

Eine vollständige Liste aller Settings liefert das Entwickler-Menü im
Novolto-Web-Config.

## Mögliche Erweiterungen (noch nicht umgesetzt)

- `st` als Alarm/Status im Victron abbilden (z.B. generischer Warn-Status
  oder Klartext-Log der gesetzten Bits)
- `ret`/`s_err`-Quittungen auswerten und bei Fehlern loggen, statt sie
  stillschweigend zu verwerfen
- `rssi` als Diagnoseinfo anzeigen (z.B. an `/Mgmt/Connection` anhängen)
- `triacon`, `r1on`, `r2on` bleiben ungenutzt, da herstellerseitig nicht
  im Detail dokumentiert und (bei `triacon`) als reiner Zähler ungeeignet
  fürs Switch Pane
