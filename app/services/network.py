import json
import socket
import subprocess
import time
import urllib.request
from typing import Any, Dict, Optional

try:
    import speedtest
except ImportError:  # pragma: no cover
    speedtest = None

# In-memory cache for geo-location to avoid ip-api.com rate limiting
# ip-api.com allows 45 req/min from a single IP
_geo_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_GEO_CACHE_TTL = 30  # seconds


def run_command_input(cmd: list[str], input_text: str, timeout: int = 10) -> tuple[str, str, int]:
    """Run a command with stdin input (used for bluetoothctl interactive commands)."""
    try:
        result = subprocess.run(
            cmd,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return "", str(exc), 1


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
            return response.read().decode().strip()
    except Exception:
        return ""

# ---------------------------------------------------------------------------
# Geo-location helper
# ---------------------------------------------------------------------------

def geolocate_ip(ip: str) -> Optional[Dict[str, Any]]:
    if not ip:
        return None

    # Return cached result if still fresh
    now = time.time()
    cached = _geo_cache.get(ip)
    if cached and (now - cached[0]) < _GEO_CACHE_TTL:
        return cached[1]

    try:
        url = (
            f"http://ip-api.com/json/{ip}"
            "?fields=status,country,regionName,city,zip,timezone,isp,org,lat,lon,query,message"
        )
        with urllib.request.urlopen(url, timeout=5) as response:
            raw = response.read().decode().strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        result = {
            "status": data.get("status", "fail"),
            "query": data.get("query"),
            "country": data.get("country"),
            "region": data.get("regionName") or data.get("region"),
            "city": data.get("city"),
            "zip": data.get("zip"),
            "timezone": data.get("timezone"),
            "isp": data.get("isp"),
            "org": data.get("org"),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "message": data.get("message"),
        }
        _geo_cache[ip] = (time.time(), result)
        return result
    except Exception:
        return None
