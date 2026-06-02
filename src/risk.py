"""Risk metric calculations for portfolio analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd


STABLECOIN_IDS = {
    "tether",
    "usd-coin",
    "dai",
    "binance-usd",
    "true-usd",
    "frax",
    "usdd",
    "paypal-usd",
}


def calculate_daily_returns(value_series: pd.Series) -> pd.Series:
    """Calculate daily percentage returns from a portfolio value series."""
    if value_series.empty:
        return pd.Series(dtype=float, name="daily_return")

    numeric_values = pd.to_numeric(value_series, errors="coerce")
    returns = numeric_values.pct_change()
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    returns.name = "daily_return"
    return returns


def calculate_annualized_volatility(
    daily_returns: pd.Series,
    periods_per_year: int = 365,
) -> float:
    """Calculate annualized volatility from daily returns."""
    clean_returns = _clean_returns(daily_returns)
    if clean_returns.empty or periods_per_year <= 0:
        return 0.0

    return float(clean_returns.std(ddof=0) * np.sqrt(periods_per_year))


def calculate_max_drawdown(value_series: pd.Series) -> float:
    """Calculate the maximum drawdown as a negative percentage return."""
    drawdowns = calculate_drawdown_series(value_series)
    if drawdowns.empty:
        return 0.0

    return float(drawdowns.min())


def calculate_historical_var(
    daily_returns: pd.Series,
    confidence_level: float = 0.95,
) -> float:
    """Calculate historical VaR as a positive loss magnitude."""
    clean_returns = _clean_returns(daily_returns)
    if clean_returns.empty:
        return 0.0

    loss_quantile = np.quantile(clean_returns, 1 - confidence_level)
    return float(max(0.0, -loss_quantile))


def calculate_expected_shortfall(
    daily_returns: pd.Series,
    confidence_level: float = 0.95,
) -> float:
    """Calculate expected shortfall as a positive average tail loss magnitude."""
    clean_returns = _clean_returns(daily_returns)
    if clean_returns.empty:
        return 0.0

    loss_quantile = np.quantile(clean_returns, 1 - confidence_level)
    tail_returns = clean_returns[clean_returns <= loss_quantile]
    if tail_returns.empty:
        return 0.0

    return float(max(0.0, -tail_returns.mean()))


def calculate_concentration_metrics(valuation_df: pd.DataFrame) -> dict[str, float]:
    """Calculate portfolio concentration metrics from valuation data."""
    allocations = _get_allocations(valuation_df)
    if allocations.empty:
        return {
            "largest_asset_allocation": 0.0,
            "top_3_allocation": 0.0,
            "hhi_score": 0.0,
        }

    sorted_allocations = allocations.sort_values(ascending=False)
    return {
        "largest_asset_allocation": float(sorted_allocations.iloc[0]),
        "top_3_allocation": float(sorted_allocations.head(3).sum()),
        "hhi_score": float((allocations**2).sum()),
    }


def calculate_risk_score(
    volatility: float,
    max_drawdown: float,
    largest_asset_allocation: float,
    stablecoin_allocation: float,
    number_of_assets: int,
) -> dict:
    """Calculate a simple explainable portfolio risk score from 0 to 100."""
    volatility_points = min(max(volatility, 0.0) / 0.80, 1.0) * 30
    drawdown_points = min(abs(min(max_drawdown, 0.0)) / 0.70, 1.0) * 25
    concentration_points = min(max(largest_asset_allocation, 0.0), 1.0) * 20
    stablecoin_points = max(1.0 - min(max(stablecoin_allocation, 0.0), 1.0), 0.0) * 10
    diversification_points = max((10 - max(number_of_assets, 0)) / 10, 0.0) * 15

    components = {
        "volatility": round(volatility_points, 2),
        "max_drawdown": round(drawdown_points, 2),
        "concentration": round(concentration_points, 2),
        "stablecoin_exposure": round(stablecoin_points, 2),
        "diversification": round(diversification_points, 2),
    }
    score = min(sum(components.values()), 100.0)

    return {
        "score": round(score, 2),
        "components": components,
        "explanation": [
            f"Annualized volatility adds {components['volatility']} points.",
            f"Maximum drawdown adds {components['max_drawdown']} points.",
            f"Largest asset concentration adds {components['concentration']} points.",
            f"Stablecoin allocation adds {components['stablecoin_exposure']} points.",
            f"Asset count diversification adds {components['diversification']} points.",
        ],
    }


def calculate_drawdown_series(value_series: pd.Series) -> pd.Series:
    """Calculate a drawdown series from portfolio values."""
    if value_series.empty:
        return pd.Series(dtype=float, name="drawdown")

    numeric_values = pd.to_numeric(value_series, errors="coerce")
    running_peak = numeric_values.cummax()
    drawdowns = (numeric_values / running_peak) - 1
    drawdowns = drawdowns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    drawdowns.name = "drawdown"
    return drawdowns


def calculate_stablecoin_allocation(valuation_df: pd.DataFrame) -> float:
    """Calculate allocation assigned to common stablecoin CoinGecko IDs."""
    if valuation_df.empty or "coingecko_id" not in valuation_df.columns:
        return 0.0

    allocations = _get_allocations(valuation_df)
    stablecoin_mask = valuation_df["coingecko_id"].isin(STABLECOIN_IDS)
    return float(allocations.loc[stablecoin_mask].sum())


def _clean_returns(daily_returns: pd.Series) -> pd.Series:
    """Return finite daily returns for risk calculations."""
    numeric_returns = pd.to_numeric(daily_returns, errors="coerce")
    return numeric_returns.replace([np.inf, -np.inf], np.nan).dropna()


def _get_allocations(valuation_df: pd.DataFrame) -> pd.Series:
    """Return allocation percentages from valuation data."""
    if valuation_df.empty:
        return pd.Series(dtype=float)
    if "allocation_pct" in valuation_df.columns:
        return pd.to_numeric(valuation_df["allocation_pct"], errors="coerce").fillna(0.0)
    if "current_value_usd" not in valuation_df.columns:
        return pd.Series(dtype=float)

    values = pd.to_numeric(valuation_df["current_value_usd"], errors="coerce").fillna(0.0)
    total_value = values.sum()
    if total_value <= 0:
        return pd.Series(0.0, index=valuation_df.index)
    return values / total_value
