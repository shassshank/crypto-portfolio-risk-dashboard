"""Tests for portfolio stress scenarios."""

import pandas as pd
import pytest

from src.stress import (
    apply_stress_scenario,
    build_broad_market_shocks,
    build_stablecoin_depeg_shocks,
)


@pytest.fixture
def valuation_df() -> pd.DataFrame:
    """Create deterministic valuation data for stress tests."""
    return pd.DataFrame(
        {
            "asset_symbol": ["BTC", "ETH", "SOL", "USDT"],
            "current_value_usd": [10000, 5000, 3000, 2000],
        }
    )


def test_btc_shock_only_affects_btc(valuation_df: pd.DataFrame) -> None:
    """A BTC-only shock should leave every other asset unchanged."""
    result = apply_stress_scenario(valuation_df, {"BTC": -0.10})
    impact_df = result["asset_impacts"]

    btc_row = impact_df.loc[impact_df["asset_symbol"] == "BTC"].iloc[0]
    eth_row = impact_df.loc[impact_df["asset_symbol"] == "ETH"].iloc[0]

    assert btc_row["shocked_value_usd"] == 9000
    assert btc_row["dollar_impact"] == -1000
    assert eth_row["shocked_value_usd"] == 5000
    assert eth_row["dollar_impact"] == 0


def test_broad_market_affects_all_non_stablecoins(
    valuation_df: pd.DataFrame,
) -> None:
    """A broad market shock should affect non-stablecoins only."""
    shocks = build_broad_market_shocks(valuation_df, shock=-0.20)
    result = apply_stress_scenario(valuation_df, shocks)
    impact_df = result["asset_impacts"]

    assert shocks == {"BTC": -0.20, "ETH": -0.20, "SOL": -0.20}
    assert impact_df.loc[impact_df["asset_symbol"] == "BTC", "dollar_impact"].iloc[0] == -2000
    assert impact_df.loc[impact_df["asset_symbol"] == "ETH", "dollar_impact"].iloc[0] == -1000
    assert impact_df.loc[impact_df["asset_symbol"] == "SOL", "dollar_impact"].iloc[0] == -600
    assert impact_df.loc[impact_df["asset_symbol"] == "USDT", "dollar_impact"].iloc[0] == 0


def test_stablecoin_depeg_affects_only_stablecoins(
    valuation_df: pd.DataFrame,
) -> None:
    """A stablecoin depeg shock should affect stablecoin symbols only."""
    shocks = build_stablecoin_depeg_shocks(valuation_df, shock=-0.05)
    result = apply_stress_scenario(valuation_df, shocks)
    impact_df = result["asset_impacts"]

    assert shocks == {"USDT": -0.05}
    assert impact_df.loc[impact_df["asset_symbol"] == "USDT", "dollar_impact"].iloc[0] == -100
    assert impact_df.loc[impact_df["asset_symbol"] == "BTC", "dollar_impact"].iloc[0] == 0


def test_total_loss_calculation_is_correct(valuation_df: pd.DataFrame) -> None:
    """Portfolio summary should calculate total dollar and percentage loss."""
    result = apply_stress_scenario(valuation_df, {"BTC": -0.10, "ETH": -0.20})
    summary = result["summary"]

    assert summary["current_portfolio_value"] == 20000
    assert summary["shocked_portfolio_value"] == 18000
    assert summary["total_dollar_loss"] == 2000
    assert summary["total_pct_loss"] == pytest.approx(0.10)


def test_custom_shock_works(valuation_df: pd.DataFrame) -> None:
    """Custom asset shocks should be applied by asset symbol."""
    result = apply_stress_scenario(valuation_df, {"SOL": -0.50})
    impact_df = result["asset_impacts"]

    sol_row = impact_df.loc[impact_df["asset_symbol"] == "SOL"].iloc[0]

    assert sol_row["shocked_value_usd"] == 1500
    assert result["summary"]["total_dollar_loss"] == 1500
