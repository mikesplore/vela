import asyncio
from typing import Any
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from app.auth import verify_websocket_token
from app.dependencies import get_current_user
from domain.monitoring import CPUUsage, BatteryInfo, BatteryHealthInfo, ProcessMetrics
from domain.system_info import RAMInfo
from services.monitoring import get_snapshot, error_response, get_cpu_usage, get_ram_status, get_gpu_usage, get_disk_io, \
    get_network_io, get_temperatures, get_fan_speeds, get_battery_status, get_battery_health, get_top_processes

router = APIRouter(prefix="/monitor", tags=["monitoring"])


@router.get("/snapshot", dependencies=[Depends(get_current_user)])
async def monitor_snapshot() -> Any:
    try:
        return get_snapshot()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/cpu", response_model=CPUUsage, dependencies=[Depends(get_current_user)])
async def monitor_cpu() -> Any:
    try:
        return get_cpu_usage()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/ram", response_model=RAMInfo, dependencies=[Depends(get_current_user)])
async def monitor_ram() -> Any:
    try:
        return get_ram_status()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/gpu", dependencies=[Depends(get_current_user)])
async def monitor_gpu() -> Any:
    try:
        return [gpu.model_dump() for gpu in get_gpu_usage()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/disk-io", dependencies=[Depends(get_current_user)])
async def monitor_disk_io() -> Any:
    try:
        return [metric.model_dump() for metric in get_disk_io()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/network-io", dependencies=[Depends(get_current_user)])
async def monitor_network_io() -> Any:
    try:
        return [metric.model_dump() for metric in get_network_io()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/temperatures", dependencies=[Depends(get_current_user)])
async def monitor_temperatures() -> Any:
    try:
        return [temp.model_dump() for temp in get_temperatures()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/fans", dependencies=[Depends(get_current_user)])
async def monitor_fans() -> Any:
    try:
        return [fan.model_dump() for fan in get_fan_speeds()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/battery", response_model=BatteryInfo, dependencies=[Depends(get_current_user)])
async def monitor_battery() -> Any:
    try:
        return get_battery_status()
    except Exception as exc:
        return error_response(str(exc))


@router.get(
    "/battery-health",
    response_model=BatteryHealthInfo,
    dependencies=[Depends(get_current_user)],
)
async def monitor_battery_health() -> Any:
    try:
        return get_battery_health()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/processes", response_model=ProcessMetrics, dependencies=[Depends(get_current_user)])
async def monitor_processes() -> Any:
    try:
        return get_top_processes()
    except Exception as exc:
        return error_response(str(exc))


@router.websocket("/stream")
async def monitor_stream(websocket: WebSocket, token_data=Depends(verify_websocket_token), interval: int = 5):
    await websocket.accept()
    try:
        while True:
            snapshot = get_snapshot()
            await websocket.send_json(snapshot)
            await asyncio.sleep(max(interval, 1))
    except WebSocketDisconnect:
        return
    except Exception:
        await websocket.close(code=1011)
