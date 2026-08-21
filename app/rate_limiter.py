from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from app.utils.config import get_config

config = get_config()


def get_client_ip(request: Request) -> str:
    cfg = get_config()
    peer = request.client.host if request.client else "unknown"
    if peer in set(cfg.trusted_proxy_ips):
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip, default_limits=[config.rate_limit_default])


def limit_route(route: str):
    limit = config.route_rate_limits.get(route)
    if limit:
        return limiter.limit(limit)
    return lambda func: func
