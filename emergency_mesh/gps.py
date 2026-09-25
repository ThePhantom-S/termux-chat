import subprocess
import json
import time
import asyncio

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
        # 1. Try last known location (instant execution, doesn't lock GPS hardware)
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
                # Run fetch in background thread executor so asyncio loop is never blocked
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
