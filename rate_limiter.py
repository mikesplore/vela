from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request

from config import Config

config = Config()


def get_client_ip(request: Request) -> str:
    # If the request is forwarded by the agent, use the original IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Get the first IP in the list
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_client_ip, default_limits=[config.rate_limit_default])


def limit_route(route: str):
    limit = config.route_rate_limits.get(route)
    if limit:
        return limiter.limit(limit)
    return lambda func: func
