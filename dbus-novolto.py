#!/usr/bin/env python3
"""
dbus-novolto v0.7
=================
Venus OS Treiber fuer den Novolto Heizstab via lokalem MQTT.

Aenderungen:
  v0.7  Fix: sptw und spp werden als Float published (34.0 statt 34).
        Die Firmware lehnt Integer-Werte mit ret=13 "wrong type" ab,
        wodurch der Sollwert nicht uebernommen wurde.
  v0.6  Max. Wassertemperatur (sptw) als einstellbares Feld im Switch
        Pane (enable_sptw_control). Phase (L1/L2/L3) und Position
        (AC-In/Out) konfigurierbar. Optionaler zweiter Temperatursensor
        fuer avt1 (enable_temperature2_service).
  v0.5  Ist-Leistung (avp) wird live im Namen des Leistungs-Felds
        angezeigt (show_power_in_switch), Aufloesung 10 W.
  v0.4  Toggle AUS setzt Leistungsanzeige auf 0; letzter Wert wird
        gemerkt und bei EIN wiederhergestellt. Wassertemperatur wird
        live im Schalternamen angezeigt (show_temp_in_switch).
  v0.3  Leistungsvorgabe als Numeric-Input-Popup (Typ 8) statt Slider;
        Ruecksync ueberschreibt vorgemerkte Werte nicht mehr.
  v0.2  Umstellung auf reales Telegramm: ein JSON auf <serial>/info,
        avp als Ist-Leistung, private dbus-Verbindung pro Service.

Der Novolto publiziert ein JSON-Telegramm auf <serial>/info, z.B.:
  {"serial":"130.140.1D0978","unix_time":...,"msi":5,"avt1":35.48,
   "avtw":25.50,"spp":0,"sptw":33.00,"sptwh":5.00,"st":0,"rod_st":0,
   "triacon":4,"r1on":0,"r2on":0,"avv":231.99,"avi":0.01,"avp":2.66,
   "avf":50.00,"wel":0.00,"rssi":0}

Feldnutzung:
  avp  -> /Ac/Power (gemessene Ist-Leistung)
  avv  -> /Ac/L1/Voltage
  avi  -> /Ac/L1/Current
  avtw -> Temperatur-Service (Speicher)
  spp  -> aktueller Sollwert (Anzeige Slider-Rueckmeldung)
  wel  -> Energiezaehler des Geraets (falls nutzbar), sonst Integration

Registriert:
  - com.victronenergy.acload.novolto (+ SwitchableOutput 0/1)
  - com.victronenergy.temperature.novolto (optional)
"""

import sys
import os
import json
import time
import logging
import configparser

sys.path.insert(1, '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python')

from gi.repository import GLib  # noqa: E402
import dbus  # noqa: E402
from dbus.mainloop.glib import DBusGMainLoop  # noqa: E402
from vedbus import VeDbusService  # noqa: E402

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.stderr.write(
        "paho-mqtt fehlt. Auf dem GX installieren mit:\n"
        "  opkg update && opkg install python3-paho-mqtt\n")
    sys.exit(1)

log = logging.getLogger("dbus-novolto")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = "/data/dbus-novolto"
ENERGY_FILE = os.path.join(DATA_DIR, "energy.json")

TYPE_TOGGLE = 1
TYPE_BASIC_SLIDER = 7
TYPE_NUMERIC_INPUT = 8


class Config:
    def __init__(self, path):
        cp = configparser.ConfigParser()
        if not cp.read(path):
            raise SystemExit("config.ini nicht gefunden: %s" % path)
        m = cp["mqtt"]
        self.host = m.get("host")
        self.port = m.getint("port", 1883)
        self.user = m.get("username", fallback="") or None
        self.password = m.get("password", fallback="") or None
        self.base = m.get("base_topic").rstrip("/")
        self.t_info = m.get("topic_info", "info")
        self.t_control = m.get("topic_control", "control")
        self.ctrl_sensor_name = m.get("control_sensor_name", "spp")

        d = cp["device"]
        self.name = d.get("name", "Novolto Heizstab")
        self.instance_acload = d.getint("deviceinstance_acload", 40)
        self.instance_temp = d.getint("deviceinstance_temperature", 41)
        self.max_power = d.getint("max_power", 3000)
        self.step = d.getint("power_step", 20)
        self.timeout = d.getint("timeout_seconds", 120)
        self.enable_temp = d.getboolean("enable_temperature_service", True)
        self.resend_seconds = d.getint("resend_setpoint_seconds", 0)
        # energy_source: integrate | wel
        self.energy_source = d.get("energy_source", "integrate").lower()
        self.show_temp_in_switch = d.getboolean(
            "show_temp_in_switch", fallback=True)
        self.show_power_in_switch = d.getboolean(
            "show_power_in_switch", fallback=True)
        self.phase = d.get("phase", fallback="L1").upper()
        if self.phase not in ("L1", "L2", "L3"):
            self.phase = "L1"
        pos = d.get("position", fallback="ac_out").lower()
        self.position = {"ac_in": 0, "ac_in_1": 0,
                         "ac_out": 1, "ac_in_2": 2}.get(pos, 1)
        self.enable_sptw = d.getboolean(
            "enable_sptw_control", fallback=True)
        self.sptw_min = d.getint("sptw_min", fallback=20)
        self.sptw_max = d.getint("sptw_max", fallback=75)
        self.enable_temp2 = d.getboolean(
            "enable_temperature2_service", fallback=False)
        self.instance_temp2 = d.getint(
            "deviceinstance_temperature2", fallback=42)


class EnergyCounter:
    """Integriert avp zu kWh und persistiert nach /data."""

    def __init__(self):
        self.kwh = 0.0
        self._last_t = None
        self._last_p = 0.0
        self._dirty = False
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(ENERGY_FILE) as f:
                self.kwh = float(json.load(f).get("kwh", 0.0))
        except (OSError, ValueError):
            pass

    def update(self, power_w):
        now = time.monotonic()
        if self._last_t is not None:
            dt = now - self._last_t
            if 0 < dt < 3600:
                self.kwh += self._last_p * dt / 3600.0 / 1000.0
                self._dirty = True
        self._last_t = now
        self._last_p = max(power_w, 0.0)

    def persist(self):
        if not self._dirty:
            return
        try:
            tmp = ENERGY_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"kwh": round(self.kwh, 4)}, f)
            os.replace(tmp, ENERGY_FILE)
            self._dirty = False
        except OSError as e:
            log.warning("Energiezaehler nicht gespeichert: %s", e)


class NovoltoDriver:
    def __init__(self, cfg):
        self.cfg = cfg
        self.energy = EnergyCounter()
        self.last_msg = 0.0
        self.switch_state = 0
        self.setpoint = 0
        self.setpoint_memory = 0
        self._last_name_temp = None
        self._last_name_power = None
        self.sptw = None
        self._suppress_sptw = 0.0
        self._suppress_echo = 0.0

        self._init_dbus()
        self._init_mqtt()

        GLib.timeout_add_seconds(5, self._watchdog)
        GLib.timeout_add_seconds(300, lambda: (self.energy.persist(), True)[1])
        if cfg.resend_seconds > 0:
            GLib.timeout_add_seconds(cfg.resend_seconds, self._resend)

    # ------------------------------------------------------------------ dbus
    def _init_dbus(self):
        cfg = self.cfg

        def make_service(name):
            # Jeder Service braucht eine eigene private dbus-Verbindung,
            # sonst: KeyError "handler for '/' already registered"
            bus = dbus.SystemBus(private=True)
            try:
                return VeDbusService(name, bus, register=False)
            except TypeError:
                return VeDbusService(name, bus)

        s = make_service("com.victronenergy.acload.novolto")
        self.svc = s

        s.add_path("/Mgmt/ProcessName", "dbus-novolto")
        s.add_path("/Mgmt/ProcessVersion", "0.7")
        s.add_path("/Mgmt/Connection", "MQTT %s:%d" % (cfg.host, cfg.port))
        s.add_path("/DeviceInstance", cfg.instance_acload)
        s.add_path("/ProductId", 0xFFFF)
        s.add_path("/ProductName", cfg.name)
        s.add_path("/CustomName", cfg.name, writeable=True)
        s.add_path("/Serial", cfg.base)
        s.add_path("/Connected", 0)

        s.add_path("/Ac/Power", None, gettextcallback=self._fmt("%.0f W"))
        for ph in ("L1", "L2", "L3"):
            s.add_path("/Ac/%s/Power" % ph, None,
                       gettextcallback=self._fmt("%.0f W"))
            s.add_path("/Ac/%s/Voltage" % ph, None,
                       gettextcallback=self._fmt("%.1f V"))
            s.add_path("/Ac/%s/Current" % ph, None,
                       gettextcallback=self._fmt("%.2f A"))
        s.add_path("/Ac/Frequency", None, gettextcallback=self._fmt("%.1f Hz"))
        s.add_path("/Position", cfg.position, writeable=True)
        s.add_path("/Ac/Energy/Forward", round(self.energy.kwh, 3),
                   gettextcallback=self._fmt("%.2f kWh"))

        p = "/SwitchableOutput/0/"
        s.add_path(p + "Name", "Heizstab")
        s.add_path(p + "Status", 0)
        s.add_path(p + "State", 0, writeable=True,
                   onchangecallback=self._on_state_changed)
        s.add_path(p + "Settings/CustomName", "Heizstab Ein/Aus",
                   writeable=True)
        s.add_path(p + "Settings/Group", "Novolto", writeable=True)
        s.add_path(p + "Settings/Type", TYPE_TOGGLE, writeable=True)
        s.add_path(p + "Settings/ValidTypes", 1 << TYPE_TOGGLE)
        s.add_path(p + "Settings/ShowUIControl", 1, writeable=True)

        p = "/SwitchableOutput/1/"
        s.add_path(p + "Name", "Leistung")
        s.add_path(p + "Status", 0)
        s.add_path(p + "State", 1, writeable=True)
        s.add_path(p + "Dimming", 0, writeable=True,
                   onchangecallback=self._on_dimming_changed)
        s.add_path(p + "Settings/CustomName", "Heizstab Leistung",
                   writeable=True)
        s.add_path(p + "Settings/Group", "Novolto", writeable=True)
        s.add_path(p + "Settings/Type", TYPE_NUMERIC_INPUT, writeable=True)
        s.add_path(p + "Settings/ValidTypes",
                   (1 << TYPE_NUMERIC_INPUT) | (1 << TYPE_BASIC_SLIDER))
        s.add_path(p + "Settings/DimmingMin", 0)
        s.add_path(p + "Settings/DimmingMax", cfg.max_power)
        s.add_path(p + "Settings/StepSize", cfg.step)
        s.add_path(p + "Settings/Decimals", 0)
        s.add_path(p + "Settings/Unit", "W")
        s.add_path(p + "Settings/ShowUIControl", 1, writeable=True)

        if cfg.enable_sptw:
            p = "/SwitchableOutput/2/"
            s.add_path(p + "Name", "Max. Temperatur")
            s.add_path(p + "Status", 0)
            s.add_path(p + "State", 1, writeable=True)
            s.add_path(p + "Dimming", None, writeable=True,
                       onchangecallback=self._on_sptw_changed)
            s.add_path(p + "Settings/CustomName", "Max. Wassertemperatur",
                       writeable=True)
            s.add_path(p + "Settings/Group", "Novolto", writeable=True)
            s.add_path(p + "Settings/Type", TYPE_NUMERIC_INPUT,
                       writeable=True)
            s.add_path(p + "Settings/ValidTypes", 1 << TYPE_NUMERIC_INPUT)
            s.add_path(p + "Settings/DimmingMin", cfg.sptw_min)
            s.add_path(p + "Settings/DimmingMax", cfg.sptw_max)
            s.add_path(p + "Settings/StepSize", 1)
            s.add_path(p + "Settings/Decimals", 0)
            s.add_path(p + "Settings/Unit", "°C")
            s.add_path(p + "Settings/ShowUIControl", 1, writeable=True)

        if hasattr(s, "register"):
            try:
                s.register()
            except Exception:
                pass

        self.tsvc = None
        if cfg.enable_temp:
            t = make_service("com.victronenergy.temperature.novolto")
            t.add_path("/Mgmt/ProcessName", "dbus-novolto")
            t.add_path("/Mgmt/ProcessVersion", "0.7")
            t.add_path("/Mgmt/Connection", "MQTT %s:%d" % (cfg.host, cfg.port))
            t.add_path("/DeviceInstance", cfg.instance_temp)
            t.add_path("/ProductId", 0xFFFF)
            t.add_path("/ProductName", cfg.name + " Speicher")
            t.add_path("/CustomName", cfg.name + " Speicher", writeable=True)
            t.add_path("/Connected", 0)
            t.add_path("/Temperature", None,
                       gettextcallback=self._fmt("%.1f C"))
            t.add_path("/TemperatureType", 2, writeable=True)
            t.add_path("/Status", 0)
            if hasattr(t, "register"):
                try:
                    t.register()
                except Exception:
                    pass
            self.tsvc = t

        self.t2svc = None
        if cfg.enable_temp2:
            t2 = make_service("com.victronenergy.temperature.novolto2")
            t2.add_path("/Mgmt/ProcessName", "dbus-novolto")
            t2.add_path("/Mgmt/ProcessVersion", "0.7")
            t2.add_path("/Mgmt/Connection",
                        "MQTT %s:%d" % (cfg.host, cfg.port))
            t2.add_path("/DeviceInstance", cfg.instance_temp2)
            t2.add_path("/ProductId", 0xFFFF)
            t2.add_path("/ProductName", cfg.name + " Elektronik")
            t2.add_path("/CustomName", cfg.name + " Elektronik",
                        writeable=True)
            t2.add_path("/Connected", 0)
            t2.add_path("/Temperature", None,
                        gettextcallback=self._fmt("%.1f C"))
            t2.add_path("/TemperatureType", 2, writeable=True)
            t2.add_path("/Status", 0)
            if hasattr(t2, "register"):
                try:
                    t2.register()
                except Exception:
                    pass
            self.t2svc = t2

    @staticmethod
    def _fmt(fmt):
        return lambda path, value: fmt % value

    # ------------------------------------------------------ dbus callbacks
    def _on_state_changed(self, path, value):
        value = int(value)
        if value not in (0, 1):
            return False
        self.switch_state = value
        self.svc["/SwitchableOutput/0/Status"] = 9 if value else 0
        if value:
            sp = self.setpoint_memory if self.setpoint_memory > 0 \
                else self.cfg.step
            self.setpoint = sp
            self.svc["/SwitchableOutput/1/Dimming"] = sp
            self._publish_setpoint(sp)
        else:
            self.setpoint = 0
            self.svc["/SwitchableOutput/1/Dimming"] = 0
            self._publish_setpoint(0)
        log.info("Schalter -> %s", "EIN" if value else "AUS")
        return True

    def _on_dimming_changed(self, path, value):
        try:
            value = int(round(float(value)))
        except (TypeError, ValueError):
            return False
        value = max(0, min(self.cfg.max_power, value))
        value = int(round(value / self.cfg.step)) * self.cfg.step
        self.setpoint = value
        if value > 0:
            self.setpoint_memory = value
        if self.switch_state:
            self._publish_setpoint(value)
            if value == 0:
                self.switch_state = 0
                self.svc["/SwitchableOutput/0/State"] = 0
                self.svc["/SwitchableOutput/0/Status"] = 0
        log.info("Sollwert -> %d W%s", value,
                 "" if self.switch_state or value == 0
                 else " (Schalter aus, vorgemerkt)")
        return True

    def _on_sptw_changed(self, path, value):
        try:
            value = int(round(float(value)))
        except (TypeError, ValueError):
            return False
        value = max(self.cfg.sptw_min, min(self.cfg.sptw_max, value))
        self.sptw = value
        # Firmware verlangt Float ("Module SENSOR: SPTW -> wrong type"
        # bei Integer, ret=13) -> immer mit Dezimalstelle senden (34.0)
        payload = json.dumps(
            {"sensor": [{"name": "sptw", "value": float(value)}]})
        t = "%s/%s" % (self.cfg.base, self.cfg.t_control)
        self.mqtt.publish(t, payload)
        self._suppress_sptw = time.monotonic() + 10
        log.info("Max. Wassertemperatur -> %d C (publish %s)", value, t)
        return True

    # ------------------------------------------------------------------ mqtt
    def _init_mqtt(self):
        cfg = self.cfg
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                 client_id="dbus-novolto")
        except AttributeError:
            client = mqtt.Client(client_id="dbus-novolto")
        if cfg.user:
            client.username_pw_set(cfg.user, cfg.password)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=2, max_delay=60)
        self.mqtt = client
        client.connect_async(cfg.host, cfg.port, keepalive=60)
        client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        t = "%s/%s" % (self.cfg.base, self.cfg.t_info)
        log.info("MQTT verbunden (%s:%d), subscribe %s",
                 self.cfg.host, self.cfg.port, t)
        client.subscribe(t)

    def _on_disconnect(self, client, userdata, *args):
        log.warning("MQTT getrennt, reconnect laeuft")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8", errors="ignore"))
        except ValueError:
            log.warning("Kein JSON auf %s: %r", msg.topic, msg.payload[:120])
            return
        if isinstance(data, dict):
            GLib.idle_add(self._update, data)

    def _publish_setpoint(self, watts):
        payload = json.dumps(
            {"sensor": [{"name": self.cfg.ctrl_sensor_name,
                         "value": float(int(watts))}]})
        t = "%s/%s" % (self.cfg.base, self.cfg.t_control)
        self.mqtt.publish(t, payload)
        self._suppress_echo = time.monotonic() + 10
        log.info("publish %s %s", t, payload)

    # ------------------------------------------------- GLib thread context
    def _update(self, d):
        self.last_msg = time.monotonic()
        s = self.svc
        s["/Connected"] = 1

        power = d.get("avp")
        if power is not None:
            power = float(power)
            self.energy.update(power)
            s["/Ac/Power"] = power
            s["/Ac/%s/Power" % self.cfg.phase] = power
            if self.cfg.show_power_in_switch:
                shown = int(round(power / 10.0)) * 10
                if shown != self._last_name_power:
                    self._last_name_power = shown
                    s["/SwitchableOutput/1/Settings/CustomName"] = \
                        "Leistung · Ist: %d W" % shown
        if "avv" in d:
            s["/Ac/%s/Voltage" % self.cfg.phase] = float(d["avv"])
        if "avi" in d:
            s["/Ac/%s/Current" % self.cfg.phase] = float(d["avi"])
        if "avf" in d:
            s["/Ac/Frequency"] = float(d["avf"])

        if self.cfg.energy_source == "wel" and "wel" in d:
            s["/Ac/Energy/Forward"] = round(float(d["wel"]), 3)
        else:
            s["/Ac/Energy/Forward"] = round(self.energy.kwh, 3)

        # Sollwert-Rueckmeldung vom Geraet -> Slider/Toggle synchron halten,
        # ausser wir haben gerade selbst gesendet (Echo-Unterdrueckung)
        if "spp" in d and time.monotonic() > self._suppress_echo:
            spp = int(float(d["spp"]))
            if spp > 0:
                # extern gesetzter Sollwert (App/HA) -> GUI nachziehen
                self.setpoint_memory = spp
                if spp != self.setpoint:
                    self.setpoint = spp
                    s["/SwitchableOutput/1/Dimming"] = spp
                if self.switch_state != 1:
                    self.switch_state = 1
                    s["/SwitchableOutput/0/State"] = 1
                    s["/SwitchableOutput/0/Status"] = 9
            else:
                # Stab aus -> Toggle und Anzeige auf 0,
                # letzter Wert bleibt im Gedaechtnis fuer Wiedereinschalten
                if self.switch_state != 0:
                    self.switch_state = 0
                    s["/SwitchableOutput/0/State"] = 0
                    s["/SwitchableOutput/0/Status"] = 0
                if self.setpoint != 0:
                    self.setpoint = 0
                    s["/SwitchableOutput/1/Dimming"] = 0

        if self.cfg.enable_sptw and "sptw" in d \
                and time.monotonic() > self._suppress_sptw:
            sptw = int(float(d["sptw"]))
            if sptw != self.sptw:
                self.sptw = sptw
                s["/SwitchableOutput/2/Dimming"] = sptw

        if self.t2svc and "avt1" in d:
            self.t2svc["/Connected"] = 1
            self.t2svc["/Temperature"] = round(float(d["avt1"]), 1)

        if "avtw" in d:
            temp = round(float(d["avtw"]), 1)
            if self.tsvc:
                self.tsvc["/Connected"] = 1
                self.tsvc["/Temperature"] = temp
            if self.cfg.show_temp_in_switch and temp != self._last_name_temp:
                self._last_name_temp = temp
                s["/SwitchableOutput/0/Settings/CustomName"] = \
                    "Heizstab · %.1f °C" % temp
        return False

    def _watchdog(self):
        if self.last_msg and \
           time.monotonic() - self.last_msg > self.cfg.timeout:
            s = self.svc
            s["/Connected"] = 0
            s["/Ac/Power"] = None
            s["/Ac/Frequency"] = None
            for ph in ("L1", "L2", "L3"):
                for k in ("Power", "Voltage", "Current"):
                    s["/Ac/%s/%s" % (ph, k)] = None
            if self.tsvc:
                self.tsvc["/Connected"] = 0
                self.tsvc["/Temperature"] = None
            if self.t2svc:
                self.t2svc["/Connected"] = 0
                self.t2svc["/Temperature"] = None
        return True

    def _resend(self):
        if self.switch_state and self.setpoint > 0:
            self._publish_setpoint(self.setpoint)
        return True


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = Config(os.path.join(HERE, "config.ini"))
    DBusGMainLoop(set_as_default=True)
    driver = NovoltoDriver(cfg)
    log.info("dbus-novolto gestartet, base_topic=%s", cfg.base)
    mainloop = GLib.MainLoop()
    try:
        mainloop.run()
    finally:
        driver.energy.persist()


if __name__ == "__main__":
    main()
