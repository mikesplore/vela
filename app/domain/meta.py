from pydantic import BaseModel

class ToolCountResponse(BaseModel):
    count: int

class ToolListResponse(BaseModel):
    tools: list[str]
