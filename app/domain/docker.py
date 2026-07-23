from typing import List, Optional

from pydantic import BaseModel, Field


class DockerInfoResponse(BaseModel):
    installed: bool
    running: bool
    version: Optional[str] = None
    containers_running: Optional[int] = None
    containers_total: Optional[int] = None
    message: Optional[str] = None


class DockerContainer(BaseModel):
    id: str
    name: str
    image: str
    status: str
    state: str
    ports: str = ""
    created: Optional[str] = None


class DockerContainerListResponse(BaseModel):
    containers: List[DockerContainer]


class DockerContainerDetail(BaseModel):
    id: str
    name: str
    image: str
    status: str
    state: str
    health: Optional[str] = None
    ports: List[str] = Field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class DockerLogsResponse(BaseModel):
    container: str
    lines: List[str]


class ComposeServiceStatus(BaseModel):
    name: str
    state: str
    status: str
    ports: str = ""


class ComposeStatusResponse(BaseModel):
    project: Optional[str] = None
    services: List[ComposeServiceStatus]


class ActionResponse(BaseModel):
    success: bool
    message: str
