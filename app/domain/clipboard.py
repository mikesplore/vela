from pydantic import BaseModel


class ClipboardData(BaseModel):
    text: str


class ClipboardWriteRequest(BaseModel):
    text: str


class StatusResponse(BaseModel):
    success: bool
    message: str
