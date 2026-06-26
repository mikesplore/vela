import os
import platform
import pwd
import re
from datetime import datetime
from typing import List, Optional

import psutil
from fastapi.responses import JSONResponse
from domain.system_info import CPUInfo, RAMInfo, GPUInfo, DiskPartitionInfo, OSInfo, USBDevice, MonitorInfo, BIOSInfo
from utils.run_command import run_command



def get_cpu_model() -> str:
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


def get_cpu_info() -> CPUInfo:
    return CPUInfo(
        model=get_cpu_model(),
        physical_cores=psutil.cpu_count(logical=False) or 0,
        logical_cores=psutil.cpu_count(logical=True) or 0,
        base_freq_mhz=psutil.cpu_freq().max if psutil.cpu_freq() else None,
        architecture=platform.machine(),
    )


def get_ram_info() -> RAMInfo:
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


def parse_lspci() -> List[GPUInfo]:
    output = run_command(["lspci", "-nnk"])
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


def parse_nvidia_smi() -> List[GPUInfo]:
    output = run_command([
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


def get_gpu_info() -> List[GPUInfo]:
    gpus = parse_nvidia_smi()
    if gpus:
        return gpus
    return parse_lspci()


def get_disk_info() -> List[DiskPartitionInfo]:
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


def get_os_info() -> OSInfo:
    uname = platform.uname()
    return OSInfo(
        os_name=platform.system(),
        os_version=platform.version(),
        kernel=uname.release,
        hostname=uname.node,
        user=pwd.getpwuid(os.getuid()).pw_name,
        uptime_seconds=int(datetime.now().timestamp() - psutil.boot_time()),
    )


def get_usb_devices() -> List[USBDevice]:
    output = run_command(["lsusb"])
    devices: List[USBDevice] = []
    for line in output.splitlines():
        match = re.match(r"Bus (\d{3}) Device (\d{3}): ID ([0-9a-fA-F:]+) (.*)$", line)
        if match:
            bus, device, bus_id, desc = match.groups()
            devices.append(USBDevice(bus=bus, device=device, id=bus_id, description=desc))
    return devices


def get_monitors() -> List[MonitorInfo]:
    output = run_command(["xrandr", "--query"])
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


def get_bios_info() -> BIOSInfo:
    vendor = None
    version = None
    release_date = None
    motherboard = None
    output = run_command(["dmidecode", "-t", "0"])
    if output:
        for line in output.splitlines():
            if line.strip().startswith("Vendor:"):
                vendor = line.split(":", 1)[1].strip()
            elif line.strip().startswith("Version:"):
                version = line.split(":", 1)[1].strip()
            elif line.strip().startswith("Release Date:"):
                release_date = line.split(":", 1)[1].strip()
    baseboard = run_command(["dmidecode", "-t", "2"])
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


def error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})
