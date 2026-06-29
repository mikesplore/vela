"""
Vela System Alerts Service
Handles CPU/memory spike detection and daily system usage reports.
Uses vnstat for network data usage tracking.
Reads RECIPIENT_EMAIL from .env so no email prompts needed.
"""

import json
import logging
import os
import subprocess
import re
import platform
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import psutil

from app.services.monitoring import get_cpu_usage, get_ram_status, get_top_processes, get_uptime
from app.services.system_info import get_os_info
from app.utils import emails

logger = logging.getLogger(__name__)

RESEND_AVAILABLE = emails.is_configured()
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

if not RESEND_AVAILABLE:
    logger.warning("RESEND_API_KEY not set in .env — email alerts disabled")
if not RECIPIENT_EMAIL:
    logger.warning("RECIPIENT_EMAIL not set in .env — cannot send alerts")

# Default thresholds
DEFAULT_CPU_THRESHOLD = 80.0
DEFAULT_MEMORY_THRESHOLD = 85.0
DEFAULT_SPIKE_COOLDOWN_MINUTES = 15

# State tracking
_last_spike_alerts: Dict[str, datetime] = {}
_alert_history: List[Dict[str, Any]] = []
_daily_stats: Dict[str, Any] = {}


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


# ── Cooldown helpers ───────────────────────────────────────────────────────────

def _is_in_cooldown(alert_type: str, cooldown_minutes: int) -> bool:
    if alert_type in _last_spike_alerts:
        elapsed = (datetime.now() - _last_spike_alerts[alert_type]).total_seconds() / 60
        return elapsed < cooldown_minutes
    return False


def _update_cooldown(alert_type: str):
    _last_spike_alerts[alert_type] = datetime.now()


def _get_top_process_info() -> Tuple[str, float]:
    try:
        processes = get_top_processes(limit=1)
        if processes.by_cpu:
            top_proc = processes.by_cpu[0]
            return top_proc.name, top_proc.cpu_percent
    except Exception as e:
        logger.warning(f"Failed to get top process: {e}")
    return "unknown", 0.0


def _get_os_info_string() -> str:
    try:
        os_info = get_os_info()
        return f"{os_info.os_name} {os_info.os_version} (Kernel: {os_info.kernel})"
    except Exception:
        return f"{platform.system()} {platform.release()}"


def _get_uptime_string() -> str:
    try:
        uptime_info = get_uptime()
        return uptime_info.formatted
    except Exception:
        return "unknown"


# ── Spike monitoring (reads email from env) ────────────────────────────────────

def check_and_send_spike_alert(
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    cooldown_minutes: int = DEFAULT_SPIKE_COOLDOWN_MINUTES,
) -> Optional[Dict[str, Any]]:
    """
    Check current CPU and memory. If thresholds exceeded, send spike alert
    to the email in RECIPIENT_EMAIL env var. No need to pass email.
    """
    if not RESEND_AVAILABLE:
        logger.error("Resend not available")
        return None
    if not RECIPIENT_EMAIL:
        logger.error("RECIPIENT_EMAIL not set")
        return None

    alerts_sent = []
    cpu_usage = get_cpu_usage()

    # CPU spike
    if cpu_usage.overall >= cpu_threshold:
        alert_key = "cpu_spike"
        if not _is_in_cooldown(alert_key, cooldown_minutes):
            try:
                top_process, _ = _get_top_process_info()
                result = emails.send_spike_alert(
                    to=RECIPIENT_EMAIL,
                    device_name=platform.node(),
                    cpu_percent=cpu_usage.overall,
                    memory_percent=get_ram_status().percent,
                    cpu_threshold=cpu_threshold,
                    memory_threshold=memory_threshold,
                    top_process=top_process,
                    uptime=_get_uptime_string(),
                    os_info=_get_os_info_string(),
                )
                _update_cooldown(alert_key)
                alerts_sent.append({"type": "cpu_spike", "value": cpu_usage.overall, "threshold": cpu_threshold})
                logger.info(f"CPU spike alert sent: {cpu_usage.overall}% >= {cpu_threshold}%")
            except Exception as e:
                logger.error(f"CPU spike alert failed: {e}")

    # Memory spike
    ram_status = get_ram_status()
    if ram_status.percent >= memory_threshold:
        alert_key = "memory_spike"
        if not _is_in_cooldown(alert_key, cooldown_minutes):
            try:
                top_process, _ = _get_top_process_info()
                result = emails.send_spike_alert(
                    to=RECIPIENT_EMAIL,
                    device_name=platform.node(),
                    cpu_percent=cpu_usage.overall,
                    memory_percent=ram_status.percent,
                    cpu_threshold=cpu_threshold,
                    memory_threshold=memory_threshold,
                    top_process=top_process,
                    uptime=_get_uptime_string(),
                    os_info=_get_os_info_string(),
                )
                _update_cooldown(alert_key)
                alerts_sent.append({"type": "memory_spike", "value": ram_status.percent, "threshold": memory_threshold})
                logger.info(f"Memory spike alert sent: {ram_status.percent}% >= {memory_threshold}%")
            except Exception as e:
                logger.error(f"Memory spike alert failed: {e}")

    return alerts_sent if alerts_sent else None


# ── Daily summary (reads email from env) ───────────────────────────────────────

def collect_daily_stats() -> Dict[str, Any]:
    """Accumulate stats throughout the day."""
    cpu_usage = get_cpu_usage()
    ram_status = get_ram_status()
    network_data = _vnstat_run("day")

    today = datetime.now().strftime("%Y-%m-%d")
    if today not in _daily_stats:
        _daily_stats[today] = {
            "cpu_readings": [], "memory_readings": [],
            "disk_read_bytes": 0, "disk_write_bytes": 0,
            "net_sent_bytes": 0, "net_recv_bytes": 0,
            "alerts_count": 0, "last_alert_time": None,
        }
    stats = _daily_stats[today]
    stats["cpu_readings"].append(cpu_usage.overall)
    stats["memory_readings"].append(ram_status.percent)
    try:
        disk_io = psutil.disk_io_counters()
        if disk_io:
            stats["disk_read_bytes"] = disk_io.read_bytes
            stats["disk_write_bytes"] = disk_io.write_bytes
    except Exception:
        pass
    stats["net_sent_bytes"] = network_data.get("tx_bytes", 0)
    stats["net_recv_bytes"] = network_data.get("rx_bytes", 0)
    return stats


def send_daily_summary() -> Optional[Dict[str, Any]]:
    """
    Send daily system summary to RECIPIENT_EMAIL. No email param needed.
    """
    if not RESEND_AVAILABLE:
        logger.error("Resend not available")
        return None
    if not RECIPIENT_EMAIL:
        logger.error("RECIPIENT_EMAIL not set")
        return None

    try:
        stats = collect_daily_stats()
        cpu_readings = stats.get("cpu_readings", [0])
        memory_readings = stats.get("memory_readings", [0])

        cpu_avg = sum(cpu_readings) / len(cpu_readings) if cpu_readings else 0
        cpu_peak = max(cpu_readings) if cpu_readings else 0
        memory_avg = sum(memory_readings) / len(memory_readings) if memory_readings else 0
        memory_peak = max(memory_readings) if memory_readings else 0

        net = _vnstat_run("day")
        net_sent = _format_bytes(net.get("tx_bytes", 0))
        net_recv = _format_bytes(net.get("rx_bytes", 0))
        disk_read = _format_bytes(stats.get("disk_read_bytes", 0))
        disk_write = _format_bytes(stats.get("disk_write_bytes", 0))

        try:
            top_procs = get_top_processes(limit=3)
            top_processes = [
                {"name": p.name, "cpu": round(p.cpu_percent, 1)}
                for p in top_procs.by_cpu[:3]
            ]
        except Exception:
            top_processes = []

        alerts_count = len([a for a in _alert_history if a.get("date") == datetime.now().strftime("%Y-%m-%d")])
        last_alert_time = _alert_history[-1].get("time", "Never") if _alert_history else "Never"

        result = emails.send_daily_summary(
            to=RECIPIENT_EMAIL,
            device_name=platform.node(),
            cpu_avg=round(cpu_avg, 1), cpu_peak=round(cpu_peak, 1),
            memory_avg=round(memory_avg, 1), memory_peak=round(memory_peak, 1),
            disk_read=disk_read, disk_write=disk_write,
            net_sent=net_sent, net_recv=net_recv,
            uptime=_get_uptime_string(), os_info=_get_os_info_string(),
            top_processes=top_processes,
            alerts_count=alerts_count, last_alert_time=last_alert_time,
        )
        logger.info("Daily summary sent")
        return result
    except Exception as e:
        logger.error(f"Daily summary failed: {e}")
        return None


# ── On-demand system stats ─────────────────────────────────────────────────────

def get_system_stats_text() -> str:
    """Return a plain-text summary of current system stats (no email)."""
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


# ── Schedule setup ─────────────────────────────────────────────────────────────

def setup_monitoring_schedule(
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    spike_check_interval_minutes: int = 5,
    daily_summary_time: str = "18:00",
):
    """
    Schedule spike monitoring (every 5min) and daily summary (default 6 PM).
    Email is read from RECIPIENT_EMAIL env var — no prompt.
    """
    from app.services.scheduler import get_scheduler
    from apscheduler.triggers.interval import IntervalTrigger
    from apscheduler.triggers.cron import CronTrigger

    scheduler = get_scheduler()

    def spike_check_job():
        try:
            result = check_and_send_spike_alert(
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
            )
            if result:
                for alert in result:
                    _alert_history.append({
                        "type": alert["type"],
                        "value": alert["value"],
                        "threshold": alert["threshold"],
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "time": datetime.now().strftime("%H:%M"),
                    })
        except Exception as e:
            logger.error(f"Spike check job error: {e}")

    scheduler.add_job(
        spike_check_job,
        trigger=IntervalTrigger(minutes=spike_check_interval_minutes),
        id="vela_spike_monitor",
        name="Vela Spike Monitor",
        replace_existing=True,
    )

    hour, minute = map(int, daily_summary_time.split(":"))

    def daily_summary_job():
        try:
            send_daily_summary()
        except Exception as e:
            logger.error(f"Daily summary job error: {e}")

    scheduler.add_job(
        daily_summary_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="vela_daily_summary",
        name="Vela Daily Summary",
        replace_existing=True,
    )

    logger.info(
        f"Monitoring scheduled: spikes every {spike_check_interval_minutes}min, "
        f"daily summary at {daily_summary_time}, email: {RECIPIENT_EMAIL}"
    )


# ── Status & vnstat check ──────────────────────────────────────────────────────

def get_monitoring_status() -> Dict[str, Any]:
    from app.services.scheduler import get_scheduler
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    spike_job = summary_job = None
    for job in jobs:
        if job.id == "vela_spike_monitor":
            spike_job = {"next_run": job.next_run_time.isoformat() if job.next_run_time else None}
        elif job.id == "vela_daily_summary":
            summary_job = {"next_run": job.next_run_time.isoformat() if job.next_run_time else None}
    return {
        "spike_monitor": spike_job,
        "daily_summary": summary_job,
        "alerts_today": len([a for a in _alert_history if a.get("date") == datetime.now().strftime("%Y-%m-%d")]),
        "recipient_email": RECIPIENT_EMAIL,
        "vnstat_available": _is_vnstat_available(),
    }


def _is_vnstat_available() -> bool:
    try:
        r = subprocess.run(["vnstat", "--version"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


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