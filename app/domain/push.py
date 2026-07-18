from pydantic import BaseModel, Field


class PushDeviceRegistration(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
    installation_id: str | None = Field(default=None, max_length=256)


class PushDeviceRemoval(BaseModel):
    token: str = Field(min_length=20, max_length=4096)
