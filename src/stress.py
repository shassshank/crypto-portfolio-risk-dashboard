"""Stress testing scenarios for portfolio valuation data."""

from __future__ import annotations

import pandas as pd


STABLECOIN_SYMBOLS = {"USDT", "USDC", "DAI", "BUSD", "TUSD"}
BTC_SYMBOL = "BTC"
ETH_SYMBOL = "ETH"


PRESET_SCENARIOS = {
    "BTC drops 10%": {BTC_SYMBOL: -0.10},
    "ETH drops 15%": {ETH_SYMBOL: -0.15},
    "Broad market drops 20%": "broad_market",
    "Altcoins drop 30%": "altcoins",
    "Stablecoins depeg 5%": "stablecoins",
    "Custom shock by asset": "custom",
}


def apply_stress_scenario(
    valuation_df: pd.DataFrame,
    shocks: dict[str, float],
) -> dict:
    """Apply asset-level percentage shocks and return impacts plus summary."""
    impact_df = valuation_df[["asset_symbol", "current_value_usd"]].copy()
    impact_df["asset_symbol"] = impact_df["asset_symbol"].str.upper()
    normalized_shocks = {
        asset_symbol.strip().upper(): float(shock)
        for asset_symbol, shock in shocks.items()
    }
    impact_df["shock"] = impact_df["asset_symbol"].map(normalized_shocks).fillna(0.0)
    impact_df["shocked_value_usd"] = (
        impact_df["current_value_usd"] * (1 + impact_df["shock"])
    ).clip(lower=0.0)
    impact_df["dollar_impact"] = (
        impact_df["shocked_value_usd"] - impact_df["current_value_usd"]
    )
    impact_df["pct_impact"] = impact_df["shock"]

    current_portfolio_value = float(impact_df["current_value_usd"].sum())
    shocked_portfolio_value = float(impact_df["shocked_value_usd"].sum())
    total_dollar_loss = current_portfolio_value - shocked_portfolio_value
    total_pct_loss = (
        total_dollar_loss / current_portfolio_value
        if current_portfolio_value > 0
        else 0.0
    )

    summary = {
        "current_portfolio_value": current_portfolio_value,
        "shocked_portfolio_value": shocked_portfolio_value,
        "total_dollar_loss": float(total_dollar_loss),
        "total_pct_loss": float(total_pct_loss),
    }

    output_columns = [
        "asset_symbol",
        "current_value_usd",
        "shocked_value_usd",
        "dollar_impact",
        "pct_impact",
    ]
    return {
        "asset_impacts": impact_df[output_columns],
        "summary": summary,
    }


def get_preset_scenario_shocks(
    valuation_df: pd.DataFrame,
    scenario_name: str,
) -> dict[str, float]:
    """Build shocks for a named preset scenario."""
    scenario = PRESET_SCENARIOS.get(scenario_name)
    if isinstance(scenario, dict):
        return scenario
    if scenario == "broad_market":
        return build_broad_market_shocks(valuation_df, shock=-0.20)
    if scenario == "altcoins":
        return build_altcoin_shocks(valuation_df, shock=-0.30)
    if scenario == "stablecoins":
        return build_stablecoin_depeg_shocks(valuation_df, shock=-0.05)
    return {}


def build_broad_market_shocks(
    valuation_df: pd.DataFrame,
    shock: float = -0.20,
) -> dict[str, float]:
    """Apply a shock to all non-stablecoin assets."""
    return {
        asset_symbol: shock
        for asset_symbol in _asset_symbols(valuation_df)
        if asset_symbol not in STABLECOIN_SYMBOLS
    }


def build_altcoin_shocks(
    valuation_df: pd.DataFrame,
    shock: float = -0.30,
) -> dict[str, float]:
    """Apply a shock to non-BTC, non-ETH, non-stablecoin assets."""
    excluded_symbols = {BTC_SYMBOL, ETH_SYMBOL, *STABLECOIN_SYMBOLS}
    return {
        asset_symbol: shock
        for asset_symbol in _asset_symbols(valuation_df)
        if asset_symbol not in excluded_symbols
    }


def build_stablecoin_depeg_shocks(
    valuation_df: pd.DataFrame,
    shock: float = -0.05,
) -> dict[str, float]:
    """Apply a depeg shock only to common stablecoin assets."""
    return {
        asset_symbol: shock
        for asset_symbol in _asset_symbols(valuation_df)
        if asset_symbol in STABLECOIN_SYMBOLS
    }


def _asset_symbols(valuation_df: pd.DataFrame) -> list[str]:
    """Return uppercase asset symbols from valuation data."""
    if valuation_df.empty or "asset_symbol" not in valuation_df.columns:
        return []

    return valuation_df["asset_symbol"].str.upper().tolist()
