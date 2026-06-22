import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


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


