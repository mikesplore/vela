"""Unified alert delivery — email (rate-limited) and push notifications."""
from __future__ import annotations

import logging
import os
import platform
from typing import Any

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
    send_email: bool = True,
    send_push: bool = True,
) -> dict[str, Any]:
    """Send a spike alert via push and/or email. Email respects caller cooldown policy."""
    results: dict[str, Any] = {"email": None, "push_delivered": 0}

    body = detail or f"{resource} is {value:.1f}% (threshold {threshold:.1f}%)."

    if send_push and push_enabled():
        try:
            from app.services.push import send_push

            results["push_delivered"] = send_push(
                title=f"Vela alert · {resource} spike",
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
            logger.warning("Push spike delivery failed: %s", exc)

    if send_email and email_enabled():
        try:
            results["email"] = emails.send_spike_alert(
                to=recipient_email(),
                device_name=platform.node(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                cpu_threshold=cpu_threshold,
                memory_threshold=memory_threshold,
                top_process=top_process,
                uptime=uptime,
                os_info=os_info,
            )
        except Exception as exc:
            logger.warning("Email spike delivery failed: %s", exc)

    return results


def deliver_daily_summary_email(**kwargs: Any) -> dict | None:
    """Send the daily summary email only (never push — avoids duplicate noise)."""
    if not email_enabled():
        logger.info("Daily summary email skipped: Resend or RECIPIENT_EMAIL not configured")
        return None
    try:
        return emails.send_daily_summary(to=recipient_email(), **kwargs)
    except Exception as exc:
        logger.warning("Daily summary email failed: %s", exc)
        return None
