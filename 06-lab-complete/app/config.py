"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.
"""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_budget() -> float:
    if os.getenv("DAILY_BUDGET_USD") not in (None, ""):
        return _env_float("DAILY_BUDGET_USD", 1.0)
    if os.getenv("MONTHLY_BUDGET_USD") not in (None, ""):
        return _env_float("MONTHLY_BUDGET_USD", 10.0)
    return 1.0


@dataclass
class Settings:
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").strip().lower() in ("1", "true", "yes")
    )
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    rate_limit_per_minute: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10)
    )
    daily_budget_usd: float = field(default_factory=_env_budget)
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())


settings = Settings()
