from typing import Any
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
from app.services.system_info import get_cpu_info, get_ram_info, get_gpu_info, get_disk_info, get_os_info, get_usb_devices, \
    get_monitors, get_bios_info, get_device_info, error_response, CPUInfo, RAMInfo, BIOSInfo, OSInfo, DeviceInfo

router = APIRouter(prefix="/system", tags=["system_info"], dependencies=[Depends(get_current_user)])


@router.get("/info")
async def system_info_snapshot() -> Any:
    try:
        return {
            "cpu": get_cpu_info().model_dump(),
            "ram": get_ram_info().model_dump(),
            "gpu": [gpu.model_dump() for gpu in get_gpu_info()],
            "disk": [disk.model_dump() for disk in get_disk_info()],
            "os": get_os_info().model_dump(),
            "usb": [usb.model_dump() for usb in get_usb_devices()],
            "monitors": [monitor.model_dump() for monitor in get_monitors()],
            "bios": get_bios_info().model_dump(),
        }
    except Exception as exc:
        return error_response(str(exc))


@router.get("/cpu", response_model=CPUInfo)
async def system_cpu() -> Any:
    try:
        return get_cpu_info()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/ram", response_model=RAMInfo)
async def system_ram() -> Any:
    try:
        return get_ram_info()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/gpu")
async def system_gpu() -> Any:
    try:
        return [gpu.model_dump() for gpu in get_gpu_info()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/disk")
async def system_disk() -> Any:
    try:
        return [disk.model_dump() for disk in get_disk_info()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/os", response_model=OSInfo)
async def system_os() -> Any:
    try:
        return get_os_info()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/usb")
async def system_usb() -> Any:
    try:
        return [usb.model_dump() for usb in get_usb_devices()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/monitors")
async def system_monitors() -> Any:
    try:
        return [monitor.model_dump() for monitor in get_monitors()]
    except Exception as exc:
        return error_response(str(exc))


@router.get("/bios", response_model=BIOSInfo)
async def system_bios() -> Any:
    try:
        return get_bios_info()
    except Exception as exc:
        return error_response(str(exc))


@router.get("/device", response_model=DeviceInfo)
async def system_device() -> Any:
    try:
        return get_device_info()
    except Exception as exc:
        return error_response(str(exc))
