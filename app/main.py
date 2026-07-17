import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.auth import router as auth_router
from app.utils.config import get_config
from app.dependencies import get_current_user
from app.agent.helpers import start_agent_loop
from app.utils.errors import ErrorResponse
from app.middleware import RequestLoggerMiddleware
from app.rate_limiter import limiter, limit_route
from app.routers import all_routers
from app.routers import scheduler as scheduler_module

API_NAME = "Vela"
API_VERSION = "1.0.0"

config = get_config()
logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
logger = logging.getLogger("vela.main")


async def uniform_error_middleware(request: Request, call_next):
    """Middleware to ensure error responses follow uniform format."""
    response = await call_next(request)
    
    # Check if response is an error (4xx or 5xx)
    if 400 <= response.status_code < 600:
        # Only process JSON responses
        if "application/json" in response.headers.get("content-type", ""):
            try:
                # For streaming responses, collect the body
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                
                data = None
                
                # Try to parse as JSON
                import json
                try:
                    data = json.loads(body)
                except (json.JSONDecodeError, ValueError):
                    data = None
                
                # If it's an error response but not in our format, convert it
                if data and "success" not in data:
                    # Convert to our uniform format
                    message = data.get("detail", f"HTTP {response.status_code}")
                    error_response = ErrorResponse.create(response.status_code, message)
                    
                    return JSONResponse(
                        status_code=response.status_code,
                        content=error_response.model_dump()
                    )
                elif not data:
                    # No data, return uniform error format
                    error_response = ErrorResponse.create(
                        response.status_code,
                        f"HTTP {response.status_code}"
                    )
                    return JSONResponse(
                        status_code=response.status_code,
                        content=error_response.model_dump()
                    )
                else:
                    # Already in our format, return as-is
                    return JSONResponse(
                        status_code=response.status_code,
                        content=data
                    )
            except Exception as exc:
                logger.warning(f"Error processing response: {exc}")
                # Return error response on processing failure
                error_response = ErrorResponse.create(
                    response.status_code,
                    f"HTTP {response.status_code}"
                )
                return JSONResponse(
                    status_code=response.status_code,
                    content=error_response.model_dump()
                )
    
    return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.start_time = time.time()
    logger.info("Vela starting on %s:%s", config.host, config.port)
    try:
        from app.db.audit_log import init_audit_db

        init_audit_db()
    except Exception as e:
        logger.warning("Could not initialize audit database: %s", e)
    try:
        scheduler_module.scheduler.start()
    except Exception:
        logger.warning("Scheduler failed to start or was already running")

    # Auto-start spike monitoring + daily summary if email is configured
    try:
        from app.utils.desktop_env import refresh_desktop_env

        refresh_desktop_env(force=True, persist=True)
    except Exception as e:
        logger.warning("Could not refresh desktop session env: %s", e)

    try:
        from app.services.alerts import setup_monitoring_schedule, RECIPIENT_EMAIL, RESEND_AVAILABLE
        if RESEND_AVAILABLE and RECIPIENT_EMAIL:
            setup_monitoring_schedule()
            logger.info("Monitoring auto-started — spikes every 5min, daily summary at 18:00, email: %s", RECIPIENT_EMAIL)
        else:
            logger.debug("Monitoring not auto-started: set RESEND_API_KEY + RECIPIENT_EMAIL in .env")
    except Exception as e:
        logger.warning("Could not auto-start monitoring: %s", e)

    app.state.agent_task = None
    if os.getenv("START_AGENT", "true").lower() in ("1", "true", "yes"):
        logger.info("Starting local tunnel agent in background")
        app.state.agent_task = asyncio.create_task(start_agent_loop())

    try:
        yield
    finally:
        try:
            scheduler_module.scheduler.shutdown(wait=False)
        except Exception:
            logger.warning("Scheduler failed to shut down cleanly")

        if getattr(app.state, "agent_task", None) is not None:
            app.state.agent_task.cancel()
            try:
                await app.state.agent_task
            except asyncio.CancelledError:
                logger.info("Agent task cancelled")

app = FastAPI(title=API_NAME, version=API_VERSION, lifespan=lifespan)
app.add_middleware(RequestLoggerMiddleware, log_level=config.log_level)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
# Add the middleware for uniform error responses
from starlette.middleware.base import BaseHTTPMiddleware
app.add_middleware(BaseHTTPMiddleware, dispatch=uniform_error_middleware)
app.state.limiter = limiter

app.include_router(auth_router)
for router in all_routers:
    app.include_router(router)


# Exception handlers (must be defined before registration)
async def http_exception_handler(request: Request, exc):
    """Handle HTTP exceptions from FastAPI."""
    from fastapi import HTTPException
    if isinstance(exc, HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.create(exc.status_code, message).model_dump()
        )
    # Fall through to general handler
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.create(500, "Internal server error").model_dump()
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    error_details = exc.errors()
    message = "; ".join([
        f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}"
        for err in error_details
    ]) if error_details else "Request validation failed"
    
    return JSONResponse(
        status_code=422,
        content=ErrorResponse.create(422, message).model_dump()
    )


async def general_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse.create(500, str(exc) or "Internal server error").model_dump()
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content=ErrorResponse.create(429, "Rate limit exceeded").model_dump()
    )


# Register exception handlers
from fastapi import HTTPException
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


@app.get("/health")
async def health() -> dict[str, object]:
    uptime_seconds = time.time() - getattr(app.state, "start_time", time.time())
    return {"status": "ok", "uptime_seconds": int(uptime_seconds)}


@app.get("/")
async def root() -> dict[str, object]:
    enabled_modules: List[str] = [name for name, enabled in config.feature_flags.items() if enabled]
    return {
        "name": API_NAME,
        "tagline": "Control from anywhere",
        "description": "A star that sailors used for navigation. Metaphorically: your guiding point of control.",
        "version": API_VERSION,
        "enabled_modules": enabled_modules,
    }


@app.get("/auth/me")
async def read_current_user(current_user: str = Depends(get_current_user)) -> dict[str, str]:
    return {"username": current_user}


@app.get("/ping")
@limit_route("/ping")
async def ping(request: Request) -> dict[str, bool]:
    return {"pong": True}
