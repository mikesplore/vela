import logging
import time
from typing import List

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


logger = logging.getLogger("vela.middleware")


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level.upper()

    async def dispatch(self, request: Request, call_next):
        start_time = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "%s %s %d %.2fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_ips: List[str] | None = None):
        super().__init__(app)
        self.allowed_ips = allowed_ips or []

    async def dispatch(self, request: Request, call_next):
        client = request.client
        if not client or client.host not in self.allowed_ips:
            logger.warning("Access denied for IP: %s", client.host if client else "unknown")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="IP address is not allowed",
            )
        return await call_next(request)
