"""
Cost guard (tiêu chí 8).

Cộng dồn chi phí LLM (tính theo token) vào Redis; vượt ngân sách trả HTTP 402.
"""
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
COST_TTL_SECONDS = 48 * 3600


def _budget_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost tracking backend unavailable")

    try:
        raw_total = r.get(_budget_key())
        current_cost = float(raw_total) if raw_total is not None else 0.0
    except (redis.RedisError, OSError, ValueError):
        raise HTTPException(status_code=503, detail="Cost tracking backend unavailable")

    if current_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily LLM budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )

    if r is None:
        return cost

    key = _budget_key()
    try:
        pipe = r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, COST_TTL_SECONDS)
        pipe.execute()
    except (redis.RedisError, OSError):
        pass

    return cost
