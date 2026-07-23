from typing import List, Optional

from pydantic import BaseModel


class ServiceEntry(BaseModel):
    name: str
    load: str
    active: str
    sub: str
    description: str
    scope: str = "system"


class ServiceListResponse(BaseModel):
    services: List[ServiceEntry]


class ServiceStatusResponse(BaseModel):
    name: str
    scope: str
    load: str
    active: str
    sub: str
    description: str
    enabled: Optional[str] = None
    running: bool


class TimerEntry(BaseModel):
    name: str
    next: str
    left: str
    last: str
    passed: str
    active: str
    unit: str
    description: str
    scope: str = "system"


class TimerListResponse(BaseModel):
    timers: List[TimerEntry]


class PackageInstalledResponse(BaseModel):
    name: str
    installed: bool
    manager: Optional[str] = None
    version: Optional[str] = None


class BootErrorsResponse(BaseModel):
    lines: List[str]


class UpdateEntry(BaseModel):
    package: str
    current: Optional[str] = None
    available: Optional[str] = None


class UpdateResponse(BaseModel):
    updates: List[UpdateEntry]
    manager: str


class ActionResponse(BaseModel):
    success: bool
    message: str


class LogResponse(BaseModel):
    service: str
    lines: List[str]
