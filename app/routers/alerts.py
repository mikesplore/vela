"""
API router for system alerts and monitoring management.
Provides endpoints to configure, control, and monitor CPU/memory spike alerts and daily summaries.
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.domain.alerts import AlertStatus, VnstatStatus
from app.services.alerts import (
    check_and_send_spike_alert,
    send_daily_summary,
    setup_monitoring_schedule,
    get_monitoring_status,
    check_vnstat_installation,
    DEFAULT_CPU_THRESHOLD,
    DEFAULT_MEMORY_THRESHOLD,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


class SetupMonitoringRequest(BaseModel):
    """Request body for setting up monitoring."""
    recipient_email: str
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD
    spike_check_interval_minutes: int = 5
    daily_summary_time: str = "18:00"
    network_interface: str | None = None


class SpikeCheckRequest(BaseModel):
    """Request body for triggering a spike check."""
    recipient_email: str
    cpu_threshold: float = DEFAULT_CPU_THRESHOLD
    memory_threshold: float = DEFAULT_MEMORY_THRESHOLD


class SummaryRequest(BaseModel):
    """Request body for triggering a daily summary."""
    recipient_email: str


class TestAlertRequest(BaseModel):
    """Request body for sending a test alert email."""
    recipient_email: str


@router.post("/setup", response_model=Dict[str, Any])
def setup_monitoring(
    request: SetupMonitoringRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Set up system monitoring with spike alerts and daily summaries.
    
    This will:
    - Schedule periodic checks for CPU and memory spikes
    - Schedule a daily summary email at the specified time
    - Send spike alerts immediately when thresholds are exceeded
    
    **Thresholds:**
    - CPU threshold: Percentage above which an alert is triggered (default: 80%)
    - Memory threshold: Percentage above which an alert is triggered (default: 85%)
    """
    try:
        setup_monitoring_schedule(
            recipient_email=request.recipient_email,
            cpu_threshold=request.cpu_threshold,
            memory_threshold=request.memory_threshold,
            spike_check_interval_minutes=request.spike_check_interval_minutes,
            daily_summary_time=request.daily_summary_time,
            network_interface=request.network_interface,
        )
        
        return {
            "success": True,
            "message": "Monitoring scheduled successfully",
            "config": {
                "recipient_email": request.recipient_email,
                "cpu_threshold": request.cpu_threshold,
                "memory_threshold": request.memory_threshold,
                "spike_check_interval_minutes": request.spike_check_interval_minutes,
                "daily_summary_time": request.daily_summary_time,
                "network_interface": request.network_interface or "auto-detect",
            }
        }
    except Exception as e:
        logger.error(f"Failed to setup monitoring: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup monitoring: {str(e)}"
        )


@router.get("/status", response_model=AlertStatus)
def get_alert_status(current_user: str = Depends(get_current_user)):
    """
    Get current monitoring status including scheduled jobs and system health.
    """
    try:
        status_data = get_monitoring_status()
        return AlertStatus(**status_data)
    except Exception as e:
        logger.error(f"Failed to get monitoring status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get monitoring status: {str(e)}"
        )


@router.post("/spike/check")
def trigger_spike_check(
    request: SpikeCheckRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Manually trigger an immediate spike check.
    
    This will check current CPU and memory usage and send alerts if thresholds are exceeded.
    Useful for testing or on-demand monitoring.
    """
    try:
        from app.services.alerts import RESEND_AVAILABLE
        
        if not RESEND_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="resend package not installed. Email alerts are disabled."
            )
        
        result = check_and_send_spike_alert(
            recipient_email=request.recipient_email,
            cpu_threshold=request.cpu_threshold,
            memory_threshold=request.memory_threshold,
        )
        
        if result:
            return {
                "success": True,
                "message": f"Spike check completed. {len(result)} alert(s) sent.",
                "alerts": result,
            }
        else:
            return {
                "success": True,
                "message": "Spike check completed. No alerts needed (all metrics within thresholds).",
                "alerts": [],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger spike check: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger spike check: {str(e)}"
        )


@router.post("/summary/send")
def trigger_daily_summary(
    request: SummaryRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Manually trigger an immediate daily summary email.
    
    This will collect current system statistics and send a summary report.
    Useful for testing or on-demand reports.
    """
    try:
        from app.services.alerts import RESEND_AVAILABLE
        
        if not RESEND_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="resend package not installed. Email alerts are disabled."
            )
        
        result = send_daily_summary(recipient_email=request.recipient_email)
        
        if result:
            return {
                "success": True,
                "message": "Daily summary sent successfully",
            }
        else:
            return {
                "success": False,
                "message": "Failed to send daily summary. Check logs for details.",
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger daily summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger daily summary: {str(e)}"
        )


@router.get("/vnstat", response_model=VnstatStatus)
def get_vnstat_status(current_user: str = Depends(get_current_user)):
    """
    Check vnstat installation and configuration status.
    
    vnstat is required for network data usage tracking in daily summaries.
    This endpoint helps diagnose if vnstat is properly installed and which
    network interfaces are available.
    """
    try:
        status_data = check_vnstat_installation()
        return VnstatStatus(**status_data)
    except Exception as e:
        logger.error(f"Failed to check vnstat status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check vnstat status: {str(e)}"
        )


@router.get("/vnstat/data")
def get_network_usage(
    interface: str | None = None,
    current_user: str = Depends(get_current_user),
):
    """
    Get current network usage data from vnstat.
    
    Returns received (rx) and transmitted (tx) data for the specified interface,
    or the default interface if not specified.
    """
    try:
        from app.services.alerts import _get_vnstat_data, _format_bytes, _get_default_interface
        
        if not interface:
            interface = _get_default_interface()
        
        data = _get_vnstat_data(interface)
        
        return {
            "success": True,
            "interface": interface,
            "received": _format_bytes(data.get("rx_bytes", 0)),
            "transmitted": _format_bytes(data.get("tx_bytes", 0)),
            "received_bytes": data.get("rx_bytes", 0),
            "transmitted_bytes": data.get("tx_bytes", 0),
        }
    except Exception as e:
        logger.error(f"Failed to get network usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get network usage: {str(e)}"
        )


@router.get("/resend/status")
def get_resend_status(current_user: str = Depends(get_current_user)):
    """
    Check if the resend package is available and configured.
    """
    try:
        from app.utils import emails
        configured = emails.is_configured()
        
        return {
            "configured": configured,
            "message": (
                "Resend is configured and ready" 
                if configured 
                else "RESEND_API_KEY not set in .env — email alerts are disabled"
            )
        }
    except Exception as e:
        logger.error(f"Failed to check resend status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check resend status: {str(e)}"
        )


@router.post("/test")
def send_test_alert(
    request: TestAlertRequest,
    current_user: str = Depends(get_current_user),
):
    """
    Send a test spike alert email immediately to verify Resend configuration.
    
    This sends an alert regardless of current system metrics — purely for testing.
    If it works, your Resend setup is correct.
    """
    try:
        from app.utils.emails import send_spike_alert
        from app.services.alerts import RESEND_AVAILABLE
        
        if not RESEND_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RESEND_API_KEY not set or resend package not installed."
            )
        
        import platform
        result = send_spike_alert(
            to=request.recipient_email,
            device_name=platform.node(),
            cpu_percent=0.0,
            memory_percent=0.0,
            cpu_threshold=80.0,
            memory_threshold=85.0,
            top_process="(test message)",
            uptime="N/A",
            os_info="Test alert — no actual spike",
        )
        
        if result:
            return {
                "success": True,
                "message": f"Test alert sent to {request.recipient_email}. Check your inbox.",
                "result": result,
            }
        else:
            return {
                "success": False,
                "message": "Failed to send test alert. Check logs for details.",
            }
    except Exception as e:
        logger.error(f"Failed to send test alert: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send test alert: {str(e)}"
        )
