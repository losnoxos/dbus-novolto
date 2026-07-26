#!/bin/sh
# Installation von dbus-novolto auf Venus OS (als root auf dem GX ausfuehren)
set -e
SRC=$(dirname "$(readlink -f "$0")")
DEST=/data/dbus-novolto

echo ">> Kopiere nach $DEST"
mkdir -p "$DEST"
cp -r "$SRC/dbus-novolto.py" "$SRC/service" "$DEST/"
[ -f "$DEST/config.ini" ] || cp "$SRC/config.ini" "$DEST/"
chmod 755 "$DEST/dbus-novolto.py" "$DEST/service/run" "$DEST/service/log/run"
# config.ini enthaelt ggf. ein Klartext-MQTT-Passwort -- nicht world-readable
chmod 600 "$DEST/config.ini"

echo ">> Pruefe paho-mqtt"
python3 -c "import paho.mqtt.client" 2>/dev/null || {
  echo "   installiere python3-paho-mqtt..."
  opkg update && opkg install python3-paho-mqtt
}

echo ">> Registriere Service"
ln -sfn "$DEST/service" /service/dbus-novolto

echo ">> rc.local Eintrag (update-fest)"
RCLOCAL=/data/rc.local
LINE='ln -sfn /data/dbus-novolto/service /service/dbus-novolto'
[ -f "$RCLOCAL" ] || { echo '#!/bin/sh' > "$RCLOCAL"; chmod 755 "$RCLOCAL"; }
grep -qF "$LINE" "$RCLOCAL" || echo "$LINE" >> "$RCLOCAL"

echo ">> Fertig. Vorher config.ini anpassen: $DEST/config.ini"
echo "   (config.ini.example im Projektordner als Vorlage nehmen, falls"
echo "   noch keine config.ini existiert)"
echo "   Start/Neustart:  svc -t /service/dbus-novolto"
echo "   Log:             tail -f /var/log/dbus-novolto/current | tai64nlocal"
