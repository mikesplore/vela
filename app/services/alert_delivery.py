"""Unified alert delivery — email (rate-limited) and push notifications."""
from __future__ import annotations

import logging
import os
import platform
from typing import Any

from app.services import alert_history
from app.utils import emails

logger = logging.getLogger(__name__)


def recipient_email() -> str:
    return os.environ.get("RECIPIENT_EMAIL", "").strip()


def email_enabled() -> bool:
    return emails.is_configured() and bool(recipient_email())


def push_enabled() -> bool:
    try:
        from app.services.push import is_configured

        return is_configured()
    except Exception:
        return False


def deliver_spike_alert(
    *,
    resource: str,
    value: float,
    threshold: float,
    cpu_percent: float,
    memory_percent: float,
    cpu_threshold: float,
    memory_threshold: float,
    top_process: str,
    uptime: str,
    os_info: str,
    detail: str | None = None,
    alert_type: str | None = None,
    send_email: bool = True,
    send_push: bool = True,
) -> dict[str, Any]:
    """Send a spike alert via push and/or email. Email respects caller cooldown policy."""
    results: dict[str, Any] = {"email": None, "push_delivered": 0}
    device_name = platform.node()
    body = detail or f"{resource} is {value:.1f}% (threshold {threshold:.1f}%)."
    push_title = f"Vela alert · {resource} spike"
    email_subject = f"Vela alert · Spike detected on {device_name}"

    push_attempted = send_push and push_enabled()
    email_attempted = send_email and email_enabled()
    push_error: str | None = None
    email_error: str | None = None

    if push_attempted:
        try:
            from app.services.push import send_push

            results["push_delivered"] = send_push(
                title=push_title,
                body=body,
                data={
                    "source": "vela",
                    "alert_type": "spike",
                    "resource": resource.lower().replace(" ", "_"),
                    "value": f"{value:.1f}",
                    "threshold": f"{threshold:.1f}",
                },
            )
        except Exception as exc:
            push_error = str(exc)
            logger.warning("Push spike delivery failed: %s", exc)

    if email_attempted:
        try:
            results["email"] = emails.send_spike_alert(
                to=recipient_email(),
                device_name=device_name,
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                top_process=top_process,
                uptime=uptime,
                os_info=os_info,
            )
        except Exception as exc:
            email_error = str(exc)
            logger.warning("Email spike delivery failed: %s", exc)

    record_title = push_title if push_attempted else email_subject
    alert_history.record_delivery(
        alert_kind="spike",
        title=record_title,
        body=body,
        email_to=recipient_email() if email_attempted else None,
        email_result=results["email"] if isinstance(results["email"], dict) else None,
        email_error=email_error,
        email_attempted=email_attempted,
        push_attempted=push_attempted,
        push_delivered=int(results["push_delivered"] or 0),
        push_error=push_error,
        alert_type=alert_type or resource.lower().replace(" ", "_"),
        value=value,
        threshold=threshold,
        resource=resource,
        metadata={
            "email_subject": email_subject,
            "push_title": push_title,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "cpu_threshold": cpu_threshold,
            "memory_threshold": memory_threshold,
            "top_process": top_process,
            "uptime": uptime,
            "os_info": os_info,
            "device_name": device_name,
        },
    )

    return results


def deliver_daily_summary_email(**kwargs: Any) -> dict | None:
    """Send the daily summary email only (never push — avoids duplicate noise)."""
    if not email_enabled():
        logger.info("Daily summary email skipped: Resend or RECIPIENT_EMAIL not configured")
        return None

    device_name = str(kwargs.get("device_name") or platform.node())
    email_subject = f"Vela Operations · Daily summary for {device_name}"
    email_error: str | None = None
    result: dict | None = None
    try:
        result = emails.send_daily_summary(to=recipient_email(), **kwargs)
    except Exception as exc:
        email_error = str(exc)
        logger.warning("Daily summary email failed: %s", exc)

    summary_body = (
        f"CPU avg {kwargs.get('cpu_avg', 0):.1f}% · peak {kwargs.get('cpu_peak', 0):.1f}% · "
        f"Memory avg {kwargs.get('memory_avg', 0):.1f}% · peak {kwargs.get('memory_peak', 0):.1f}%"
    )
    alert_history.record_delivery(
        alert_kind="daily_summary",
        title=email_subject,
        body=summary_body,
        email_to=recipient_email(),
        email_result=result if isinstance(result, dict) else None,
        email_error=email_error,
        email_attempted=True,
        push_attempted=False,
        metadata={
            "email_subject": email_subject,
            "device_name": device_name,
            "cpu_avg": kwargs.get("cpu_avg"),
            "cpu_peak": kwargs.get("cpu_peak"),
            "memory_avg": kwargs.get("memory_avg"),
            "memory_peak": kwargs.get("memory_peak"),
            "disk_read": kwargs.get("disk_read"),
            "disk_write": kwargs.get("disk_write"),
            "net_sent": kwargs.get("net_sent"),
            "net_recv": kwargs.get("net_recv"),
            "alerts_count": kwargs.get("alerts_count"),
            "last_alert_time": kwargs.get("last_alert_time"),
            "top_processes": kwargs.get("top_processes"),
            "uptime": kwargs.get("uptime"),
            "os_info": kwargs.get("os_info"),
        },
    )
    return result


def deliver_test_spike_email(
    *,
    cpu_percent: float = 0.0,
    memory_percent: float = 0.0,
    cpu_threshold: float = 85.0,
    memory_threshold: float = 85.0,
    top_process: str = "(test)",
    uptime: str = "N/A",
    os_info: str = "Test alert",
) -> dict | None:
    """Send a test spike email and record it in delivery history."""
    if not email_enabled():
        return None

    device_name = platform.node()
    email_subject = f"Vela alert · Spike detected on {device_name}"
    email_error: str | None = None
    result: dict | None = None
    try:
        result = emails.send_spike_alert(
            to=recipient_email(),
            device_name=device_name,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            cpu_threshold=cpu_threshold,
            memory_threshold=memory_threshold,
            top_process=top_process,
            uptime=uptime,
            os_info=os_info,
        )
    except Exception as exc:
        email_error = str(exc)
        logger.warning("Test spike email failed: %s", exc)

    alert_history.record_delivery(
        alert_kind="test",
        title=email_subject,
        body="Manual test spike alert email.",
        email_to=recipient_email(),
        email_result=result if isinstance(result, dict) else None,
        email_error=email_error,
        email_attempted=True,
        push_attempted=False,
        alert_type="test",
        metadata={
            "email_subject": email_subject,
            "device_name": device_name,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "cpu_threshold": cpu_threshold,
            "memory_threshold": memory_threshold,
            "top_process": top_process,
            "uptime": uptime,
            "os_info": os_info,
        },
    )
    return result
