import subprocess
import json
import time
import asyncio
import math
import sys
import shutil
import urllib.request
from pathlib import Path

DEFAULT_CONFIG_DIR = Path.home() / ".emergency_mesh"

def validate_coordinates(lat, lon):
    """
    Validates if lat and lon are valid numeric coordinates and not Null Island (0, 0).
    """
    try:
        lat = float(lat)
        lon = float(lon)
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            # Reject exact (0, 0) as it usually indicates uninitialized GPS fix
            if lat == 0.0 and lon == 0.0:
                return False
            return True
    except (ValueError, TypeError):
        pass
    return False

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculates great circle distance between two (lat, lon) coordinates in meters.
    Returns float distance in meters, or None if coordinates are invalid/UNKNOWN.
    """
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except (ValueError, TypeError):
        return None

    R = 6371000.0  # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c

def trigger_vibration(duration_ms=1500):
    """
    Triggers physical device vibration using `termux-vibrate` via subprocess.
    Fails gracefully if Termux:API is not installed or running on desktop.
    """
    if not shutil.which("termux-vibrate"):
        return False
    try:
        subprocess.Popen(
            ["termux-vibrate", "-d", str(duration_ms)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception:
        return False

def trigger_sos_alarm(duration_ms=2000, alert_text="Emergency SOS Alert Received"):
    """
    Triggers physical device vibration AND sound alarms on peer device:
    1. Terminal audio chime bell (\a).
    2. Physical vibration via termux-vibrate.
    3. High-priority Android notification with sound via termux-notification.
    4. Text-To-Speech audio alert via termux-tts-speak.
    """
    # 1. Terminal audio bell chime
    try:
        sys.stdout.write("\a\a\a")
        sys.stdout.flush()
    except Exception:
        pass

    # 2. Physical Vibration
    trigger_vibration(duration_ms)

    # 3. Android Notification Sound Alert
    if shutil.which("termux-notification"):
        try:
            subprocess.Popen(
                ["termux-notification", "--sound", "--title", "🚨 EMERGENCY SOS ALERT", "--content", str(alert_text), "--priority", "high"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

    # 4. Text-To-Speech Audio Voice Alert
    if shutil.which("termux-tts-speak"):
        try:
            subprocess.Popen(
                ["termux-tts-speak", "Emergency S O S alert received!"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass

class LocationManager:
    def __init__(self, config_dir=None):
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.persistence_file = self.config_dir / "location.json"

        self.cached_location = None
        self.manual_override = None
        self.update_task = None
        self.running = False

        self.load_persisted()

    def set_config_dir(self, config_dir):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.persistence_file = self.config_dir / "location.json"
        self.load_persisted()

    def load_persisted(self):
        if self.persistence_file.exists():
            try:
                with open(self.persistence_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("manual_override") and validate_coordinates(
                        data["manual_override"].get("latitude"),
                        data["manual_override"].get("longitude")
                    ):
                        self.manual_override = data["manual_override"]

                    if data.get("cached_location") and validate_coordinates(
                        data["cached_location"].get("latitude"),
                        data["cached_location"].get("longitude")
                    ):
                        self.cached_location = data["cached_location"]
            except Exception:
                pass

    def save_persisted(self):
        try:
            data = {
                "manual_override": self.manual_override,
                "cached_location": self.cached_location
            }
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def set_manual_location(self, lat, lon):
        if validate_coordinates(lat, lon):
            self.manual_override = {
                "latitude": float(lat),
                "longitude": float(lon),
                "provider": "manual",
                "timestamp": int(time.time())
            }
            self.save_persisted()
            return True
        return False

    def clear_manual_location(self):
        self.manual_override = None
        self.save_persisted()

    def get_location_fresh(self):
        if self.manual_override:
            return self.manual_override

        loc = self._fetch_location_all()
        if loc:
            self.cached_location = loc
            self.save_persisted()
            return loc

        return self.cached_location

    def get_location(self):
        """
        Returns the most accurate available location instantly from manual override or cache,
        or performs a fast lookup if cache is cold (>120s old).
        """
        if self.manual_override:
            return self.manual_override

        if self.cached_location and (time.time() - self.cached_location.get("timestamp", 0)) < 120:
            return self.cached_location

        # Immediate fast lookup if cache is cold
        loc = self._fetch_location_all()
        if loc:
            self.cached_location = loc
            self.save_persisted()
            return loc

        return self.cached_location

    def _fetch_location_all(self):
        # 1. Try Termux Location API (if binary exists)
        termux_loc = self._fetch_termux_location_fast()
        if termux_loc:
            return termux_loc

        # 2. Fallback to IP-based Geolocation
        ip_loc = self._fetch_ip_location()
        if ip_loc:
            return ip_loc

        return None

    def _fetch_termux_location_fast(self):
        if not shutil.which("termux-location"):
            return None

        commands = [
            ["termux-location", "-r", "last"],
            ["termux-location", "-p", "network", "-r", "once"],
            ["termux-location", "-p", "gps", "-r", "once"],
            ["termux-location"]
        ]

        for cmd in commands:
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1.5
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout.strip())
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    if validate_coordinates(lat, lon):
                        provider = data.get("provider", "termux-gps")
                        return {
                            "latitude": float(lat),
                            "longitude": float(lon),
                            "provider": str(provider),
                            "timestamp": int(time.time())
                        }
            except Exception:
                continue

        return None

    def _fetch_ip_location(self):
        """
        Fallback geolocation using standard HTTP services when GPS is unavailable.
        """
        services = [
            ("http://ip-api.com/json/?fields=status,lat,lon", lambda d: (d.get("lat"), d.get("lon")) if d.get("status") == "success" else (None, None)),
            ("https://ipapi.co/json/", lambda d: (d.get("latitude"), d.get("longitude"))),
            ("https://ipinfo.io/json", lambda d: tuple(map(float, d.get("loc", "").split(","))) if "loc" in d and "," in d["loc"] else (None, None))
        ]

        for url, parser in services:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "EmergencyMesh/1.0"})
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        lat, lon = parser(data)
                        if validate_coordinates(lat, lon):
                            return {
                                "latitude": float(lat),
                                "longitude": float(lon),
                                "provider": "ip-geolocation",
                                "timestamp": int(time.time())
                            }
            except Exception:
                continue

        return None

    async def start_background_updates(self, interval=15):
        self.running = True
        loop = asyncio.get_event_loop()

        while self.running:
            try:
                loc = await loop.run_in_executor(None, self._fetch_location_all)
                if loc:
                    self.cached_location = loc
                    self.save_persisted()
            except Exception:
                pass
            await asyncio.sleep(interval)

    def stop_background_updates(self):
        self.running = False
        if self.update_task:
            self.update_task.cancel()

# Global default instance
_location_manager = None

def get_location_manager(config_dir=None):
    global _location_manager
    if _location_manager is None:
        _location_manager = LocationManager(config_dir=config_dir)
    elif config_dir and _location_manager.config_dir != Path(config_dir):
        _location_manager.set_config_dir(config_dir)
    return _location_manager

def get_location():
    return get_location_manager().get_location()

