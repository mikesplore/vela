import logging
import time
import uuid
from datetime import datetime, UTC

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.config import get_config

logger = logging.getLogger("vela.middleware")

# Soft import path — avoid circular import at module load if audit db not ready
_AUDIT_WRITE_COUNTER = 0


def _extract_user_id(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        cfg = get_config()
        payload = jwt.decode(token, cfg.secret_key, algorithms=["HS256"])
        sub = payload.get("sub")
        return str(sub) if sub else None
    except JWTError:
        return None
    except Exception:
        return None


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _record_audit(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    user_id: str | None,
    client_ip: str | None,
) -> None:
    global _AUDIT_WRITE_COUNTER
    try:
        from app.services.audit import should_audit_path, maybe_prune
        from app.db.audit_log import insert_audit_event

        if not get_config().audit_enabled:
            return
        if not should_audit_path(path):
            return

        error = None
        if status_code >= 400:
            error = f"HTTP {status_code}"

        insert_audit_event(
            request_id=request_id,
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            user_id=user_id,
            client_ip=client_ip,
            error=error,
            created_at=datetime.now(UTC),
        )
        _AUDIT_WRITE_COUNTER += 1
        # Occasional prune so the DB doesn't grow unbounded
        if _AUDIT_WRITE_COUNTER % 200 == 0:
            maybe_prune()
    except Exception as exc:
        logger.debug("Audit write skipped: %s", exc)


class RequestLoggerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, log_level: str = "INFO"):
        super().__init__(app)
        self.log_level = log_level.upper()

    async def dispatch(self, request: Request, call_next):
        start_time = time.monotonic()
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        user_id = _extract_user_id(request)
        request.state.audit_user_id = user_id
        client_ip = _client_ip(request)

        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "%s %s %d %.2fms rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )

        response.headers["X-Request-ID"] = request_id
        _record_audit(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=elapsed_ms,
            user_id=user_id,
            client_ip=client_ip,
        )
        return response
