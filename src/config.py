"""Application configuration defaults."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _get_int_env(name: str, default: int) -> int:
    """Read an integer environment variable with a safe fallback."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _get_float_env(name: str, default: float) -> float:
    """Read a float environment variable with a safe fallback."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


@dataclass(frozen=True)
class AppSettings:
    """Basic application settings used across the project."""

    default_currency: str = os.getenv("DEFAULT_CURRENCY", "usd")
    default_lookback_days: int = int(os.getenv("DEFAULT_LOOKBACK_DAYS", "90"))
    coingecko_base_url: str = os.getenv(
        "COINGECKO_BASE_URL",
        "https://api.coingecko.com/api/v3",
    )
    cache_ttl_seconds: int = _get_int_env("CACHE_TTL_SECONDS", 300)
    coingecko_timeout_seconds: int = _get_int_env("COINGECKO_TIMEOUT_SECONDS", 10)
    coingecko_max_attempts: int = _get_int_env("COINGECKO_MAX_ATTEMPTS", 3)
    coingecko_backoff_seconds: float = _get_float_env("COINGECKO_BACKOFF_SECONDS", 0.75)


settings = AppSettings()
