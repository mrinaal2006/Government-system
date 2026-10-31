"""Redis fixed-window rate limiter.

Fails *closed* for authentication endpoints (if Redis is down, login is refused
rather than left unthrottled) and *open* for general API traffic.
"""

from __future__ import annotations

import logging
import time

import redis

from app.core.errors import AppError
from app.infra.redis import get_redis

logger = logging.getLogger("app.ratelimit")


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Please wait and try again."


def hit(key: str, limit: int, window_seconds: int = 60, *, fail_closed: bool = False) -> None:
    bucket = int(time.time() // window_seconds)
    redis_key = f"rl:{key}:{bucket}"
    try:
        client = get_redis()
        pipe = client.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window_seconds + 5)
        count = int(pipe.execute()[0])
    except redis.RedisError:
        logger.warning("rate_limit_store_unavailable", extra={"key_prefix": key.split(":")[0]})
        if fail_closed:
            raise RateLimitedError("The service is temporarily unable to accept sign-ins.") from None
        return
    if count > limit:
        raise RateLimitedError()
