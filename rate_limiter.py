from slowapi import Limiter
from slowapi.util import get_remote_address

from config import Config

config = Config()
limiter = Limiter(key_func=get_remote_address, default_limits=[config.rate_limit_default])


def limit_route(route: str):
    limit = config.route_rate_limits.get(route)
    if limit:
        return limiter.limit(limit)
    return lambda func: func
