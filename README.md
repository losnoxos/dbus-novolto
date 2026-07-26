# dbus-novolto

Venus OS Treiber (Victron Cerbo GX) für den Novolto Heizstab (P2300/P3000)
via lokalem MQTT — Anzeige, Ein/Aus, manuelle Leistungsvorgabe und
einstellbare Max. Wassertemperatur über die SwitchableOutput-API.

## Was erscheint im Victron

- **Geräteliste / VRM:** "Novolto Heizstab" als AC-Last mit Ist-Leistung (W),
  Energiezähler (kWh, persistent über Neustarts) und Spannung/Strom je Phase
- **Switch Pane (GUI v2 / Remote Console / VRM):** Gruppe "Novolto" mit
  - Toggle **Ein/Aus**
  - Numerisches Eingabefeld **Leistung** 0–3000 W in 20-W-Schritten (zeigt
    live die Ist-Leistung im Feldnamen an)
  - Numerisches Eingabefeld **Max. Temperatur** (Sollwassertemperatur)
  - Numerisches Eingabefeld **Hysterese** (Heizstab schaltet aus oberhalb
    `sptw + Hysterese/2`, wieder ein unterhalb `sptw - Hysterese/2`,
    `enable_sptwh_control`)
- **Temperatursensor** "Novolto Speicher" (avtw), optional ein zweiter
  Sensor "Novolto Elektronik" (avt1), beide mit VRM-Historie

## Funktionsweise

Der Novolto publiziert ein einzelnes JSON-Telegramm auf `<base_topic>/info`
mit allen Messwerten (Leistung, Spannung, Temperaturen, Sollwert, ...).
Steuerbefehle gehen als JSON auf `<base_topic>/control`, z.B.
`{"sensor":[{"name":"spp","value":500.0}]}` für eine Leistungsvorgabe.
Alle Topic-Namen und das Feld für die Sollwert-Rückmeldung sind in
`config.ini` anpassbar. Vollständige Feld- und Protokollreferenz siehe
[NOVOLTO-MQTT.md](NOVOLTO-MQTT.md).

## Installation

1. Ordner auf den Cerbo kopieren (z.B. per scp nach /data/tmp):
   `scp -r dbus-novolto root@<cerbo-ip>:/data/tmp/`
2. `config.ini` aus `config.ini.example` erstellen und anpassen — mindestens
   `host`, `username`, `password` und `base_topic` (Serial-Prefix des
   Heizstabs, im MQTT-Explorer sichtbar, z.B. `141.142.9FFED8`).
3. `sh /data/tmp/dbus-novolto/install.sh`

Der Installer legt alles nach `/data/dbus-novolto`, registriert den
daemontools-Service und trägt den Symlink in `/data/rc.local` ein
(überlebt Venus-OS-Updates).

Neustart des Treibers: `svc -t /service/dbus-novolto`
Log: `tail -f /var/log/dbus-novolto/current | tai64nlocal`

## Verhalten

- Schalter AUS → `spp = 0` wird publiziert, letzter Sollwert bleibt für
  das Wiedereinschalten gemerkt (`setpoint_memory`).
- Eingaben werden auf das konfigurierte Watt-Raster (`power_step`)
  gerundet und nur bei eingeschaltetem Toggle gesendet.
- sptw/spp werden bewusst als Float gesendet (34.0 statt 34) — die
  Firmware lehnt Integer-Werte mit `ret=13 "wrong type"` ab.
- Externe Sollwert-Änderungen (App/Home Assistant) ziehen Slider/Toggle
  automatisch nach, außer kurz nach einem eigenen Publish
  (Echo-Unterdrückung, 10 s).
- Keine MQTT-Daten für `timeout_seconds` → Gerät geht auf "Disconnected".
- Energiezähler wird aus der Ist-Leistung integriert und alle 5 Minuten
  nach `/data/dbus-novolto/energy.json` persistiert (übersteht Neustarts).

## Anpassen / Prüfen

- Phase (`phase`) und Systemposition (`position`: ac_in/ac_out/ac_in_2)
  in config.ini an die tatsächliche Verkabelung anpassen.
- `enable_sptw_control`, `enable_sptwh_control`, `enable_temperature2_service`
  je nach Bedarf ein-/ausschalten, falls der Novolto diese Werte nicht liefert.
- Später auf Cerbo-eigenen Broker umziehen: am Cerbo *MQTT on LAN
  (plaintext)* aktivieren, Novolto auf die Cerbo-IP zeigen lassen,
  in config.ini `host = 127.0.0.1` und Zugangsdaten leeren.
