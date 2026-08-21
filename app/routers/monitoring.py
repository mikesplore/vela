import asyncio
import time
from typing import Any
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from app.auth import verify_websocket_token
from app.dependencies import get_current_user
from app.domain.monitoring import CPUUsage, BatteryInfo, BatteryHealthInfo, ProcessMetrics, UptimeInfo
from app.domain.system_info import RAMInfo
from app.services.monitoring import get_snapshot, error_response, get_cpu_usage, get_ram_status, get_gpu_usage, get_disk_io, \
    get_network_io, get_temperatures, get_fan_speeds, get_battery_status, get_battery_health, get_top_processes, get_uptime
from app.utils.list_limits import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT

router = APIRouter(prefix="/monitor", tags=["monitoring"])
_stream_connections: dict[str, int] = {}
_stream_attempts: dict[str, list[float]] = {}


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


@router.get("/uptime", response_model=UptimeInfo, dependencies=[Depends(get_current_user)])
async def monitor_uptime() -> Any:
    try:
        return get_uptime()
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
async def monitor_processes(
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
) -> Any:
    try:
        return get_top_processes(limit=limit)
    except Exception as exc:
        return error_response(str(exc))


@router.websocket("/stream")
async def monitor_stream(
    websocket: WebSocket,
    token_data=Depends(verify_websocket_token),
    interval: int = Query(5, ge=1, le=300),
):
    user_id = str(token_data.sub)
    active = _stream_connections.get(user_id, 0)
    from app.utils.config import get_config

    now = time.monotonic()
    attempts = [stamp for stamp in _stream_attempts.get(user_id, []) if now - stamp < 60]
    if len(attempts) >= 30:
        await websocket.close(code=1013, reason="Too many monitoring stream attempts")
        return
    attempts.append(now)
    _stream_attempts[user_id] = attempts
    if active >= get_config().max_websocket_connections:
        await websocket.close(code=1013, reason="Too many monitoring streams")
        return
    _stream_connections[user_id] = active + 1
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
    finally:
        remaining = _stream_connections.get(user_id, 1) - 1
        if remaining > 0:
            _stream_connections[user_id] = remaining
        else:
            _stream_connections.pop(user_id, None)
