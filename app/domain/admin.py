from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    id: int
    request_id: str
    created_at: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    user_id: Optional[str] = None
    client_ip: Optional[str] = None
    error: Optional[str] = None


class EndpointStats(BaseModel):
    endpoint: str
    count: int
    errors: int
    error_rate: float
    median_ms: float
    p95_ms: float
    avg_ms: float


class TimelinePoint(BaseModel):
    minute: str
    count: int
    errors: int
    median_ms: float
    p95_ms: float


class AuditSummary(BaseModel):
    window_minutes: int
    total_requests: int
    error_count: int
    error_rate: float
    median_ms: float
    p95_ms: float
    avg_ms: float
    by_endpoint: list[EndpointStats]
    timeline: list[TimelinePoint]
    recent_errors: list[AuditEvent]


class AuditEventsResponse(BaseModel):
    events: list[AuditEvent]
    total_stored: int = Field(description="Total rows currently in the audit database")


class ToolCallEvent(BaseModel):
    id: int
    request_id: str
    created_at: str
    tool_name: str
    duration_ms: float
    succeeded: bool
    user_id: Optional[str] = None
    error: Optional[str] = None


class ToolStats(BaseModel):
    tool_name: str
    count: int
    errors: int
    error_rate: float
    median_ms: float
    p95_ms: float


class AssistantAuditSummary(BaseModel):
    window_minutes: int
    total_tool_calls: int
    tool_error_count: int
    tool_error_rate: float
    by_tool: list[ToolStats]
    recent_failures: list[ToolCallEvent]


class ToolEventsResponse(BaseModel):
    events: list[ToolCallEvent]
    total_stored: int
