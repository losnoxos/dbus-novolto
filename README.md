# dbus-novolto

Venus OS Treiber (Victron Cerbo GX) für den Novolto Heizstab (P2300/P3000)
via lokalem MQTT — Anzeige, manuelle Leistungsvorgabe und einstellbare
Max. Wassertemperatur über die SwitchableOutput-API.

## Was erscheint im Victron

- **Geräteliste / VRM:** "Novolto Heizstab" als AC-Last mit Ist-Leistung (W),
  Energiezähler (kWh, persistent über Neustarts) und Spannung/Strom je Phase
- **Switch Pane (GUI v2 / Remote Console / VRM):** Gruppe "Novolto" mit
  - **Ein/Aus** als reine Statusanzeige (nicht schaltbar!) — zeigt, ob der
    Heizstab gerade tatsächlich heizt (`avp` über einem Schwellwert,
    `HEATING_THRESHOLD_W`). Der Novolto kennt kein echtes An/Aus,
    Steuerung läuft über das Leistungsfeld.
  - Numerisches Eingabefeld **Leistung** 0–3000 W in 20-W-Schritten (zeigt
    live die Ist-Leistung im Feldnamen an) — `0 W` = aus
  - Numerisches Eingabefeld **Max. Temperatur** (Sollwassertemperatur)
  - Numerisches Eingabefeld **Hysterese** (Heizstab schaltet aus oberhalb
    `sptw + Hysterese/2`, wieder ein unterhalb `sptw - Hysterese/2`,
    `enable_sptwh_control`)
- **Temperatursensor** "Novolto Speicher" (avtw, `enable_temperature_service`),
  optional ein zweiter Sensor "Novolto Elektronik" (avt1,
  `enable_temperature2_service`) — beide unabhängig voneinander
  abschaltbar, beide mit VRM-Historie

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
Deinstallieren: `sh /data/dbus-novolto/uninstall.sh` (entfernt Service,
rc.local-Eintrag und `/data/dbus-novolto` restlos)

## Verhalten

- Es gibt kein echtes An/Aus am Novolto — `0 W` Leistungsvorgabe *ist*
  "aus". Die Ein/Aus-Anzeige im Switch Pane ist reiner Status, abgeleitet
  aus `avp` (Ist-Leistung über `HEATING_THRESHOLD_W`, 15 W), nicht
  schaltbar. `rod_st` wäre naheliegender gewesen, erwies sich im Test
  aber als unzuverlässig (blieb bei niedrigen Leistungsstufen auf 1
  hängen, siehe NOVOLTO-MQTT.md).
- Eingaben im Leistungsfeld werden auf das konfigurierte Watt-Raster
  (`power_step`) gerundet und sofort published.
- `spp` wird bewusst als Integer gesendet (20 statt 20.0) — die
  Firmware lehnt Float mit `ret=13 "Module SENSOR: SPP -> wrong type"`
  ab. `sptw`/`sptwh` verhalten sich umgekehrt: dort wird bewusst Float
  gesendet (34.0 statt 34), Integer wird mit `ret=13 "wrong type"`
  abgelehnt. Beides real per MQTT-Ack bestätigt (Stand v0.11) — jedes
  Feld hat seinen eigenen, nicht pauschal übertragbaren Typ.
- Externe Sollwert-Änderungen (App/Home Assistant) ziehen den
  Leistungs-Slider automatisch nach, außer kurz nach einem eigenen
  Publish (Echo-Unterdrückung, 10 s). Die Ein/Aus-Statusanzeige
  aktualisiert sich unabhängig davon direkt aus `avp`.
- Alle Anzeigen (Leistung, Temperaturen, Ein/Aus-Status, ...)
  aktualisieren sich nur so schnell, wie der Novolto selbst sein
  Info-Telegramm sendet (`msi`-Feld, siehe NOVOLTO-MQTT.md). Das kann
  spürbar träge wirken — das ist kein Bug in dbus-novolto, sondern das
  Sendeintervall des Geräts.
- Keine MQTT-Daten für `timeout_seconds` (Standard 120 s) → Gerät geht
  auf "Disconnected", eine einzelne Log-Zeile beim Verlust und eine
  beim Wiederkommen (keine Wiederholung).
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

## Verwandtes Projekt

[victronenergy.heatpump.novolto](https://github.com/losnoxos/victronenergy.heatpump.novolto)
ist ein experimenteller Fork, der den nativen `com.victronenergy.heatpump`-
Gerätetyp aus der Venus-OS-Beta testet (Pendant zu `com.victronenergy.evcharger`
für Wallboxen). Braucht Venus OS Beta, bringt aktuell (Stand der Tests dort)
noch keinen sichtbaren GUI-Vorteil gegenüber diesem Repo hier.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
