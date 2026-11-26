"""
Rate limiting (tiêu chí 7).

Sliding window 60 giây lưu trên Redis Sorted Set để chia sẻ giữa mọi worker/instance
và giữ nguyên trạng thái sau khi restart agent.
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def _rate_limit_key(api_key: str) -> str:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"ratelimit:{key_hash}"


def check_rate_limit(key: str) -> None:
    """Kiểm tra giới hạn request/phút bằng Redis Sorted Set; vượt ngưỡng trả HTTP 429."""
    if r is None:
        raise HTTPException(status_code=503, detail="Rate limiter backend unavailable")

    limit = settings.rate_limit_per_minute
    redis_key = _rate_limit_key(key)
    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        r.zremrangebyscore(redis_key, 0, window_start)
        current_count = r.zcard(redis_key)

        if current_count >= limit:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now) + 1)
            else:
                retry_after = WINDOW_SECONDS
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now:.6f}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except (redis.RedisError, OSError):
        raise HTTPException(status_code=503, detail="Rate limiter backend unavailable")
