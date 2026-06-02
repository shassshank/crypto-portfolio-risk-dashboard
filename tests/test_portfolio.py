"""Tests for portfolio valuation logic."""

import pandas as pd
import pytest

from src.portfolio import (
    build_historical_portfolio_value,
    calculate_cumulative_return,
    calculate_daily_returns,
    calculate_portfolio_valuation,
)


FAKE_PRICES = {
    "bitcoin": 50000,
    "ethereum": 3000,
    "solana": 100,
    "chainlink": 15,
    "tether": 1,
}


@pytest.fixture
def sample_holdings_df() -> pd.DataFrame:
    """Create deterministic holdings for valuation tests."""
    return pd.DataFrame(
        [
            {
                "asset_symbol": "BTC",
                "coingecko_id": "bitcoin",
                "quantity": 0.25,
                "avg_buy_price_usd": 42000,
            },
            {
                "asset_symbol": "ETH",
                "coingecko_id": "ethereum",
                "quantity": 2.5,
                "avg_buy_price_usd": 2400,
            },
            {
                "asset_symbol": "SOL",
                "coingecko_id": "solana",
                "quantity": 40,
                "avg_buy_price_usd": 95,
            },
            {
                "asset_symbol": "LINK",
                "coingecko_id": "chainlink",
                "quantity": 100,
                "avg_buy_price_usd": 14,
            },
            {
                "asset_symbol": "USDT",
                "coingecko_id": "tether",
                "quantity": 1000,
                "avg_buy_price_usd": 1,
            },
        ]
    )


def test_current_value_calculation(sample_holdings_df: pd.DataFrame) -> None:
    """Current value should equal quantity multiplied by current price."""
    valuation_df = calculate_portfolio_valuation(sample_holdings_df, FAKE_PRICES)

    btc_row = valuation_df.loc[valuation_df["coingecko_id"] == "bitcoin"].iloc[0]

    assert btc_row["current_value_usd"] == 12500


def test_cost_basis_calculation(sample_holdings_df: pd.DataFrame) -> None:
    """Cost basis should equal quantity multiplied by average buy price."""
    valuation_df = calculate_portfolio_valuation(sample_holdings_df, FAKE_PRICES)

    eth_row = valuation_df.loc[valuation_df["coingecko_id"] == "ethereum"].iloc[0]

    assert eth_row["cost_basis_usd"] == 6000


def test_pnl_calculation(sample_holdings_df: pd.DataFrame) -> None:
    """Unrealized PnL should equal current value minus cost basis."""
    valuation_df = calculate_portfolio_valuation(sample_holdings_df, FAKE_PRICES)

    sol_row = valuation_df.loc[valuation_df["coingecko_id"] == "solana"].iloc[0]

    assert sol_row["unrealized_pnl_usd"] == 200
    assert sol_row["unrealized_pnl_pct"] == pytest.approx(200 / 3800)


def test_allocation_sums_to_one(sample_holdings_df: pd.DataFrame) -> None:
    """Portfolio allocation percentages should sum to roughly 1.0."""
    valuation_df = calculate_portfolio_valuation(sample_holdings_df, FAKE_PRICES)

    assert valuation_df["allocation_pct"].sum() == pytest.approx(1.0)


def test_zero_cost_basis_does_not_crash() -> None:
    """Zero cost basis should produce a safe zero PnL percentage."""
    holdings_df = pd.DataFrame(
        [
            {
                "asset_symbol": "BTC",
                "coingecko_id": "bitcoin",
                "quantity": 1,
                "avg_buy_price_usd": 0,
            }
        ]
    )

    valuation_df = calculate_portfolio_valuation(holdings_df, FAKE_PRICES)

    assert valuation_df.loc[0, "cost_basis_usd"] == 0
    assert valuation_df.loc[0, "current_value_usd"] == 50000
    assert valuation_df.loc[0, "unrealized_pnl_pct"] == 0
    assert valuation_df.loc[0, "allocation_pct"] == 1


def test_build_historical_portfolio_value_aligns_and_forward_fills() -> None:
    """Historical values should align dates and forward-fill later missing prices."""
    holdings_df = pd.DataFrame(
        [
            {
                "asset_symbol": "BTC",
                "coingecko_id": "bitcoin",
                "quantity": 2,
                "avg_buy_price_usd": 100,
            },
            {
                "asset_symbol": "ETH",
                "coingecko_id": "ethereum",
                "quantity": 3,
                "avg_buy_price_usd": 50,
            },
        ]
    )
    price_history = {
        "bitcoin": pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "price": [100, 110, 120],
            }
        ),
        "ethereum": pd.DataFrame(
            {
                "date": ["2026-01-02", "2026-01-03"],
                "price": [50, 60],
            }
        ),
    }

    historical_df = build_historical_portfolio_value(holdings_df, price_history)

    assert historical_df["total_value_usd"].tolist() == [200, 370, 420]
    assert historical_df["BTC_value_usd"].tolist() == [200, 220, 240]
    assert pd.isna(historical_df.loc[0, "ETH_value_usd"])
    assert historical_df["ETH_value_usd"].iloc[1:].tolist() == [150, 180]


def test_build_historical_portfolio_value_skips_missing_history() -> None:
    """Missing asset histories should not crash historical value building."""
    holdings_df = pd.DataFrame(
        [
            {
                "asset_symbol": "BTC",
                "coingecko_id": "bitcoin",
                "quantity": 1,
                "avg_buy_price_usd": 100,
            },
            {
                "asset_symbol": "ETH",
                "coingecko_id": "ethereum",
                "quantity": 1,
                "avg_buy_price_usd": 50,
            },
        ]
    )
    price_history = {
        "bitcoin": pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "price": [100, 120],
            }
        )
    }

    historical_df = build_historical_portfolio_value(holdings_df, price_history)

    assert list(historical_df.columns) == [
        "date",
        "total_value_usd",
        "BTC_value_usd",
    ]
    assert historical_df["total_value_usd"].tolist() == [100, 120]


def test_build_historical_portfolio_value_returns_empty_when_no_history() -> None:
    """No usable price history should return an empty historical value dataframe."""
    holdings_df = pd.DataFrame(
        [
            {
                "asset_symbol": "BTC",
                "coingecko_id": "bitcoin",
                "quantity": 1,
                "avg_buy_price_usd": 100,
            }
        ]
    )

    historical_df = build_historical_portfolio_value(holdings_df, {})

    assert historical_df.empty
    assert list(historical_df.columns) == ["date", "total_value_usd"]


def test_calculate_daily_returns() -> None:
    """Daily returns should be calculated from total portfolio values."""
    historical_df = pd.DataFrame({"total_value_usd": [100, 110, 99]})

    returns = calculate_daily_returns(historical_df)

    assert returns.tolist() == [0, pytest.approx(0.10), pytest.approx(-0.10)]


def test_calculate_cumulative_return() -> None:
    """Cumulative return should be based on the first positive portfolio value."""
    historical_df = pd.DataFrame({"total_value_usd": [100, 110, 121]})

    cumulative_return = calculate_cumulative_return(historical_df)

    assert cumulative_return.tolist() == [0, pytest.approx(0.10), pytest.approx(0.21)]
