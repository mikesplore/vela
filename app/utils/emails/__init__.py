"""
Email notification module for Vela system alerts and daily summaries.
Uses Resend API to send emails. HTML templates are managed on the Resend side.
"""

import os
from datetime import datetime
from html import escape
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


def _text(value: object) -> str:
    return escape(str(value), quote=True)


def _layout(*, eyebrow: str, title: str, subtitle: str, content: str, accent: str = "#4F7CFF") -> str:
    """A compact, table-based email shell matching the Operations dashboard."""
    return f"""<!doctype html>
<html lang="en">
<body style="margin:0;padding:0;background:#F3F6FC;color:#E8ECF4;font-family:Inter,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#F3F6FC;padding:32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#171C26;border:1px solid #2A3344;border-radius:12px;overflow:hidden;">
        <tr><td style="padding:20px 24px;border-bottom:1px solid #2A3344;">
          <table role="presentation" cellspacing="0" cellpadding="0"><tr>
            <td style="width:18px;height:18px;background:{accent};border-radius:5px;"></td>
            <td style="padding-left:10px;color:#8B95A8;font-family:monospace;font-size:11px;font-weight:600;letter-spacing:1px;text-transform:uppercase;">Vela Operations · {_text(eyebrow)}</td>
          </tr></table>
        </td></tr>
        <tr><td style="padding:24px;">
          <h1 style="margin:0;color:#E8ECF4;font-size:22px;line-height:28px;">{_text(title)}</h1>
          <p style="margin:7px 0 20px;color:#8B95A8;font-size:13px;line-height:20px;">{_text(subtitle)}</p>
          {content}
        </td></tr>
        <tr><td style="padding:16px 24px;border-top:1px solid #2A3344;color:#5C667A;font-size:11px;line-height:16px;">
          Sent by Vela · Local device monitoring
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _metric(label: str, value: str, color: str = "#E8ECF4") -> str:
    return f"""<td width="50%" style="padding:8px;">
  <div style="background:#1D2430;border:1px solid #2A3344;border-radius:9px;padding:12px;">
    <div style="color:#8B95A8;font-family:monospace;font-size:10px;letter-spacing:.5px;text-transform:uppercase;">{_text(label)}</div>
    <div style="margin-top:5px;color:{color};font-size:17px;font-weight:700;">{_text(value)}</div>
  </div>
</td>"""


def _detail_row(label: str, value: object) -> str:
    return f"""<tr>
  <td style="padding:8px 0;color:#8B95A8;font-size:12px;border-bottom:1px solid #2A3344;">{_text(label)}</td>
  <td style="padding:8px 0;color:#E8ECF4;font-family:monospace;font-size:12px;text-align:right;border-bottom:1px solid #2A3344;">{_text(value)}</td>
</tr>"""


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
        "subject": f"Vela alert · Spike detected on {device_name}",
        "html": _layout(
            eyebrow="System alert",
            title="Resource spike detected",
            subtitle=f"{device_name} exceeded its configured monitoring threshold.",
            accent="#F07178",
            content=f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>
              {_metric("CPU", f"{cpu_percent:.1f}%", "#F07178")}
              {_metric("Memory", f"{memory_percent:.1f}%", "#F07178")}
            </tr></table>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px;">
              {_detail_row("CPU threshold", f"{cpu_threshold:.1f}%")}
              {_detail_row("Memory threshold", f"{memory_threshold:.1f}%")}
              {_detail_row("Top process", top_process)}
              {_detail_row("Uptime", uptime)}
              {_detail_row("System", os_info)}
            </table>""",
        ),
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

    process_rows = "".join(
        _detail_row(f"Process {index + 1}", f"{process.get('name', '—')} · {float(process.get('cpu', 0)):.1f}%")
        for index, process in enumerate(procs)
    )

    return resend.Emails.send({
        "from": FROM_EMAIL,
        "to": to,
        "subject": f"Vela Operations · Daily summary for {device_name}",
        "html": _layout(
            eyebrow="Daily report",
            title="System summary",
            subtitle=f"{device_name} · {datetime.now().strftime('%d %b %Y')}",
            content=f"""<table role="presentation" width="100%" cellspacing="0" cellpadding="0">
              <tr>{_metric("CPU average", f"{cpu_avg:.1f}%")}{_metric("CPU peak", f"{cpu_peak:.1f}%", "#E6B450")}</tr>
              <tr>{_metric("Memory average", f"{memory_avg:.1f}%")}{_metric("Memory peak", f"{memory_peak:.1f}%", "#E6B450")}</tr>
            </table>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px;">
              {_detail_row("Disk I/O", f"Read {disk_read} · Write {disk_write}")}
              {_detail_row("Network", f"Sent {net_sent} · Received {net_recv}")}
              {_detail_row("Alerts today", alerts_count)}
              {_detail_row("Last alert", last_alert_time)}
              {_detail_row("Uptime", uptime)}
              {_detail_row("System", os_info)}
            </table>
            <div style="margin:18px 0 8px;color:#8B95A8;font-family:monospace;font-size:10px;letter-spacing:.5px;text-transform:uppercase;">Top processes</div>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">{process_rows}</table>""",
        ),
    })