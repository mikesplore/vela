from typing import Optional, List

from pydantic import BaseModel


class ServiceEntry(BaseModel):
    name: str
    load: str
    active: str
    sub: str
    description: str


class ServiceListResponse(BaseModel):
    services: List[ServiceEntry]


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
