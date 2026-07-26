#!/bin/sh
# Deinstallation von dbus-novolto auf Venus OS (als root auf dem GX)
# Entfernt Service, rc.local-Eintrag und /data/dbus-novolto komplett.
set -e
DEST=/data/dbus-novolto
SVC=/service/dbus-novolto
RCLOCAL=/data/rc.local

echo ">> Stoppe Service"
[ -e "$SVC" ] && svc -d "$SVC" 2>/dev/null || true

echo ">> Entferne Service-Symlink"
rm -f "$SVC"

echo ">> Entferne rc.local-Eintrag"
if [ -f "$RCLOCAL" ]; then
  grep -v "dbus-novolto" "$RCLOCAL" > "$RCLOCAL.tmp" || true
  mv "$RCLOCAL.tmp" "$RCLOCAL"
  chmod 755 "$RCLOCAL"
fi

echo ">> Entferne $DEST"
rm -rf "$DEST"

echo ">> Fertig. dbus-novolto ist deinstalliert."
