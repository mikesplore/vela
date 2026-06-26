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
    high: Optional[float]
    critical: Optional[float]


class FanEntry(BaseModel):
    sensor: str
    speed_rpm: Optional[int]


class BatteryInfo(BaseModel):
    percent: Optional[float]
    plugged_in: Optional[bool]
    secs_left: Optional[int]


class SingleBatteryHealth(BaseModel):
    name: str
    path: str
    present: bool
    cycle_count: Optional[int]
    design_capacity_wh: Optional[float]
    current_max_capacity_wh: Optional[float]
    health_percent: Optional[float]
    manufacturer: Optional[str]
    model_name: Optional[str]
    serial_number: Optional[str]
    technology: Optional[str]
    voltage_now_uv: Optional[int]
    charge_control_start_threshold: Optional[int]
    charge_control_stop_threshold: Optional[int]


class BatteryHealthInfo(BaseModel):
    """Aggregated battery health across all detected batteries."""

    batteries: List[SingleBatteryHealth]
    total_cycle_count: Optional[int]
    overall_health_percent: Optional[float]


class ProcessInfo(BaseModel):
    pid: int
    name: str
    username: Optional[str]
    cpu_percent: float
    memory_percent: float
    memory_rss: int


class ProcessMetrics(BaseModel):
    top_by_cpu: List[ProcessInfo]
    top_by_memory: List[ProcessInfo]
