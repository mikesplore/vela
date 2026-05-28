import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import List

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from agent import start_agent_loop
from auth import router as auth_router, config as auth_config
from config import Config
from dependencies import get_current_user
from middleware import IPAllowlistMiddleware, RequestLoggerMiddleware
from rate_limiter import limiter, limit_route
from routers import all_routers
from routers import scheduler as scheduler_module

API_NAME = "Vela"
API_VERSION = "1.0.0"

config = Config()
logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
logger = logging.getLogger("vela.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.start_time = time.time()
    logger.info("Vela starting on %s:%s", config.host, config.port)
    try:
        scheduler_module.scheduler.start()
    except Exception:
        logger.warning("Scheduler failed to start or was already running")

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
app.add_middleware(IPAllowlistMiddleware, allowed_ips=config.allowed_ips)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SlowAPIMiddleware)
app.state.limiter = limiter

app.include_router(auth_router)
for router in all_routers:
    app.include_router(router)


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


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
    )


def main() -> None:
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
