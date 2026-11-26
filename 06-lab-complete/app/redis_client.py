"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

App vẫn khởi động bình thường khi Redis chưa sẵn sàng (không ping khi import).
"""
from typing import Optional

import redis

from app.config import settings


def _create_client() -> Optional[redis.Redis]:
    if not settings.redis_url:
        return None
    return redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


r: Optional[redis.Redis] = _create_client()


def redis_healthy() -> bool:
    """Kiểm tra kết nối Redis cho endpoint /ready."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except (redis.RedisError, OSError):
        return False


def close_redis() -> None:
    """Đóng connection pool khi shutdown."""
    if r is not None:
        try:
            r.close()
        except Exception:
            pass
