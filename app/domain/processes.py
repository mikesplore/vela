from typing import List, Optional

from pydantic import BaseModel, Field


class ProcessInfo(BaseModel):
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: Optional[str]
    cmdline: List[str] = Field(default_factory=list)


class ProcessList(BaseModel):
    processes: List[ProcessInfo]


class LaunchRequest(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)


class ApplicationRequest(BaseModel):
    name: str
    args: List[str] = Field(default_factory=list)


class ApplicationCloseRequest(BaseModel):
    name: str


class InstalledApplication(BaseModel):
    id: str
    name: str
    generic_name: Optional[str] = None
    exec_command: str
    exec_binary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    categories: List[str] = Field(default_factory=list)


class InstalledApplicationList(BaseModel):
    applications: List[InstalledApplication]


class ActionResponse(BaseModel):
    success: bool
    message: Optional[str] = None
    pid: Optional[int] = None
    killed_count: Optional[int] = None
    application_id: Optional[str] = None
    application_name: Optional[str] = None


class ProcessRunningResponse(BaseModel):
    name: str
    running: bool
    count: int
    pids: List[int] = Field(default_factory=list)
