import subprocess
import json

def get_location(timeout_seconds=3):
    """
    Attempts to fetch GPS coordinates via `termux-location`.
    Returns dict with latitude and longitude float values if successful,
    or None if unavailable, permission denied, disabled, or timed out.
    """
    try:
        result = subprocess.run(
            ["termux-location", "-p", "gps", "-r", "once"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                return {"latitude": float(lat), "longitude": float(lon)}
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError, Exception):
        pass

    # Fallback attempt with default network/last known provider if GPS provider timed out
    try:
        result = subprocess.run(
            ["termux-location", "-r", "last"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            lat = data.get("latitude")
            lon = data.get("longitude")
            if lat is not None and lon is not None:
                return {"latitude": float(lat), "longitude": float(lon)}
    except Exception:
        pass

    return None
