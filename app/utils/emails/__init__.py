"""
Email notification module for Vela system alerts and daily summaries.
Uses Resend API to send emails. HTML templates are managed on the Resend side.
"""

import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Try to import resend; gracefully handle if not installed
try:
    import resend
    RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
    resend.api_key = RESEND_API_KEY
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    logger.warning("resend package not installed. Install it with: pip install resend")

FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Vela <alerts@yourdomain.com>")


def is_configured() -> bool:
    """Check if Resend API key is set and resend package is installed."""
    return RESEND_AVAILABLE and bool(os.environ.get("RESEND_API_KEY", ""))


def send_spike_alert(
    to: str,
    device_name: str,
    cpu_percent: float,
    memory_percent: float,
    cpu_threshold: float,
    memory_threshold: float,
    top_process: str,
    uptime: str,
    os_info: str,

) -> dict | None:
    """
    Send a spike alert email when CPU or memory usage exceeds thresholds.
    HTML template is managed on Resend (not stored locally).

    Args:
        to: Recipient email address
        device_name: Name of the monitored device
        cpu_percent: Current CPU usage percentage
        memory_percent: Current memory usage percentage
        cpu_threshold: CPU threshold that was exceeded
        memory_threshold: Memory threshold that was exceeded
        top_process: Name of the top CPU-consuming process
        uptime: System uptime string
        os_info: Operating system information

    Returns:
        dict | None: Resend API response, or None if not configured
    """
    if not is_configured():
        logger.warning("Resend not configured — spike alert not sent")
        return None

    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to,
        "subject": f"⚠ Spike detected on {device_name}",
        "html": f"<p>Device: {device_name}<br>CPU: {cpu_percent:.1f}%<br>Memory: {memory_percent:.1f}%<br>Top Process: {top_process}</p>",
    })


def send_daily_summary(
    to: str,
    device_name: str,
    cpu_avg: float,
    cpu_peak: float,
    memory_avg: float,
    memory_peak: float,
    disk_read: str,
    disk_write: str,
    net_sent: str,
    net_recv: str,
    uptime: str,
    os_info: str,
    top_processes: list[dict],
    alerts_count: int,
    last_alert_time: str,
) -> dict | None:
    """
    Send a daily summary email with system usage statistics.
    HTML template is managed on Resend (not stored locally).

    Args:
        to: Recipient email address
        device_name: Name of the monitored device
        cpu_avg: Average CPU usage for the day
        cpu_peak: Peak CPU usage for the day
        memory_avg: Average memory usage for the day
        memory_peak: Peak memory usage for the day
        disk_read: Total disk read data (human-readable)
        disk_write: Total disk write data (human-readable)
        net_sent: Total network data sent (human-readable)
        net_recv: Total network data received (human-readable)
        uptime: System uptime string
        os_info: Operating system information
        top_processes: List of top CPU-consuming processes
        alerts_count: Number of alerts triggered today
        last_alert_time: Time of the last alert

    Returns:
        dict | None: Resend API response, or None if not configured
    """
    if not is_configured():
        logger.warning("Resend not configured — daily summary not sent")
        return None

    procs = top_processes[:3]
    while len(procs) < 3:
        procs.append({"name": "—", "cpu": 0.0})

    top_procs_text = ", ".join(f"{p['name']} ({p['cpu']:.1f}%)" for p in procs)

    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to,
        "subject": f"Vela daily summary — {device_name}",
        "html": (
            f"<p><b>Device:</b> {device_name}<br>"
            f"<b>Date:</b> {datetime.now().strftime('%d %b %Y')}<br><br>"
            f"<b>CPU:</b> Avg {cpu_avg:.1f}% / Peak {cpu_peak:.1f}%<br>"
            f"<b>Memory:</b> Avg {memory_avg:.1f}% / Peak {memory_peak:.1f}%<br>"
            f"<b>Disk:</b> R: {disk_read} / W: {disk_write}<br>"
            f"<b>Network (vnstat):</b> Sent {net_sent} / Recv {net_recv}<br>"
            f"<b>Top processes:</b> {top_procs_text}<br><br>"
            f"<b>Alerts today:</b> {alerts_count}<br>"
            f"<b>Last alert:</b> {last_alert_time}<br>"
            f"<b>Uptime:</b> {uptime}<br>"
            f"<b>OS:</b> {os_info}</p>"
        ),
    })