"""
API router for system alerts — no email prompts.
Email recipient is read from RECIPIENT_EMAIL in .env.
Spike monitoring and daily summary are auto-scheduled on startup.
"""

import logging
import hmac
from typing import Dict, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services import alert_delivery
from app.services.alerts import (
    check_and_send_spike_alert,
    send_daily_summary,
    get_system_stats_text,
    get_monitoring_status,
    DEFAULT_CPU_THRESHOLD,
    DEFAULT_MEMORY_THRESHOLD,
    handle_alertmanager_webhook,
)
from app.utils.config import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/webhook/alertmanager")
async def alertmanager_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
) -> Dict[str, int]:
    """Receive Alertmanager events and forward them to registered FCM devices."""
    secret = get_config().alertmanager_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Alertmanager webhook is not configured")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Alertmanager payload must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Alertmanager payload must be a JSON object")
    return handle_alertmanager_webhook(payload)


@router.get("/status")
def alert_status(current_user: str = Depends(get_current_user)):
    """Check monitoring status — scheduled jobs, alerts today, recipient email."""
    return get_monitoring_status()


@router.post("/spike/check")
def trigger_spike_check(
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD,
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD,
    current_user: str = Depends(get_current_user),
):
    """
    Manually check CPU/memory. Sends email alert if thresholds exceeded.
    Email recipient is read from RECIPIENT_EMAIL in .env (no prompt).
    """
    if not alert_delivery.email_enabled() and not alert_delivery.push_enabled():
        raise HTTPException(
            status_code=503,
            detail="Alerts not configured. Set push (FCM) and/or email (RESEND_API_KEY + RECIPIENT_EMAIL) in .env",
        )

    result = check_and_send_spike_alert(cpu_threshold=cpu_threshold, memory_threshold=memory_threshold)
    if result:
        return {"success": True, "message": f"{len(result)} alert(s) sent", "alerts": result}
    return {"success": True, "message": "No alerts — metrics within thresholds"}


@router.post("/summary/send")
def trigger_daily_summary(current_user: str = Depends(get_current_user)):
    """
    Send daily summary to RECIPIENT_EMAIL (from .env) right now.
    """
    if not alert_delivery.email_enabled():
        raise HTTPException(status_code=503, detail="Email not configured. Set RESEND_API_KEY and RECIPIENT_EMAIL in .env")

    result = send_daily_summary()
    if result:
        return {"success": True, "message": "Daily summary sent"}
    return {"success": False, "message": "Failed to send daily summary"}


@router.get("/test")
def send_test_alert(current_user: str = Depends(get_current_user)):
    """
    Send a test spike alert email to RECIPIENT_EMAIL (from .env).
    Always sends regardless of system metrics.
    """
    from app.utils.emails import send_spike_alert
    import platform

    if not alert_delivery.email_enabled():
        raise HTTPException(status_code=503, detail="Email not configured. Set RESEND_API_KEY and RECIPIENT_EMAIL in .env")

    recipient = alert_delivery.recipient_email()
    result = send_spike_alert(
        to=recipient,
        device_name=platform.node(),
        cpu_percent=0.0, memory_percent=0.0,
        cpu_threshold=85.0, memory_threshold=85.0,
        top_process="(test)", uptime="N/A", os_info="Test alert",
    )
    if result:
        return {"success": True, "message": f"Test email sent to {recipient}"}
    return {"success": False, "message": "Failed to send test email"}


# ── On-demand system stats ────────────────────────────────────────────────────

@router.get("/stats")
def system_stats(current_user: str = Depends(get_current_user)):
    """
    Return current system stats as plain text:
    CPU, memory, network (today/month via vnstat), top processes, uptime.
    """
    return {"stats": get_system_stats_text()}