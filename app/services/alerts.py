"""
Vela System Alerts Service
Handles CPU/memory spike detection and daily system usage reports.
Reads RECIPIENT_EMAIL from .env so no email prompts needed.
"""

import logging
import os
import platform
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

import psutil

from app.services.monitoring import get_cpu_usage, get_ram_status, get_top_processes, get_uptime
from app.services.system_info import get_os_info
from app.utils import emails

logger = logging.getLogger(__name__)

RESEND_AVAILABLE = emails.is_configured()
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "")

# Default thresholds
DEFAULT_CPU_THRESHOLD = 80.0
DEFAULT_MEMORY_THRESHOLD = 85.0
DEFAULT_SPIKE_COOLDOWN_MINUTES = 15

# State tracking
_last_spike_alerts: Dict[str, datetime] = {}
_alert_history: List[Dict[str, Any]] = []
_daily_stats: Dict[str, Any] = {}


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


def _send_push_spike(*, resource: str, value: float, threshold: float) -> None:
    try:
        from app.services.push import send_push

        send_push(
            title=f"Vela alert · {resource} spike",
            body=f"{resource} is {value:.1f}% (threshold {threshold:.1f}%).",
            data={"source": "vela", "resource": resource.lower(), "value": f"{value:.1f}", "threshold": f"{threshold:.1f}"},
        )
    except Exception as exc:
        logger.warning("Could not deliver FCM spike notification: %s", exc)


# ── Spike monitoring (reads email from env) ────────────────────────────────────

def check_and_send_spike_alert(
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    cooldown_minutes: int = DEFAULT_SPIKE_COOLDOWN_MINUTES,
) -> list[Any] | None:
    """
    Check current CPU and memory. If thresholds exceeded, send spike alert
    to the email in RECIPIENT_EMAIL env var. No need to pass email.
    """
    email_enabled = RESEND_AVAILABLE and bool(RECIPIENT_EMAIL)
    if not email_enabled:
        logger.info("Email alert delivery is unavailable; continuing with configured push delivery.")

    alerts_sent = []
    cpu_usage = get_cpu_usage()

    # CPU spike
    if cpu_usage.overall >= cpu_threshold:
        alert_key = "cpu_spike"
        if not _is_in_cooldown(alert_key, cooldown_minutes):
            try:
                top_process, _ = _get_top_process_info()
                if email_enabled:
                    emails.send_spike_alert(
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
                _send_push_spike(resource="CPU", value=cpu_usage.overall, threshold=cpu_threshold)
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
                if email_enabled:
                    emails.send_spike_alert(
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
                _send_push_spike(resource="Memory", value=ram_status.percent, threshold=memory_threshold)
                _update_cooldown(alert_key)
                alerts_sent.append({"type": "memory_spike", "value": ram_status.percent, "threshold": memory_threshold})
                logger.info(f"Memory spike alert sent: {ram_status.percent}% >= {memory_threshold}%")
            except Exception as e:
                logger.error(f"Memory spike alert failed: {e}")

    return alerts_sent if alerts_sent else None


# ── Daily summary (reads email from env) ───────────────────────────────────────

def collect_daily_stats() -> Dict[str, Any]:
    """Accumulate stats throughout the day."""
    from app.services.network import _vnstat_run

    cpu_usage = get_cpu_usage()
    ram_status = get_ram_status()
    network_data = _vnstat_run("day")
    try:
        disk_io = psutil.disk_io_counters()
    except Exception:
        disk_io = None

    today = datetime.now().strftime("%Y-%m-%d")
    if today not in _daily_stats:
        _daily_stats[today] = {
            "cpu_readings": [], "memory_readings": [],
            "disk_read_bytes": 0, "disk_write_bytes": 0,
            "disk_read_baseline": disk_io.read_bytes if disk_io else 0,
            "disk_write_baseline": disk_io.write_bytes if disk_io else 0,
            "net_sent_bytes": 0, "net_recv_bytes": 0,
            "alerts_count": 0, "last_alert_time": None,
        }
    stats = _daily_stats[today]
    stats["cpu_readings"].append(cpu_usage.overall)
    stats["memory_readings"].append(ram_status.percent)
    if disk_io:
        stats["disk_read_bytes"] = max(0, disk_io.read_bytes - stats["disk_read_baseline"])
        stats["disk_write_bytes"] = max(0, disk_io.write_bytes - stats["disk_write_baseline"])
    stats["net_sent_bytes"] = network_data.get("tx_bytes", 0)
    stats["net_recv_bytes"] = network_data.get("rx_bytes", 0)
    return stats


def scheduled_spike_check(
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
) -> None:
    """Persistent-scheduler-safe monitoring job; callable by import path."""
    try:
        # Sampling here makes daily averages and peaks reflect the whole
        # runtime day, rather than only the instant the summary is sent.
        collect_daily_stats()
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
    except Exception as exc:
        logger.error("Spike check job error: %s", exc)


def scheduled_daily_summary() -> None:
    """Persistent-scheduler-safe daily summary job."""
    try:
        send_daily_summary()
    except Exception as exc:
        logger.error("Daily summary job error: %s", exc)


def handle_alertmanager_webhook(payload: dict[str, Any]) -> dict[str, int]:
    """Deliver deduplicated Alertmanager firing/resolved events to FCM devices."""
    from app.services.push import claim_external_alert, send_push

    accepted = delivered = 0
    for alert in payload.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") or {}
        annotations = alert.get("annotations") or {}
        status = str(alert.get("status") or payload.get("status") or "firing").lower()
        fingerprint = str(alert.get("fingerprint") or "")
        if not fingerprint:
            fingerprint = hashlib.sha256(
                json.dumps({"labels": labels, "startsAt": alert.get("startsAt")}, sort_keys=True).encode()
            ).hexdigest()
        if not claim_external_alert(fingerprint=fingerprint, status=status):
            continue
        name = str(labels.get("alertname") or "System alert")
        severity = str(labels.get("severity") or "warning").lower()
        summary = str(annotations.get("summary") or annotations.get("description") or name)
        title = f"Vela {'resolved' if status == 'resolved' else 'alert'} · {name}"
        delivered += send_push(
            title=title,
            body=summary,
            data={
                "source": "alertmanager",
                "fingerprint": fingerprint,
                "status": status,
                "severity": severity,
                "alertname": name,
            },
        )
        accepted += 1
    return {"accepted": accepted, "delivered": delivered}


def send_daily_summary() -> Optional[Dict[str, Any]]:
    """
    Send daily system summary to RECIPIENT_EMAIL. No email param needed.
    """
    from app.services.network import _vnstat_run, _format_bytes

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
    from app.services.network import _vnstat_run, _format_bytes

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

    scheduler.add_job(
        scheduled_spike_check,
        trigger=IntervalTrigger(minutes=spike_check_interval_minutes),
        id="vela_spike_monitor",
        name="Vela Spike Monitor",
        replace_existing=True,
        kwargs={
            "cpu_threshold": cpu_threshold,
            "memory_threshold": memory_threshold,
        },
    )

    hour, minute = map(int, daily_summary_time.split(":"))

    scheduler.add_job(
        scheduled_daily_summary,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=scheduler.timezone),
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
    from app.services.network import _is_vnstat_available
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