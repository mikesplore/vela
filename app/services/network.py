import json
import logging
import os
import re
import socket
import subprocess
import time
import urllib.request
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import psutil

try:
    import speedtest
except ImportError:  # pragma: no cover
    speedtest = None

from app.services.monitoring import get_top_processes, get_uptime
from app.services.system_info import get_os_info
from app.utils.config import get_config

logger = logging.getLogger(__name__)

# In-memory cache for geo-location to avoid external provider rate limits.
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

def _lookup_ip_api(ip: str) -> Optional[Dict[str, Any]]:
    url = (
        f"http://ip-api.com/json/{quote(ip, safe='')}"
        "?fields=status,country,regionName,city,zip,timezone,isp,org,lat,lon,query,message"
    )
    with urllib.request.urlopen(url, timeout=5) as response:
        data = json.loads(response.read().decode().strip())
    if not isinstance(data, dict) or data.get("status") != "success":
        return None
    return {
        "status": "success",
        "query": data.get("query") or ip,
        "country": data.get("country"),
        "region": data.get("regionName") or data.get("region"),
        "city": data.get("city"),
        "zip": data.get("zip"),
        "timezone": data.get("timezone"),
        "isp": data.get("isp"),
        "org": data.get("org"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "message": None,
    }


def _lookup_ipinfo_lite(ip: str, token: str) -> Optional[Dict[str, Any]]:
    """IPinfo Lite fallback; Lite only supplies country and ASN metadata."""
    url = f"https://api.ipinfo.io/lite/{quote(ip, safe='')}?token={quote(token, safe='')}"
    with urllib.request.urlopen(url, timeout=5) as response:
        data = json.loads(response.read().decode().strip())
    if not isinstance(data, dict) or not data.get("ip"):
        return None
    return {
        "status": "success",
        "query": data.get("ip") or ip,
        "country": data.get("country"),
        "region": None,
        "city": None,
        "zip": None,
        "timezone": None,
        "isp": data.get("as_name"),
        "org": data.get("as_domain") or data.get("asn"),
        "lat": None,
        "lon": None,
        "message": "Location resolved by IPinfo Lite; city and coordinates are unavailable on this plan.",
    }


def geolocate_ip(ip: str) -> Optional[Dict[str, Any]]:
    if not ip:
        return None

    now = time.time()
    cached = _geo_cache.get(ip)
    if cached and (now - cached[0]) < _GEO_CACHE_TTL:
        return cached[1]

    try:
        result = _lookup_ip_api(ip)
    except Exception:
        result = None

    if result is None:
        token = (get_config().ipinfo_token or "").strip()
        if token:
            try:
                result = _lookup_ipinfo_lite(ip, token)
            except Exception:
                result = None

    if result is not None:
        _geo_cache[ip] = (now, result)
    return result


# ── vnstat helpers (multi-period) ──────────────────────────────────────────────

def _get_default_interface() -> str:
    """Auto-detect the primary network interface."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout:
            match = re.search(r'dev\s+(\w+)', result.stdout)
            if match:
                return match.group(1)
    except Exception:
        pass
    for iface in ["eth0", "enp0s3", "ens33", "wlan0"]:
        if psutil.net_if_stats().get(iface):
            return iface
    interfaces = psutil.net_if_stats()
    for name, stats in interfaces.items():
        if name != "lo" and stats.isup:
            return name
    return "eth0"


def _vnstat_run(period: str = "day", interface: Optional[str] = None) -> Dict[str, Any]:
    """
    Run vnstat CLI and parse human-readable output.
    period: 'day' -> vnstat -d, 'month' -> vnstat -m, 'hour' -> vnstat -h, 'live' -> vnstat -l (1 line)
    Returns dict with 'rx', 'tx', 'rx_bytes', 'tx_bytes'.
    """
    if not interface:
        interface = _get_default_interface()

    flag = {"day": "-d", "month": "-m", "hour": "-h", "live": "-l"}.get(period, "-d")
    cmd = ["vnstat", "-i", interface, flag]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0 or not result.stdout.strip():
            return {"rx": 0, "tx": 0, "rx_bytes": 0, "tx_bytes": 0}
    except Exception as e:
        logger.warning(f"vnstat error: {e}")
        return {"rx": 0, "tx": 0, "rx_bytes": 0, "tx_bytes": 0}

    today_str = datetime.now().strftime("%Y-%m-%d")
    current_month = today_str[:7]

    def to_bytes(v, u):
        return {
            'B': v, 'KiB': v*1024, 'MiB': v*1024**2,
            'GiB': v*1024**3, 'TiB': v*1024**4
        }.get(u, v)

    best_rx = best_tx = 0.0

    # Helper: extract first "N UNIT" occurrences from a string
    def extract_pair(text):
        vals = re.findall(r'([0-9,]+\.[0-9]+)\s*(MiB|GiB|KiB|B|TiB|kbit|Mbit|Gbit|bit)', text)
        if len(vals) >= 2:
            return to_bytes(float(vals[0][0].replace(',', '')), vals[0][1]), to_bytes(float(vals[1][0].replace(',', '')), vals[1][1])
        return 0.0, 0.0

    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue

        # Match date/month/hour label
        date_label = None
        m_date = re.match(r'^(\d{4}-\d{2}-\d{2})', line)
        if m_date:
            date_label = m_date.group(1)

        if period == "month":
            m_month = re.match(r'^(\d{4}-\d{2})', line)
            if m_month:
                date_label = m_month.group(1)
            else:
                continue

        if period == "hour":
            # For hourly, take the LAST line that has an HH:MM time
            m_hour = re.search(r'\b(\d{2}:\d{2})\b', line)
            if not m_hour:
                continue
            # We'll set date_label and continue scanning to find the last matching line
            date_label = m_hour.group(1)
            rx, tx = extract_pair(line)
            best_rx, best_tx = rx, tx
            continue

        if not date_label:
            continue

        target = today_str if period in ("day",) else current_month
        if date_label != target:
            continue

        # Pull the rx/tx values from the line text (after the date prefix)
        # vnstat format: "2026-06-29   6.76 GiB |  446.75 MiB | ..."
        rx, tx = extract_pair(line)
        best_rx, best_tx = rx, tx
        break

    return {"rx": best_rx, "tx": best_tx, "rx_bytes": int(best_rx), "tx_bytes": int(best_tx)}


def get_vnstat_data(period: str = "day", interface: Optional[str] = None) -> Dict[str, Any]:
    """
    Public: get network usage from vnstat for a given period.
    period: "day" (today), "month" (this month), "hour" (current hour)
    Returns raw bytes and human-readable strings.
    """
    raw = _vnstat_run(period, interface)
    rx = raw.get("rx_bytes", 0)
    tx = raw.get("tx_bytes", 0)
    return {
        "interface": interface or _get_default_interface(),
        "period": period,
        "received_bytes": rx,
        "transmitted_bytes": tx,
        "received": _format_bytes(rx),
        "transmitted": _format_bytes(tx),
    }


def _format_bytes(bytes_value: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(bytes_value) < 1024.0:
            return f"{bytes_value:.1f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.1f} PB"


def get_system_stats_text() -> str:
    """Return a plain-text summary of current system stats (no email)."""
    import platform
    cpu = get_cpu_usage()
    ram = get_ram_status()
    uptime_str = _get_uptime_string()
    os_str = _get_os_info_string()
    net_today = _vnstat_run("day")
    net_month = _vnstat_run("month")
    top = get_top_processes(limit=5)

    lines = [
        f"📊 System Stats — {platform.node()}",
        f"OS: {os_str}",
        f"Uptime: {uptime_str}",
        "",
        "── CPU ──",
        f"  Overall: {cpu.overall:.1f}%",
        f"  Per core: {', '.join(f'{c:.1f}%' for c in cpu.per_core)}",
        "",
        "── Memory ──",
        f"  Used: {ram.percent:.1f}% ({_format_bytes(ram.used)} / {_format_bytes(ram.total)})",
        "",
        "── Network (vnstat) ──",
        f"  Today:  ↓ {_format_bytes(net_today.get('rx_bytes', 0))}  ↑ {_format_bytes(net_today.get('tx_bytes', 0))}",
        f"  Month:  ↓ {_format_bytes(net_month.get('rx_bytes', 0))}  ↑ {_format_bytes(net_month.get('tx_bytes', 0))}",
        "",
        "── Top Processes (CPU) ──",
    ]
    for p in top.by_cpu[:5]:
        lines.append(f"  {p.name:<20} CPU: {p.cpu_percent:6.1f}%  MEM: {p.memory_percent:5.1f}%")
    return "\n".join(lines)


def _get_uptime_string() -> str:
    try:
        uptime_info = get_uptime()
        return uptime_info.formatted
    except Exception:
        return "unknown"


def _get_os_info_string() -> str:
    try:
        os_info = get_os_info()
        return f"{os_info.os_name} {os_info.os_version} (Kernel: {os_info.kernel})"
    except Exception:
        import platform
        return f"{platform.system()} {platform.release()}"


def check_vnstat_installation() -> Dict[str, Any]:
    status = {"installed": False, "version": None, "interfaces": [], "default_interface": None, "errors": []}
    try:
        r = subprocess.run(["vnstat", "--version"], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            status["installed"] = True
            status["version"] = r.stdout.strip().split('\n')[0] if r.stdout else "unknown"
        r2 = subprocess.run(["vnstat", "--json"], capture_output=True, text=True, timeout=10)
        if r2.returncode == 0:
            data = json.loads(r2.stdout)
            if "interfaces" in data:
                status["interfaces"] = [iface["name"] for iface in data["interfaces"]]
                status["default_interface"] = _get_default_interface()
    except Exception as e:
        status["errors"].append(str(e))
    return status


def _is_vnstat_available() -> bool:
    try:
        r = subprocess.run(["vnstat", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


# Import these here to avoid circular imports
from app.services.monitoring import get_cpu_usage, get_ram_status
