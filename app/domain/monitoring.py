from typing import List, Optional

from pydantic import BaseModel


class CPUUsage(BaseModel):
    overall: float
    per_core: List[float]


class DiskIOMetric(BaseModel):
    device: str
    read_bytes_per_sec: float
    write_bytes_per_sec: float


class NetworkIOMetric(BaseModel):
    interface: str
    bytes_sent_per_sec: float
    bytes_recv_per_sec: float


class TemperatureEntry(BaseModel):
    sensor: str
    label: str
    current: float
    high: Optional[float] = None
    critical: Optional[float] = None


class BatteryInfo(BaseModel):
    percent: Optional[float]
    plugged_in: Optional[bool]
    secs_left: Optional[int]


class FanEntry(BaseModel):
    sensor: str
    speed_rpm: Optional[float]


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    memory_mb: float


class ProcessMetrics(BaseModel):
    by_cpu: List[ProcessInfo]
    by_memory: List[ProcessInfo]


class SingleBatteryHealth(BaseModel):
    name: str
    present: bool
    cycle_count: Optional[int] = None
    design_capacity_wh: Optional[float] = None
    current_capacity_wh: Optional[float] = None


class BatteryHealthInfo(BaseModel):
    batteries: List[SingleBatteryHealth]
    total_cycle_count: Optional[int] = None
    average_health: Optional[float] = None


class UptimeInfo(BaseModel):
    """Human-readable system uptime."""
    seconds: int
    minutes: int
    hours: int
    days: int
    formatted: str