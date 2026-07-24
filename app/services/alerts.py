"""
Vela System Alerts Service
Handles CPU/memory/disk spike detection and daily system usage reports.
Uses alert_delivery for push + email; email is cooldown-limited to avoid spam.
"""

import hashlib
import json
import logging
import platform
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psutil

from app.services import alert_delivery
from app.services.monitoring import get_cpu_usage, get_ram_status, get_top_processes, get_uptime
from app.services.system_info import get_os_info
from app.utils.config import get_config

logger = logging.getLogger(__name__)

# Backwards-compatible module constants (prefer get_config() at runtime).
DEFAULT_CPU_THRESHOLD = 85.0
DEFAULT_MEMORY_THRESHOLD = 85.0
DEFAULT_DISK_THRESHOLD = 80.0
DEFAULT_SPIKE_COOLDOWN_MINUTES = 15

# State tracking (in-memory cooldown prevents notification spam).
_last_spike_alerts: Dict[str, datetime] = {}
_daily_stats: Dict[str, Any] = {}


def _alert_settings() -> dict[str, float | int]:
    cfg = get_config()
    return {
        "cpu_threshold": cfg.cpu_alert_threshold,
        "memory_threshold": cfg.memory_alert_threshold,
        "disk_threshold": cfg.disk_alert_threshold,
        "cooldown_minutes": cfg.alert_cooldown_minutes,
    }


def _is_in_cooldown(alert_type: str, cooldown_minutes: int) -> bool:
    if alert_type in _last_spike_alerts:
        elapsed = (datetime.now() - _last_spike_alerts[alert_type]).total_seconds() / 60
        return elapsed < cooldown_minutes
    return False


def _update_cooldown(alert_type: str) -> None:
    _last_spike_alerts[alert_type] = datetime.now()


def _get_top_process_info() -> Tuple[str, float]:
    try:
        processes = get_top_processes(limit=1)
        if processes.by_cpu:
            top_proc = processes.by_cpu[0]
            return top_proc.name, top_proc.cpu_percent
    except Exception as e:
        logger.warning("Failed to get top process: %s", e)
    return "unknown", 0.0


def _get_os_info_string() -> str:
    try:
        os_info = get_os_info()
        return f"{os_info.os_name} {os_info.os_version} (Kernel: {os_info.kernel})"
    except Exception:
        return f"{platform.system()} {platform.release()}"


def _get_uptime_string() -> str:
    try:
        return get_uptime().formatted
    except Exception:
        return "unknown"


def _disk_usage_alerts(threshold: float) -> list[dict[str, Any]]:
    """Partitions at or above threshold percent usage."""
    alerts: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype in {"tmpfs", "devtmpfs", "squashfs", "overlay"}:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except OSError:
            continue
        if usage.percent >= threshold:
            alerts.append({
                "mountpoint": part.mountpoint,
                "percent": usage.percent,
                "filesystem": part.fstype,
            })
    return alerts


def _swap_usage_percent() -> float | None:
    try:
        swap = psutil.swap_memory()
    except Exception:
        return None
    if swap.total <= 0:
        return None
    return swap.percent


def _dispatch_spike(
    *,
    alert_key: str,
    resource: str,
    value: float,
    threshold: float,
    cpu_usage: float,
    memory_percent: float,
    cpu_threshold: float,
    memory_threshold: float,
    cooldown_minutes: int,
    detail: str | None = None,
) -> dict[str, Any] | None:
    if _is_in_cooldown(alert_key, cooldown_minutes):
        return None
    top_process, _ = _get_top_process_info()
    alert_delivery.deliver_spike_alert(
        resource=resource,
        value=value,
        threshold=threshold,
        cpu_percent=cpu_usage,
        memory_percent=memory_percent,
        cpu_threshold=cpu_threshold,
        memory_threshold=memory_threshold,
        top_process=top_process,
        uptime=_get_uptime_string(),
        os_info=_get_os_info_string(),
        detail=detail,
        alert_type=alert_key,
    )
    _update_cooldown(alert_key)
    alert = {
        "type": alert_key,
        "value": value,
        "threshold": threshold,
        "resource": resource,
    }
    logger.info("%s alert sent: %.1f%% >= %.1f%%", resource, value, threshold)
    return alert


def check_and_send_spike_alert(
    cpu_threshold: float | None = None,
    memory_threshold: float | None = None,
    disk_threshold: float | None = None,
    cooldown_minutes: int | None = None,
) -> list[dict[str, Any]] | None:
    """
    Check CPU, memory, disk, and swap. Send spike alerts via push/email wrapper.
    Email and push share cooldown per alert type to avoid spam.
    """
    settings = _alert_settings()
    cpu_threshold = float(settings["cpu_threshold"] if cpu_threshold is None else cpu_threshold)
    memory_threshold = float(settings["memory_threshold"] if memory_threshold is None else memory_threshold)
    disk_threshold = float(settings["disk_threshold"] if disk_threshold is None else disk_threshold)
    cooldown_minutes = int(settings["cooldown_minutes"] if cooldown_minutes is None else cooldown_minutes)

    if not alert_delivery.email_enabled() and not alert_delivery.push_enabled():
        logger.debug("No alert delivery configured (email or push required)")
        return None

    alerts_sent: list[dict[str, Any]] = []
    cpu_usage = get_cpu_usage()
    ram_status = get_ram_status()
    cpu_overall = cpu_usage.overall
    memory_percent = ram_status.percent

    if cpu_overall >= cpu_threshold:
        try:
            alert = _dispatch_spike(
                alert_key="cpu_spike",
                resource="CPU",
                value=cpu_overall,
                threshold=cpu_threshold,
                cpu_usage=cpu_overall,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                cooldown_minutes=cooldown_minutes,
            )
            if alert:
                alerts_sent.append(alert)
        except Exception as e:
            logger.error("CPU spike alert failed: %s", e)

    if memory_percent >= memory_threshold:
        try:
            alert = _dispatch_spike(
                alert_key="memory_spike",
                resource="Memory",
                value=memory_percent,
                threshold=memory_threshold,
                cpu_usage=cpu_overall,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                cooldown_minutes=cooldown_minutes,
            )
            if alert:
                alerts_sent.append(alert)
        except Exception as e:
            logger.error("Memory spike alert failed: %s", e)

    for disk in _disk_usage_alerts(disk_threshold):
        mount = disk["mountpoint"]
        percent = disk["percent"]
        alert_key = f"disk_spike:{mount}"
        try:
            alert = _dispatch_spike(
                alert_key=alert_key,
                resource=f"Disk {mount}",
                value=percent,
                threshold=disk_threshold,
                cpu_usage=cpu_overall,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                cooldown_minutes=cooldown_minutes,
                detail=f"{mount} is {percent:.1f}% full (threshold {disk_threshold:.1f}%).",
            )
            if alert:
                alert["mountpoint"] = mount
                alerts_sent.append(alert)
        except Exception as e:
            logger.error("Disk spike alert failed for %s: %s", mount, e)

    swap_percent = _swap_usage_percent()
    if swap_percent is not None and swap_percent >= memory_threshold:
        try:
            alert = _dispatch_spike(
                alert_key="swap_spike",
                resource="Swap",
                value=swap_percent,
                threshold=memory_threshold,
                cpu_usage=cpu_overall,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                cooldown_minutes=cooldown_minutes,
                detail=f"Swap usage is {swap_percent:.1f}% (threshold {memory_threshold:.1f}%).",
            )
            if alert:
                alerts_sent.append(alert)
        except Exception as e:
            logger.error("Swap spike alert failed: %s", e)

    return alerts_sent if alerts_sent else None


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
            "cpu_readings": [],
            "memory_readings": [],
            "disk_read_bytes": 0,
            "disk_write_bytes": 0,
            "disk_read_baseline": disk_io.read_bytes if disk_io else 0,
            "disk_write_baseline": disk_io.write_bytes if disk_io else 0,
            "net_sent_bytes": 0,
            "net_recv_bytes": 0,
            "alerts_count": 0,
            "last_alert_time": None,
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


def scheduled_spike_check() -> None:
    """Persistent-scheduler-safe monitoring job; reads thresholds from config."""
    try:
        collect_daily_stats()
        settings = _alert_settings()
        check_and_send_spike_alert(
            cpu_threshold=float(settings["cpu_threshold"]),
            memory_threshold=float(settings["memory_threshold"]),
            disk_threshold=float(settings["disk_threshold"]),
            cooldown_minutes=int(settings["cooldown_minutes"]),
        )
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
    from app.services import alert_history
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
        push_error: str | None = None
        push_delivered = 0
        try:
            push_delivered = send_push(
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
        except Exception as exc:
            push_error = str(exc)
            logger.warning("Alertmanager push delivery failed: %s", exc)
        alert_history.record_delivery(
            alert_kind="alertmanager",
            title=title,
            body=summary,
            push_attempted=True,
            push_delivered=push_delivered,
            push_error=push_error,
            alert_type=name,
            fingerprint=fingerprint,
            metadata={
                "status": status,
                "severity": severity,
                "labels": labels,
                "annotations": annotations,
            },
        )
        accepted += 1
        delivered += push_delivered
    return {"accepted": accepted, "delivered": delivered}


def send_daily_summary() -> Optional[Dict[str, Any]]:
    """Send daily system summary email to RECIPIENT_EMAIL (push is not used for summaries)."""
    from app.services.network import _format_bytes, _vnstat_run

    if not alert_delivery.email_enabled():
        logger.error("Daily summary skipped: Resend or RECIPIENT_EMAIL not configured")
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

        from app.services import alert_history

        alerts_count = alert_history.count_today(alert_kind="spike")
        last_alert_time = alert_history.last_delivery_time_today() or "Never"

        result = alert_delivery.deliver_daily_summary_email(
            device_name=platform.node(),
            cpu_avg=round(cpu_avg, 1),
            cpu_peak=round(cpu_peak, 1),
            memory_avg=round(memory_avg, 1),
            memory_peak=round(memory_peak, 1),
            disk_read=disk_read,
            disk_write=disk_write,
            net_sent=net_sent,
            net_recv=net_recv,
            uptime=_get_uptime_string(),
            os_info=_get_os_info_string(),
            top_processes=top_processes,
            alerts_count=alerts_count,
            last_alert_time=last_alert_time,
        )
        if result:
            logger.info("Daily summary sent to %s", alert_delivery.recipient_email())
        return result
    except Exception as e:
        logger.error("Daily summary failed: %s", e)
        return None


def get_system_stats_text() -> str:
    """Return a plain-text summary of current system stats (no email)."""
    from app.services.network import _format_bytes, _vnstat_run

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
        "── Disk ──",
    ]
    for disk in _disk_usage_alerts(0):
        lines.append(f"  {disk['mountpoint']}: {disk['percent']:.1f}% ({disk['filesystem']})")
    swap_percent = _swap_usage_percent()
    if swap_percent is not None:
        lines.extend(["", "── Swap ──", f"  Used: {swap_percent:.1f}%"])
    lines.extend([
        "",
        "── Network (vnstat) ──",
        f"  Today:  ↓ {_format_bytes(net_today.get('rx_bytes', 0))}  ↑ {_format_bytes(net_today.get('tx_bytes', 0))}",
        f"  Month:  ↓ {_format_bytes(net_month.get('rx_bytes', 0))}  ↑ {_format_bytes(net_month.get('tx_bytes', 0))}",
        "",
        "── Top Processes (CPU) ──",
    ])
    for p in top.by_cpu[:5]:
        lines.append(f"  {p.name:<20} CPU: {p.cpu_percent:6.1f}%  MEM: {p.memory_percent:5.1f}%")
    return "\n".join(lines)


def setup_monitoring_schedule(
    cpu_threshold: float | None = None,
    memory_threshold: float | None = None,
    spike_check_interval_minutes: int | None = None,
    daily_summary_time: str | None = None,
    alert_timezone: str | None = None,
) -> None:
    """Schedule spike monitoring and daily summary in the user's configured timezone."""
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    from app.services.scheduler import get_scheduler

    cfg = get_config()
    cpu_threshold = cfg.cpu_alert_threshold if cpu_threshold is None else cpu_threshold
    memory_threshold = cfg.memory_alert_threshold if memory_threshold is None else memory_threshold
    spike_check_interval_minutes = (
        cfg.spike_check_interval_minutes if spike_check_interval_minutes is None else spike_check_interval_minutes
    )
    daily_summary_time = cfg.daily_summary_time if daily_summary_time is None else daily_summary_time
    tz_name = cfg.alert_timezone if alert_timezone is None else alert_timezone
    tz = ZoneInfo(tz_name)

    scheduler = get_scheduler()

    scheduler.add_job(
        scheduled_spike_check,
        trigger=IntervalTrigger(minutes=spike_check_interval_minutes),
        id="vela_spike_monitor",
        name="Vela Spike Monitor",
        replace_existing=True,
    )

    hour, minute = map(int, daily_summary_time.split(":"))
    scheduler.add_job(
        scheduled_daily_summary,
        trigger=CronTrigger(hour=hour, minute=minute, timezone=tz),
        id="vela_daily_summary",
        name="Vela Daily Summary",
        replace_existing=True,
    )

    logger.info(
        "Monitoring scheduled: spikes every %smin (CPU≥%.0f%%, RAM≥%.0f%%, disk≥%.0f%%), "
        "daily summary at %s %s, email=%s push=%s",
        spike_check_interval_minutes,
        cpu_threshold,
        memory_threshold,
        cfg.disk_alert_threshold,
        daily_summary_time,
        tz_name,
        alert_delivery.recipient_email() or "(none)",
        alert_delivery.push_enabled(),
    )


def get_monitoring_status() -> Dict[str, Any]:
    from app.services import alert_history
    from app.services.network import _is_vnstat_available
    from app.services.scheduler import format_job_next_run, get_scheduler

    cfg = get_config()
    scheduler = get_scheduler()
    jobs = scheduler.get_jobs()
    spike_job = summary_job = None
    for job in jobs:
        if job.id == "vela_spike_monitor":
            spike_job = {"next_run": format_job_next_run(job)}
        elif job.id == "vela_daily_summary":
            summary_job = {
                "next_run": format_job_next_run(job),
                "timezone": cfg.alert_timezone,
                "local_time": cfg.daily_summary_time,
            }
    return {
        "scheduler_running": getattr(scheduler, "running", False),
        "spike_monitor": spike_job,
        "daily_summary": summary_job,
        "alerts_today": alert_history.count_today(alert_kind="spike"),
        "deliveries_stored": alert_history.count_deliveries(),
        "recipient_email": alert_delivery.recipient_email(),
        "email_configured": alert_delivery.email_enabled(),
        "push_configured": alert_delivery.push_enabled(),
        "thresholds": {
            "cpu_percent": cfg.cpu_alert_threshold,
            "memory_percent": cfg.memory_alert_threshold,
            "disk_percent": cfg.disk_alert_threshold,
            "cooldown_minutes": cfg.alert_cooldown_minutes,
        },
        "vnstat_available": _is_vnstat_available(),
    }


def __getattr__(name: str):
    """Backwards-compatible lazy accessors for legacy imports."""
    if name == "RECIPIENT_EMAIL":
        return alert_delivery.recipient_email()
    if name == "RESEND_AVAILABLE":
        return alert_delivery.email_enabled()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
