from datetime import datetime

from pydantic import BaseModel, Field


class ValueResponse(BaseModel):
    success: bool
    message: str


class ScheduleShutdownRequest(BaseModel):
    at: datetime


class PowerProfileRequest(BaseModel):
    profile: str = Field(..., pattern="^(performance|balanced|power-saver)$")


class PowerProfileResponse(BaseModel):
    success: bool
    message: str
    profile: str