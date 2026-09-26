"""Fixed-window per-user rate limiting backed by Redis (no-op without Redis, see core/redis.py)."""

import time

from fastapi import Depends, HTTPException, status

from app.auth.security import current_user
from app.core.redis import get_redis, mark_unreachable, redis_usable
from app.models import User


def rate_limit(bucket: str, limit: int, window_s: int = 60):
    async def dep(user: User = Depends(current_user)) -> User:
        if not redis_usable():
            return user
        key = f"rl:{bucket}:{user.id}:{int(time.time() // window_s)}"
        try:
            r = get_redis()
            n = await r.incr(key)
            if n == 1:
                await r.expire(key, window_s)
        except Exception as exc:
            mark_unreachable(exc)
            return user
        if n > limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"rate limit: {limit} {bucket} per {window_s}s")
        return user

    return dep
