"""
API router for system alerts — no email prompts.
Email recipient is read from RECIPIENT_EMAIL in .env.
Spike monitoring and daily summary are auto-scheduled on startup.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services.alerts import (
    check_and_send_spike_alert,
    send_daily_summary,
    get_system_stats_text,
    get_monitoring_status,
    check_vnstat_installation,
    get_vnstat_data,
    RECIPIENT_EMAIL,
    DEFAULT_CPU_THRESHOLD,
    DEFAULT_MEMORY_THRESHOLD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


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
    from app.services.alerts import RESEND_AVAILABLE
    if not RESEND_AVAILABLE or not RECIPIENT_EMAIL:
        raise HTTPException(status_code=503, detail="Email not configured. Set RESEND_API_KEY and RECIPIENT_EMAIL in .env")

    result = check_and_send_spike_alert(cpu_threshold=cpu_threshold, memory_threshold=memory_threshold)
    if result:
        return {"success": True, "message": f"{len(result)} alert(s) sent", "alerts": result}
    return {"success": True, "message": "No alerts — metrics within thresholds"}


@router.post("/summary/send")
def trigger_daily_summary(current_user: str = Depends(get_current_user)):
    """
    Send daily summary to RECIPIENT_EMAIL (from .env) right now.
    """
    from app.services.alerts import RESEND_AVAILABLE
    if not RESEND_AVAILABLE or not RECIPIENT_EMAIL:
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
    from app.services.alerts import RESEND_AVAILABLE
    import platform

    if not RESEND_AVAILABLE or not RECIPIENT_EMAIL:
        raise HTTPException(status_code=503, detail="Email not configured. Set RESEND_API_KEY and RECIPIENT_EMAIL in .env")

    result = send_spike_alert(
        to=RECIPIENT_EMAIL,
        device_name=platform.node(),
        cpu_percent=0.0, memory_percent=0.0,
        cpu_threshold=80.0, memory_threshold=85.0,
        top_process="(test)", uptime="N/A", os_info="Test alert",
    )
    if result:
        return {"success": True, "message": f"Test email sent to {RECIPIENT_EMAIL}"}
    return {"success": False, "message": "Failed to send test email"}


# ── vnstat endpoints (daily, monthly, hourly) ──────────────────────────────────

@router.get("/vnstat")
def vnstat_status(current_user: str = Depends(get_current_user)):
    """Check if vnstat is installed and configured."""
    return check_vnstat_installation()


@router.get("/vnstat/data")
def network_usage(
    period: str = "day",
    interface: str | None = None,
    current_user: str = Depends(get_current_user),
):
    """
    Get network usage from vnstat.
    period: 'day' (today), 'month' (this month), 'hour' (current hour)
    """
    try:
        return get_vnstat_data(period=period, interface=interface)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── On-demand system stats ────────────────────────────────────────────────────

@router.get("/stats")
def system_stats(current_user: str = Depends(get_current_user)):
    """
    Return current system stats as plain text:
    CPU, memory, network (today/month via vnstat), top processes, uptime.
    """
    return {"stats": get_system_stats_text()}