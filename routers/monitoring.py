import asyncio
import glob
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import verify_websocket_token
from dependencies import get_current_user

router = APIRouter(prefix="/monitor", tags=["monitoring"])


def _run_command(cmd: List[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""


class CPUUsage(BaseModel):
    overall: float
    per_core: List[float]


class RAMStatus(BaseModel):
    total: int
    available: int
    used: int
    percent: float
    swap_total: int
    swap_used: int
    swap_free: int
    swap_percent: float


class GPUUsage(BaseModel):
    name: str
    utilization_percent: Optional[float]
    memory_used_mb: Optional[int]
    memory_total_mb: Optional[int]


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


def _error_response(message: str, status_code: int = 500) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"success": False, "error": message})


def _get_cpu_usage() -> CPUUsage:
    per_core = psutil.cpu_percent(interval=0.1, percpu=True)
    overall = psutil.cpu_percent(interval=None)
    return CPUUsage(overall=overall, per_core=per_core)


def _get_ram_status() -> RAMStatus:
    virtual = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return RAMStatus(
        total=virtual.total,
        available=virtual.available,
        used=virtual.used,
        percent=virtual.percent,
        swap_total=swap.total,
        swap_used=swap.used,
        swap_free=swap.free,
        swap_percent=swap.percent,
    )


def _get_gpu_usage() -> List[GPUUsage]:
    output = _run_command([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total",
        "--format=csv,noheader,nounits",
    ])
    if not output:
        return []

    usage_list: List[GPUUsage] = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 4:
            name = parts[0]
            util = float(parts[1]) if parts[1].replace(".", "", 1).isdigit() else None
            used = int(parts[2]) if parts[2].isdigit() else None
            total = int(parts[3]) if parts[3].isdigit() else None
            usage_list.append(
                GPUUsage(
                    name=name,
                    utilization_percent=util,
                    memory_used_mb=used,
                    memory_total_mb=total,
                )
            )
    return usage_list


def _compute_rate(first: Dict[str, Any], second: Dict[str, Any], elapsed: float) -> Dict[str, Any]:
    delta = {}
    for key, current in second.items():
        previous = first.get(key)
        if previous is None:
            continue
        delta[key] = (current - previous) / elapsed if elapsed > 0 else 0.0
    return delta


def _get_disk_io() -> List[DiskIOMetric]:
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


def _get_network_io() -> List[NetworkIOMetric]:
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


def _get_temperatures() -> List[TemperatureEntry]:
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


def _get_fan_speeds() -> List[FanEntry]:
    results: List[FanEntry] = []
    if not hasattr(psutil, "sensors_fans"):
        return results
    for label, entries in psutil.sensors_fans().items():
        for entry in entries:
            results.append(FanEntry(sensor=label, speed_rpm=getattr(entry, "current", None)))
    return results


def _get_battery_status() -> BatteryInfo:
    battery = psutil.sensors_battery()
    if not battery:
        return BatteryInfo(percent=None, plugged_in=None, secs_left=None)
    return BatteryInfo(
        percent=battery.percent,
        plugged_in=battery.power_plugged,
        secs_left=int(battery.secsleft) if battery.secsleft is not None and battery.secsleft >= 0 else None,
    )


def _read_sysfs_int(path: str) -> Optional[int]:
    try:
        with open(path, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _read_sysfs_str(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            val = f.read().strip()
            return val if val else None
    except OSError:
        return None


def _get_battery_health() -> BatteryHealthInfo:
    batteries: List[SingleBatteryHealth] = []
    total_cycle: Optional[int] = None
    health_values: List[float] = []

    for bat_dir in sorted(glob.glob("/sys/class/power_supply/BAT*")):
        name = os.path.basename(bat_dir)
        present_val = _read_sysfs_int(os.path.join(bat_dir, "present"))
        present = present_val == 1 if present_val is not None else True

        cycle_count = _read_sysfs_int(os.path.join(bat_dir, "cycle_count"))
        design_cap_uwh = _read_sysfs_int(os.path.join(bat_dir, "energy_full_design"))
        current_cap_uwh = _read_sysfs_int(os.path.join(bat_dir, "energy_full"))

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
                manufacturer=_read_sysfs_str(os.path.join(bat_dir, "manufacturer")),
                model_name=_read_sysfs_str(os.path.join(bat_dir, "model_name")),
                serial_number=_read_sysfs_str(os.path.join(bat_dir, "serial_number")),
                technology=_read_sysfs_str(os.path.join(bat_dir, "technology")),
                voltage_now_uv=_read_sysfs_int(os.path.join(bat_dir, "voltage_now")),
                charge_control_start_threshold=_read_sysfs_int(
                    os.path.join(bat_dir, "charge_control_start_threshold")
                ),
                charge_control_stop_threshold=_read_sysfs_int(
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


def _get_top_processes(limit: int = 20) -> ProcessMetrics:
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


def _get_snapshot() -> Dict[str, Any]:
    return {
        "cpu": _get_cpu_usage().model_dump(),
        "ram": _get_ram_status().model_dump(),
        "gpu": [gpu.model_dump() for gpu in _get_gpu_usage()],
        "disk_io": [metric.model_dump() for metric in _get_disk_io()],
        "network_io": [metric.model_dump() for metric in _get_network_io()],
        "temperatures": [temp.model_dump() for temp in _get_temperatures()],
        "fans": [fan.model_dump() for fan in _get_fan_speeds()],
        "battery": _get_battery_status().model_dump(),
        "processes": _get_top_processes().model_dump(),
    }


@router.get("/snapshot", dependencies=[Depends(get_current_user)])
async def monitor_snapshot() -> Any:
    try:
        return _get_snapshot()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/cpu", response_model=CPUUsage, dependencies=[Depends(get_current_user)])
async def monitor_cpu() -> Any:
    try:
        return _get_cpu_usage()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/ram", response_model=RAMStatus, dependencies=[Depends(get_current_user)])
async def monitor_ram() -> Any:
    try:
        return _get_ram_status()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/gpu", dependencies=[Depends(get_current_user)])
async def monitor_gpu() -> Any:
    try:
        return [gpu.model_dump() for gpu in _get_gpu_usage()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/disk-io", dependencies=[Depends(get_current_user)])
async def monitor_disk_io() -> Any:
    try:
        return [metric.model_dump() for metric in _get_disk_io()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/network-io", dependencies=[Depends(get_current_user)])
async def monitor_network_io() -> Any:
    try:
        return [metric.model_dump() for metric in _get_network_io()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/temperatures", dependencies=[Depends(get_current_user)])
async def monitor_temperatures() -> Any:
    try:
        return [temp.model_dump() for temp in _get_temperatures()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/fans", dependencies=[Depends(get_current_user)])
async def monitor_fans() -> Any:
    try:
        return [fan.model_dump() for fan in _get_fan_speeds()]
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/battery", response_model=BatteryInfo, dependencies=[Depends(get_current_user)])
async def monitor_battery() -> Any:
    try:
        return _get_battery_status()
    except Exception as exc:
        return _error_response(str(exc))


@router.get(
    "/battery-health",
    response_model=BatteryHealthInfo,
    dependencies=[Depends(get_current_user)],
)
async def monitor_battery_health() -> Any:
    try:
        return _get_battery_health()
    except Exception as exc:
        return _error_response(str(exc))


@router.get("/processes", response_model=ProcessMetrics, dependencies=[Depends(get_current_user)])
async def monitor_processes() -> Any:
    try:
        return _get_top_processes()
    except Exception as exc:
        return _error_response(str(exc))


@router.websocket("/stream")
async def monitor_stream(websocket: WebSocket, token_data=Depends(verify_websocket_token), interval: int = 5):
    await websocket.accept()
    try:
        while True:
            snapshot = _get_snapshot()
            await websocket.send_json(snapshot)
            await asyncio.sleep(max(interval, 1))
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)
