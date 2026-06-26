from typing import Optional

from pydantic import BaseModel, Field


class MediaStatus(BaseModel):
    success: bool
    message: str


class SeekRequest(BaseModel):
    seconds: float = Field(...)


class NowPlayingInfo(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    art_url: Optional[str] = None
    status: Optional[str] = None
    playing: Optional[bool] = None
    position_seconds: Optional[float] = None
    length_seconds: Optional[float] = None
