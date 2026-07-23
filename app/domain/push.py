from pydantic import BaseModel, Field


class PushDeviceRegistration(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    installation_id: str | None = Field(default=None, max_length=256)


class PushDeviceRemoval(BaseModel):
    token: str = Field(min_length=20, max_length=4096)


class PushSendRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    data: dict[str, str] = Field(default_factory=dict)


class PushSendResponse(BaseModel):
    success: bool
    delivered: int
    configured: bool
