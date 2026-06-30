from typing import Optional

from pydantic import BaseModel


class SpotifyTrack(BaseModel):
    name: str
    artist: str
    uri: str
    url: str
    genre: Optional[str] = None