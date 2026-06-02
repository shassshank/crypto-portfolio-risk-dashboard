"""Tests for the CoinGecko API client."""

from pathlib import Path

import pytest

from src import coingecko_client, storage


class FakeResponse:
    """Small fake requests response for deterministic client tests."""

    def __init__(self, status_code: int, data, text: str = "") -> None:
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        """Return fake JSON data."""
        return self._data


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path: Path, monkeypatch) -> None:
    """Isolate client cache writes for every test."""
    monkeypatch.setattr(storage, "CACHE_DIR", tmp_path)


def test_get_current_prices_fetches_and_caches(monkeypatch) -> None:
    """Current prices should be parsed and cached from the simple price endpoint."""
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return FakeResponse(
            200,
            {
                "bitcoin": {"usd": 50000},
                "ethereum": {"usd": 3000},
            },
        )

    monkeypatch.setattr(coingecko_client.requests, "get", fake_get)

    prices = coingecko_client.get_current_prices(["bitcoin", "ethereum"])
    cached_prices = coingecko_client.get_current_prices(["ethereum", "bitcoin"])

    assert prices == {"bitcoin": 50000.0, "ethereum": 3000.0}
    assert cached_prices == prices
    assert len(calls) == 1
    assert coingecko_client.get_last_data_source() == "cache"


def test_get_current_prices_force_refresh_bypasses_cache(monkeypatch) -> None:
    """Force refresh should bypass a valid cached response."""
    calls = []
    responses = [
        FakeResponse(200, {"bitcoin": {"usd": 50000}}),
        FakeResponse(200, {"bitcoin": {"usd": 51000}}),
    ]

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return responses.pop(0)

    monkeypatch.setattr(coingecko_client.requests, "get", fake_get)

    first_prices = coingecko_client.get_current_prices(["bitcoin"])
    refreshed_prices = coingecko_client.get_current_prices(
        ["bitcoin"],
        force_refresh=True,
    )

    assert first_prices == {"bitcoin": 50000.0}
    assert refreshed_prices == {"bitcoin": 51000.0}
    assert len(calls) == 2
    assert coingecko_client.get_last_data_source() == "api"


def test_get_market_chart_returns_date_price_dataframe(monkeypatch) -> None:
    """Market chart responses should become a date and price dataframe."""
    monkeypatch.setattr(
        coingecko_client.requests,
        "get",
        lambda url, params, timeout: FakeResponse(
            200,
            {
                "prices": [
                    [1717200000000, 50000],
                    [1717286400000, 51000],
                ]
            },
        ),
    )

    chart_df = coingecko_client.get_market_chart("bitcoin", days=2)

    assert list(chart_df.columns) == ["date", "price"]
    assert chart_df["price"].tolist() == [50000.0, 51000.0]


def test_temporary_errors_are_retried(monkeypatch) -> None:
    """Temporary API errors should be retried before failing."""
    responses = [
        FakeResponse(503, {}, "service unavailable"),
        FakeResponse(200, {"bitcoin": {"usd": 50000}}),
    ]

    monkeypatch.setattr(coingecko_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        coingecko_client.requests,
        "get",
        lambda url, params, timeout: responses.pop(0),
    )

    prices = coingecko_client.get_current_prices(["bitcoin"])

    assert prices == {"bitcoin": 50000.0}
    assert responses == []


def test_ping_returns_false_on_api_error(monkeypatch) -> None:
    """Ping should return False instead of raising on API failure."""
    monkeypatch.setattr(coingecko_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(
        coingecko_client.requests,
        "get",
        lambda url, params, timeout: FakeResponse(500, {}, "server error"),
    )

    assert coingecko_client.ping_coingecko() is False
