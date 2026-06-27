import glob
import os
import time
from typing import Any, Dict, List, Optional

import psutil
from fastapi.responses import JSONResponse

from app.domain.monitoring import CPUUsage, DiskIOMetric, NetworkIOMetric, TemperatureEntry, BatteryInfo, FanEntry, \
    BatteryHealthInfo, SingleBatteryHealth, ProcessMetrics, ProcessInfo, UptimeInfo
from app.services.system_info import RAMInfo, GPUInfo
from app.utils.run_command import run_command




def error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


def get_cpu_usage() -> CPUUsage:
    per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    overall = psutil.cpu_percent(interval=None)
    return CPUUsage(overall=overall, per_core=per_core)


def get_ram_status() -> RAMInfo:
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


def get_gpu_usage() -> List[GPUInfo]:
    stdout, _, returncode = run_command([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if returncode != 0 or not stdout:
        return []

    usage_list: List[GPUInfo] = []
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 4:
            name = parts[0]
            util = float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else None
            used = int(parts[2]) if parts[2].isdigit() else None
            total = int(parts[3]) if parts[3].isdigit() else None
            usage_list.append(
                GPUInfo(
                    name=name,
                    utilization_percent=util,
                    memory_used_mb=used,
                    memory_total_mb=total,
                )
            )
    return usage_list


def compute_rate(first: Dict[str, Any], second: Dict[str, Any], elapsed: float) -> Dict[str, Any]:
    delta = {}
    for key, current in second.items():
        previous = first.get(key)
        if previous is None:
            continue
        delta[key] = (current - previous) / elapsed if elapsed > 0 else 0.0
    return delta


def get_disk_io() -> List[DiskIOMetric]:
    first = psutil.disk_io_counters(perdisk=True)
    time.sleep(0.1)
    second = psutil.disk_io_counters(perdisk=True)
    metrics: List[DiskIOMetric] = []
    for device, counters in second.items():
        previous = first.get(device)
        if not previous:
            continue
        elapsed = 0.1
        metrics.append(
            DiskIOMetric(
                device=device,
                read_bytes_per_sec=(counters.read_bytes - previous.read_bytes) / elapsed,
                write_bytes_per_sec=(counters.write_bytes - previous.write_bytes) / elapsed,
            )
        )
    return metrics


def get_network_io() -> List[NetworkIOMetric]:
    first = psutil.net_io_counters(pernic=True)
    time.sleep(0.1)
    second = psutil.net_io_counters(pernic=True)
    metrics: List[NetworkIOMetric] = []
    for nic, counters in second.items():
        previous = first.get(nic)
        if not previous:
            continue
        elapsed = 0.1
        metrics.append(
            NetworkIOMetric(
                interface=nic,
                bytes_sent_per_sec=(counters.bytes_sent - previous.bytes_sent) / elapsed,
                bytes_recv_per_sec=(counters.bytes_recv - previous.bytes_recv) / elapsed,
            )
        )
    return metrics


def get_temperatures() -> List[TemperatureEntry]:
    results: List[TemperatureEntry] = []
    if not hasattr(psutil, "sensors_temperatures"):
        return results
    for label, entries in psutil.sensors_temperatures().items():
        for entry in entries:
            results.append(
                TemperatureEntry(
                    sensor=label,
                    label=getattr(entry, "label", ""),
                    current=entry.current,
                    high=getattr(entry, "high", None),
                    critical=getattr(entry, "critical", None),
                )
            )
    return results


def get_fan_speeds() -> List[FanEntry]:
    results: List[FanEntry] = []
    if not hasattr(psutil, "sensors_fans"):
        return results
    for label, entries in psutil.sensors_fans().items():
        for entry in entries:
            results.append(FanEntry(sensor=label, speed_rpm=getattr(entry, "current", None)))
    return results


def get_battery_status() -> BatteryInfo:
    battery = psutil.sensors_battery()
    if not battery:
        return BatteryInfo(percent=None, plugged_in=None, secs_left=None)
    return BatteryInfo(
        percent=battery.percent,
        plugged_in=battery.power_plugged,
        secs_left=int(battery.secsleft) if battery.secsleft is not None and battery.secsleft >= 0 else None,
    )


def read_sysfs_int(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def read_sysfs_str(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            val = f.read().strip()
            return val if val else None
    except OSError:
        return None


def get_battery_health() -> BatteryHealthInfo:
    batteries: List[SingleBatteryHealth] = []
    total_cycle: Optional[int] = None
    health_values: List[float] = []

    for bat_dir in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        name = os.path.basename(bat_dir)
        present_val = read_sysfs_int(os.path.join(bat_dir, "present"))
        present = present_val == 1 if present_val is not None else True

        cycle_count = read_sysfs_int(os.path.join(bat_dir, "cycle_count"))
        design_cap_uwh = read_sysfs_int(os.path.join(bat_dir, "energy_full_design"))
        current_cap_uwh = read_sysfs_int(os.path.join(bat_dir, "energy_full"))

        design_wh = round(design_cap_uwh / 1_000_000, 2) if design_cap_uwh is not None else None
        current_wh = round(current_cap_uwh / 1_000_000, 2) if current_cap_uwh is not None else None

        health_pct: Optional[float] = None
        if design_cap_uwh is not None and design_cap_uwh > 0 and current_cap_uwh is not None:
            health_pct = round((current_cap_uwh / design_cap_uwh) * 100, 2)

        if health_pct is not None:
            health_values.append(health_pct)

        if cycle_count is not None:
            if total_cycle is not None:
                total_cycle += cycle_count
            else:
                total_cycle = cycle_count

        batteries.append(
            SingleBatteryHealth(
                name=name,
                path=bat_dir,
                present=present,
                cycle_count=cycle_count,
                design_capacity_wh=design_wh,
                current_max_capacity_wh=current_wh,
                health_percent=health_pct,
                manufacturer=read_sysfs_str(os.path.join(bat_dir, "manufacturer")),
                model_name=read_sysfs_str(os.path.join(bat_dir, "model_name")),
                serial_number=read_sysfs_str(os.path.join(bat_dir, "serial_number")),
                technology=read_sysfs_str(os.path.join(bat_dir, "technology")),
                voltage_now_uv=read_sysfs_int(os.path.join(bat_dir, "voltage_now")),
                charge_control_start_threshold=read_sysfs_int(
                    os.path.join(bat_dir, "charge_control_start_threshold")
                ),
                charge_control_stop_threshold=read_sysfs_int(
                    os.path.join(bat_dir, "charge_control_stop_threshold")
                ),
            )
        )

    overall_health: Optional[float] = None
    if health_values:
        overall_health = round(sum(health_values) / len(health_values), 2)

    return BatteryHealthInfo(
        batteries=batteries,
        total_cycle_count=total_cycle,
        overall_health_percent=overall_health,
    )


def get_top_processes(limit: int = 20) -> ProcessMetrics:
    processes: List[ProcessInfo] = []
    for proc in psutil.process_iter(attrs=["pid", "name", "username"]):
        try:
            cpu_percent = proc.cpu_percent(interval=None)
            memory_percent = proc.memory_percent()
            memory_rss = proc.memory_info().rss
            processes.append(
                ProcessInfo(
                    pid=proc.pid,
                    name=proc.info.get("name", ""),
                    username=proc.info.get("username"),
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_rss=memory_rss,
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return ProcessMetrics(
        top_by_cpu=sorted(processes, key=lambda item: item.cpu_percent, reverse=True)[:limit],
        top_by_memory=sorted(processes, key=lambda item: item.memory_percent, reverse=True)[:limit],
    )


def get_uptime() -> UptimeInfo:
    """Get system uptime in human-readable format."""
    import datetime
    boot_time = psutil.boot_time()
    uptime_seconds = int(time.time() - boot_time)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")

    return UptimeInfo(
        seconds=uptime_seconds,
        minutes=minutes + hours * 60 + days * 1440,
        hours=hours + days * 24,
        days=days,
        formatted=" ".join(parts),
    )


def get_snapshot() -> Dict[str, Any]:
    return {
        "cpu": get_cpu_usage().model_dump(),
        "ram": get_ram_status().model_dump(),
        "gpu": [gpu.model_dump() for gpu in get_gpu_usage()],
        "disk_io": [metric.model_dump() for metric in get_disk_io()],
        "network_io": [metric.model_dump() for metric in get_network_io()],
        "temperatures": [temp.model_dump() for temp in get_temperatures()],
        "fans": [fan.model_dump() for fan in get_fan_speeds()],
        "battery": get_battery_status().model_dump(),
        "processes": get_top_processes().model_dump(),
    }
