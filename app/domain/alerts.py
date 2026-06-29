"""
Domain models for the alerts/notification monitoring system.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class AlertConfig(BaseModel):
    """Configuration for system monitoring alerts."""
    recipient_email: str = Field(..., description="Email address to receive alerts and daily summaries")
    cpu_threshold: float = Field(
        default=80.0, 
        ge=0, 
        le=100, 
        description="CPU usage percentage threshold for spike alerts (default: 80%)"
    )
    memory_threshold: float = Field(
        default=85.0, 
        ge=0, 
        le=100, 
        description="Memory usage percentage threshold for spike alerts (default: 85%)"
    )
    spike_check_interval_minutes: int = Field(
        default=5,
        ge=1,
        le=60,
        description="How often to check for CPU/memory spikes (default: 5 minutes)"
    )
    daily_summary_time: str = Field(
        default="18:00",
        pattern=r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$",
        description="Time to send daily summary in HH:MM format (default: 18:00)"
    )
    network_interface: Optional[str] = Field(
        default=None,
        description="Network interface for vnstat (auto-detected if not specified)"
    )


class AlertStatus(BaseModel):
    """Current status of the monitoring system."""
    spike_monitor: Optional[Dict[str, Any]] = None
    daily_summary: Optional[Dict[str, Any]] = None
    alerts_today: int = 0
    vnstat_available: bool = False


class VnstatStatus(BaseModel):
    """Status of vnstat installation and configuration."""
    installed: bool = False
    version: Optional[str] = None
    interfaces: List[str] = []
    default_interface: Optional[str] = None
    errors: List[str] = []


class AlertHistoryEntry(BaseModel):
    """A single alert history entry."""
    type: str
    value: float
    threshold: float
    date: str
    time: str


class AlertHistoryResponse(BaseModel):
    """Response containing alert history."""
    alerts: List[AlertHistoryEntry]
    total_count: int
    today_count: int