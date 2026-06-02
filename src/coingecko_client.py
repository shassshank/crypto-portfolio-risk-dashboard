"""CoinGecko API client with local caching and retry handling."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

from src.config import settings
from src.storage import get_cached_response, make_cache_key, set_cached_response


RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_LAST_DATA_SOURCE = "unknown"


class CoinGeckoAPIError(RuntimeError):
    """Raised when CoinGecko returns an unusable response."""


def get_current_prices(
    coingecko_ids: list[str],
    vs_currency: str = "usd",
    force_refresh: bool = False,
) -> dict[str, float]:
    """Fetch current prices for CoinGecko IDs using the simple price endpoint."""
    normalized_ids = sorted({coin_id.strip().lower() for coin_id in coingecko_ids})
    if not normalized_ids:
        return {}

    params = {
        "ids": ",".join(normalized_ids),
        "vs_currencies": vs_currency.lower(),
    }
    data = _get_json_with_cache(
        "simple_price",
        "/simple/price",
        params,
        force_refresh=force_refresh,
    )

    prices: dict[str, float] = {}
    for coin_id in normalized_ids:
        try:
            prices[coin_id] = float(data[coin_id][vs_currency.lower()])
        except (KeyError, TypeError, ValueError) as exc:
            raise CoinGeckoAPIError(
                f"CoinGecko response did not include a valid price for {coin_id}."
            ) from exc

    return prices


def get_market_chart(
    coingecko_id: str,
    vs_currency: str = "usd",
    days: int = 90,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch historical market prices for one CoinGecko ID."""
    normalized_id = coingecko_id.strip().lower()
    params = {
        "vs_currency": vs_currency.lower(),
        "days": days,
    }
    data = _get_json_with_cache(
        "market_chart",
        f"/coins/{normalized_id}/market_chart",
        params,
        force_refresh=force_refresh,
    )

    prices = data.get("prices")
    if not isinstance(prices, list):
        raise CoinGeckoAPIError("CoinGecko market chart response did not include prices.")

    chart_df = pd.DataFrame(prices, columns=["timestamp_ms", "price"])
    if chart_df.empty:
        return pd.DataFrame(columns=["date", "price"])

    chart_df["date"] = pd.to_datetime(chart_df["timestamp_ms"], unit="ms").dt.date
    chart_df["price"] = chart_df["price"].astype(float)
    return chart_df[["date", "price"]]


def ping_coingecko() -> bool:
    """Return True when the public CoinGecko API responds to ping."""
    try:
        data = _request_json("/ping", params={})
    except CoinGeckoAPIError:
        return False

    return bool(data)


def get_last_data_source() -> str:
    """Return the source used by the most recent client data call."""
    return _LAST_DATA_SOURCE


def _get_json_with_cache(
    name: str,
    endpoint: str,
    params: dict[str, Any],
    force_refresh: bool = False,
) -> Any:
    """Read a cached response or fetch and cache a fresh API response."""
    global _LAST_DATA_SOURCE

    cache_key = make_cache_key(name, {"endpoint": endpoint, **params})
    cached = None if force_refresh else get_cached_response(cache_key)
    if cached is not None:
        _LAST_DATA_SOURCE = "cache"
        return cached

    data = _request_json(endpoint, params=params)
    set_cached_response(cache_key, data)
    _LAST_DATA_SOURCE = "api"
    return data


def _request_json(
    endpoint: str,
    params: dict[str, Any],
) -> Any:
    """Request JSON from CoinGecko with retries for temporary failures."""
    url = f"{settings.coingecko_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    last_error: str | None = None
    max_attempts = max(settings.coingecko_max_attempts, 1)

    for attempt in range(1, max_attempts + 1):
        response = None
        try:
            response = requests.get(
                url,
                params=params,
                timeout=settings.coingecko_timeout_seconds,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
        else:
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise CoinGeckoAPIError(
                        f"CoinGecko returned invalid JSON for {endpoint}."
                    ) from exc

            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            if response.status_code not in RETRY_STATUS_CODES:
                break

        if attempt < max_attempts:
            time.sleep(_retry_sleep_seconds(attempt, response))

    raise CoinGeckoAPIError(
        f"CoinGecko request failed for {endpoint}. Last error: {last_error}"
    )


def _retry_sleep_seconds(attempt: int, response: requests.Response | None) -> float:
    """Calculate retry sleep duration, respecting Retry-After when provided."""
    retry_after = (
        getattr(response, "headers", {}).get("Retry-After") if response else None
    )
    if retry_after:
        try:
            return min(float(retry_after), 10.0)
        except ValueError:
            pass
    return settings.coingecko_backoff_seconds * attempt
