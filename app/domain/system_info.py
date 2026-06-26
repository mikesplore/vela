from typing import Optional

from pydantic import BaseModel


class CPUInfo(BaseModel):
    model: str
    physical_cores: int
    logical_cores: int
    base_freq_mhz: Optional[float]
    architecture: str


class RAMInfo(BaseModel):
    total: int
    available: int
    used: int
    percent: float
    swap_total: int
    swap_used: int
    swap_free: int
    swap_percent: float


class GPUInfo(BaseModel):
    name: str
    vram_total_mb: Optional[int]
    driver: Optional[str]
    vendor: Optional[str]


class DiskPartitionInfo(BaseModel):
    mountpoint: str
    total: int
    used: int
    free: int
    percent: float
    filesystem: str


class OSInfo(BaseModel):
    os_name: str
    os_version: str
    kernel: str
    hostname: str
    user: str
    uptime_seconds: int


class USBDevice(BaseModel):
    bus: str
    device: str
    id: str
    description: str


class MonitorInfo(BaseModel):
    name: str
    resolution: str
    refresh_rate: Optional[float]


class BIOSInfo(BaseModel):
    vendor: Optional[str]
    version: Optional[str]
    release_date: Optional[str]
    motherboard: Optional[str]