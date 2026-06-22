import os
import platform
import re
import subprocess
import pwd
from datetime import datetime
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies import get_current_user

router = APIRouter(prefix="/system", tags=["system_info"], dependencies=[Depends(get_current_user)])


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


def _run_command(cmd: List[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


def _get_cpu_model() -> str:
    cpu_model = "unknown"
    if os.path.exists("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.startswith("model name") or line.startswith("Processor"):
                        cpu_model = line.split(":", 1)[1].strip()
                        return cpu_model
        except OSError:
            pass
    return platform.processor() or platform.machine() or cpu_model


def _get_cpu_info() -> CPUInfo:
    return CPUInfo(
        model=_get_cpu_model(),
        physical_cores=psutil.cpu_count(logical=False) or 0,
        logical_cores=psutil.cpu_count(logical=True) or 0,
        base_freq_mhz=psutil.cpu_freq().max if psutil.cpu_freq() else None,
        architecture=platform.machine(),
    )


def _get_ram_info() -> RAMInfo:
    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return RAMInfo(
        total=virtual.total,
        available=virtual.available,
        used=virtual.used,
        percent=virtual.percent,
        swap_total=swap.total,
        swap_used=swap.used,
        swap_free=swap.free,
        swap_percent=swap.percent,
    )


def _parse_lspci() -> List[GPUInfo]:
    output = _run_command(["lspci", "-nnk"])
    if not output:
        return []

    gpus: List[GPUInfo] = []
    for line in output.splitlines():
        if "VGA compatible controller" in line or "3D controller" in line:
            vendor_match = re.search(r"\] (.*?)(?: \(|$)", line)
            vendor = vendor_match.group(1).strip() if vendor_match else line.split(":", 1)[1].strip()
            name = line.split(":", 1)[1].strip()
            gpus.append(GPUInfo(name=name, vram_total_mb=None, driver=None, vendor=vendor))
    return gpus


def _parse_nvidia_smi() -> List[GPUInfo]:
    output = _run_command([
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ])
    if not output:
        return []

    gpus: List[GPUInfo] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            name, memory_total, driver = parts[0], parts[1], parts[2]
            memory_mb = int(memory_total) if memory_total.isdigit() else None
            gpus.append(GPUInfo(name=name, vram_total_mb=memory_mb, driver=driver, vendor="NVIDIA"))
    return gpus


def _get_gpu_info() -> List[GPUInfo]:
    gpus = _parse_nvidia_smi()
    if gpus:
        return gpus
    return _parse_lspci()


def _get_disk_info() -> List[DiskPartitionInfo]:
    partitions: List[DiskPartitionInfo] = []
    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            partitions.append(
                DiskPartitionInfo(
                    mountpoint=partition.mountpoint,
                    total=usage.total,
                    used=usage.used,
                    free=usage.free,
                    percent=usage.percent,
                    filesystem=partition.fstype,
                )
            )
        except OSError:
            continue
    return partitions


def _get_os_info() -> OSInfo:
    uname = platform.uname()
    return OSInfo(
        os_name=platform.system(),
        os_version=platform.version(),
        kernel=uname.release,
        hostname=uname.node,
        user=pwd.getpwuid(os.getuid()).pw_name,
        uptime_seconds=int(datetime.now().timestamp() - psutil.boot_time()),
    )


def _get_usb_devices() -> List[USBDevice]:
    output = _run_command(["lsusb"])
    devices: List[USBDevice] = []
    for line in output.splitlines():
        match = re.match(r"Bus (\d{3}) Device (\d{3}): ID ([0-9a-fA-F:]+) (.*)$", line)
        if match:
            bus, device, bus_id, desc = match.groups()
            devices.append(USBDevice(bus=bus, device=device, id=bus_id, description=desc))
    return devices


def _get_monitors() -> List[MonitorInfo]:
    output = _run_command(["xrandr", "--query"])
    monitors: List[MonitorInfo] = []
    if not output:
        return monitors

    current_name: Optional[str] = None
    for line in output.splitlines():
        parts = line.split()
        if " connected " in line:
            current_name = parts[0]
            resolution = "unknown"
            refresh_rate: Optional[float] = None
            if "+" in line and "x" in line:
                match = re.search(r"(\d+x\d+).*?([0-9]+\.\d+)\*?\+?", line)
                if match:
                    resolution = match.group(1)
                    refresh_rate = float(match.group(2))
            monitors.append(MonitorInfo(name=current_name, resolution=resolution, refresh_rate=refresh_rate))
        elif current_name and "*" in line:
            match = re.search(r"(\d+x\d+).*?([0-9]+\.\d+)\*", line)
            if match:
                monitors.append(
                    MonitorInfo(name=current_name, resolution=match.group(1), refresh_rate=float(match.group(2)))
                )
            current_name = None
    return monitors


def _get_bios_info() -> BIOSInfo:
    vendor = None
    version = None
    release_date = None
    motherboard = None
    output = _run_command(["dmidecode", "-t", "0"])
    if output:
        for line in output.splitlines():
            if line.strip().startswith("Vendor:"):
                vendor = line.split(":", 1)[1].strip()
            elif line.strip().startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            elif line.strip().startswith("Release Date:"):
                release_date = line.split(":", 1)[1].strip()
    baseboard = _run_command(["dmidecode", "-t", "2"])
    if baseboard:
        for line in baseboard.splitlines():
            if line.strip().startswith("Product Name:"):
                motherboard = line.split(":", 1)[1].strip()
                break
    return BIOSInfo(
        vendor=vendor,
        version=version,
        release_date=release_date,
        motherboard=motherboard,
    )


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


@router.get("/info")
async def system_info_snapshot() -> Any:
    try:
        return {
            "cpu": _get_cpu_info().model_dump(),
            "ram": _get_ram_info().model_dump(),
            "gpu": [gpu.model_dump() for gpu in _get_gpu_info()],
            "disk": [disk.model_dump() for disk in _get_disk_info()],
            "os": _get_os_info().model_dump(),
            "usb": [usb.model_dump() for usb in _get_usb_devices()],
            "monitors": [monitor.model_dump() for monitor in _get_monitors()],
            "bios": _get_bios_info().model_dump(),
        }
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/cpu", response_model=CPUInfo)
async def system_cpu() -> Any:
    try:
        return _get_cpu_info()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/ram", response_model=RAMInfo)
async def system_ram() -> Any:
    try:
        return _get_ram_info()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/gpu")
async def system_gpu() -> Any:
    try:
        return [gpu.model_dump() for gpu in _get_gpu_info()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/disk")
async def system_disk() -> Any:
    try:
        return [disk.model_dump() for disk in _get_disk_info()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/os", response_model=OSInfo)
async def system_os() -> Any:
    try:
        return _get_os_info()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/usb")
async def system_usb() -> Any:
    try:
        return [usb.model_dump() for usb in _get_usb_devices()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/monitors")
async def system_monitors() -> Any:
    try:
        return [monitor.model_dump() for monitor in _get_monitors()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/bios", response_model=BIOSInfo)
async def system_bios() -> Any:
    try:
        return _get_bios_info()
    except Exception as exc:
        return _error_response(str(exc))
