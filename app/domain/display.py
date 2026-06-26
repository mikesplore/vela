from typing import Optional

from pydantic import BaseModel, Field


class ScreenshotResponse(BaseModel):
    image_base64: str


class RecordRequest(BaseModel):
    duration_seconds: int = Field(..., gt=0, le=60)


class BrightnessRequest(BaseModel):
    value: int = Field(..., ge=0, le=100)


class ResolutionRequest(BaseModel):
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    refresh: int = Field(..., gt=0)


class RotateRequest(BaseModel):
    orientation: str = Field(..., pattern="^(normal|left|right|inverted)$")


class NightLightRequest(BaseModel):
    enabled: bool
    temperature: Optional[int] = Field(None, ge=1000, le=10000)


class ValueResponse(BaseModel):
    success: bool
    message: Optional[str] = None


MUTTER_POWER_SAVE_MODE_ON = 0
MUTTER_POWER_SAVE_MODE_OFF = 1


class PowerSaveState(BaseModel):
    power_save_mode: int
    is_on: bool
    message: str


class BrightnessInfo(BaseModel):
    brightness: Optional[float]


class ResolutionInfo(BaseModel):
    width: int
    height: int
    refresh: Optional[float]
    output: str