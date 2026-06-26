"""Unified error response handling for Vela API."""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Unified error response format."""
    success: bool = False
    statusCode: int
    message: str
    timestamp: str  # ISO8601 format

    @staticmethod
    def now() -> str:
        """Get current timestamp in ISO8601 format."""
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    @classmethod
    def create(cls, status_code: int, message: str) -> "ErrorResponse":
        """Create an error response with current timestamp."""
        return cls(
            statusCode=status_code,
            message=message,
            timestamp=cls.now()
        )
