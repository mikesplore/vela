from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field


class SchedulerCreateRequest(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)
    run_at: datetime
    recurring: Optional[str] = None


class SchedulerJobInfo(BaseModel):
    id: str
    command: str
    args: List[str]
    next_run_time: Optional[datetime]
    trigger: str
    recurring: Optional[str]
    run_at: datetime


class SchedulerListResponse(BaseModel):
    jobs: List[SchedulerJobInfo]


class SchedulerActionResponse(BaseModel):
    success: bool
    message: str