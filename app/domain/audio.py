from pydantic import BaseModel, Field

class VolumeInfo(BaseModel):
    volume: int
    muted: bool


class VolumeRequest(BaseModel):
    value: int = Field(..., ge=0, le=100)


class StepRequest(BaseModel):
    step: int = Field(..., gt=0, le=20)


class MuteRequest(BaseModel):
    muted: bool


class AudioDevice(BaseModel):
    id: str
    name: str
    type: str


class ActionResponse(BaseModel):
    success: bool
    message: str


class OutputDeviceRequest(BaseModel):
    device_id: str
