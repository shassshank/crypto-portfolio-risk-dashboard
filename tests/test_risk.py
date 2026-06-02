"""Tests for portfolio risk metrics."""

import pandas as pd
import pytest

from src.risk import (
    calculate_annualized_volatility,
    calculate_concentration_metrics,
    calculate_daily_returns,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_max_drawdown,
    calculate_risk_score,
)


def test_calculate_daily_returns() -> None:
    """Daily returns should come from percentage changes in portfolio value."""
    value_series = pd.Series([100, 110, 99])

    daily_returns = calculate_daily_returns(value_series)

    assert daily_returns.tolist() == [0, pytest.approx(0.10), pytest.approx(-0.10)]


def test_annualized_volatility_is_non_negative() -> None:
    """Annualized volatility should never be negative."""
    daily_returns = pd.Series([0, 0.01, -0.02, 0.03])

    volatility = calculate_annualized_volatility(daily_returns)

    assert volatility >= 0


def test_calculate_max_drawdown() -> None:
    """Maximum drawdown should be the worst peak-to-trough decline."""
    value_series = pd.Series([100, 120, 90, 150, 75])

    max_drawdown = calculate_max_drawdown(value_series)

    assert max_drawdown == pytest.approx(-0.50)


def test_calculate_historical_var() -> None:
    """Historical VaR should return a positive loss magnitude."""
    daily_returns = pd.Series([-0.10, -0.05, 0.02, 0.03])

    var = calculate_historical_var(daily_returns, confidence_level=0.75)

    assert var == pytest.approx(0.0625)


def test_calculate_expected_shortfall() -> None:
    """Expected shortfall should average losses beyond the VaR threshold."""
    daily_returns = pd.Series([-0.10, -0.05, 0.02, 0.03])

    expected_shortfall = calculate_expected_shortfall(
        daily_returns,
        confidence_level=0.75,
    )

    assert expected_shortfall == pytest.approx(0.10)


def test_calculate_concentration_metrics() -> None:
    """Concentration metrics should summarize allocation concentration."""
    valuation_df = pd.DataFrame(
        {
            "asset_symbol": ["BTC", "ETH", "SOL", "USDT"],
            "coingecko_id": ["bitcoin", "ethereum", "solana", "tether"],
            "allocation_pct": [0.50, 0.25, 0.15, 0.10],
        }
    )

    metrics = calculate_concentration_metrics(valuation_df)

    assert metrics["largest_asset_allocation"] == pytest.approx(0.50)
    assert metrics["top_3_allocation"] == pytest.approx(0.90)
    assert metrics["hhi_score"] == pytest.approx(0.345)


def test_calculate_risk_score_is_bounded_and_explainable() -> None:
    """Risk score should be bounded from 0 to 100 and include components."""
    risk_score = calculate_risk_score(
        volatility=0.60,
        max_drawdown=-0.40,
        largest_asset_allocation=0.50,
        stablecoin_allocation=0.10,
        number_of_assets=4,
    )

    assert 0 <= risk_score["score"] <= 100
    assert set(risk_score["components"]) == {
        "volatility",
        "max_drawdown",
        "concentration",
        "stablecoin_exposure",
        "diversification",
    }
    assert risk_score["explanation"]
