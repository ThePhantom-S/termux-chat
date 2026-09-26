import subprocess
import json
import time
import asyncio
import math
import sys

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
    try:
        subprocess.Popen(
            ["termux-notification", "--sound", "--title", "🚨 EMERGENCY SOS ALERT", "--content", str(alert_text), "--priority", "high"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

    # 4. Text-To-Speech Audio Voice Alert
    try:
        subprocess.Popen(
            ["termux-tts-speak", "Emergency S O S alert received!"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

class LocationManager:
    def __init__(self):
        self.cached_location = None
        self.manual_override = None
        self.update_task = None
        self.running = False

    def set_manual_location(self, lat, lon):
        try:
            self.manual_override = {
                "latitude": float(lat),
                "longitude": float(lon),
                "provider": "manual",
                "timestamp": int(time.time())
            }
            return True
        except (ValueError, TypeError):
            return False

    def clear_manual_location(self):
        self.manual_override = None

    def get_location(self):
        """
        Returns the most accurate available location instantly from cache or manual override,
        or performs a fast lookup if cache is cold.
        """
        if self.manual_override:
            return self.manual_override

        if self.cached_location and (time.time() - self.cached_location.get("timestamp", 0)) < 120:
            return self.cached_location

        # Immediate fast lookup if cache is cold
        loc = self._fetch_termux_location_fast()
        if loc:
            self.cached_location = loc
            return loc

        return self.cached_location

    def _fetch_termux_location_fast(self):
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
                    timeout=3
                )
                if result.returncode == 0 and result.stdout.strip():
                    data = json.loads(result.stdout.strip())
                    lat = data.get("latitude")
                    lon = data.get("longitude")
                    if lat is not None and lon is not None:
                        provider = data.get("provider", "termux-api")
                        return {
                            "latitude": float(lat),
                            "longitude": float(lon),
                            "provider": str(provider),
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
                loc = await loop.run_in_executor(None, self._fetch_termux_location_fast)
                if loc:
                    self.cached_location = loc
            except Exception:
                pass
            await asyncio.sleep(interval)

    def stop_background_updates(self):
        self.running = False
        if self.update_task:
            self.update_task.cancel()

# Global default instance
_location_manager = LocationManager()

def get_location():
    return _location_manager.get_location()

def get_location_manager():
    return _location_manager
