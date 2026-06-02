"""Portfolio loading, validation, and valuation logic."""

from pathlib import Path

import numpy as np
import pandas as pd

from src.models import Holding


VALUATION_COLUMNS = [
    "asset_symbol",
    "coingecko_id",
    "quantity",
    "avg_buy_price_usd",
    "current_price_usd",
    "cost_basis_usd",
    "current_value_usd",
    "unrealized_pnl_usd",
    "unrealized_pnl_pct",
    "allocation_pct",
]


def load_portfolio_csv(path: str) -> pd.DataFrame:
    """Load a portfolio CSV file into a dataframe."""
    return pd.read_csv(Path(path))


def validate_portfolio_df(df: pd.DataFrame) -> list[Holding]:
    """Validate portfolio rows and return normalized holdings."""
    records = df.to_dict(orient="records")
    return [Holding(**record) for record in records]


def calculate_portfolio_valuation(
    holdings_df: pd.DataFrame,
    prices: dict[str, float],
) -> pd.DataFrame:
    """Calculate portfolio valuation metrics using current USD prices."""
    holdings = validate_portfolio_df(holdings_df)
    rows = []

    for holding in holdings:
        if holding.coingecko_id not in prices:
            raise ValueError(f"Missing price for coingecko_id: {holding.coingecko_id}")

        current_price_usd = float(prices[holding.coingecko_id])
        cost_basis_usd = holding.quantity * holding.avg_buy_price_usd
        current_value_usd = holding.quantity * current_price_usd
        unrealized_pnl_usd = current_value_usd - cost_basis_usd
        unrealized_pnl_pct = (
            unrealized_pnl_usd / cost_basis_usd if cost_basis_usd > 0 else 0.0
        )

        rows.append(
            {
                "asset_symbol": holding.asset_symbol,
                "coingecko_id": holding.coingecko_id,
                "quantity": holding.quantity,
                "avg_buy_price_usd": holding.avg_buy_price_usd,
                "current_price_usd": current_price_usd,
                "cost_basis_usd": cost_basis_usd,
                "current_value_usd": current_value_usd,
                "unrealized_pnl_usd": unrealized_pnl_usd,
                "unrealized_pnl_pct": unrealized_pnl_pct,
            }
        )

    valuation_df = pd.DataFrame(rows)
    total_portfolio_value = valuation_df["current_value_usd"].sum()
    valuation_df["allocation_pct"] = (
        valuation_df["current_value_usd"] / total_portfolio_value
        if total_portfolio_value > 0
        else 0.0
    )

    return valuation_df[VALUATION_COLUMNS]


def build_historical_portfolio_value(
    holdings_df: pd.DataFrame,
    price_history: dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build a historical total portfolio value dataframe from price histories."""
    holdings = validate_portfolio_df(holdings_df)
    value_frames = []

    for holding in holdings:
        history_df = price_history.get(holding.coingecko_id)
        if history_df is None or history_df.empty:
            continue
        if not {"date", "price"}.issubset(history_df.columns):
            continue

        asset_value_df = history_df[["date", "price"]].copy()
        asset_value_df["date"] = pd.to_datetime(asset_value_df["date"])
        asset_value_df["price"] = pd.to_numeric(
            asset_value_df["price"],
            errors="coerce",
        )
        asset_value_df = (
            asset_value_df.dropna(subset=["date", "price"])
            .sort_values("date")
            .drop_duplicates(subset="date", keep="last")
        )
        if asset_value_df.empty:
            continue

        value_column = f"{holding.asset_symbol}_value_usd"
        asset_value_df[value_column] = asset_value_df["price"] * holding.quantity
        value_frames.append(asset_value_df[["date", value_column]])

    if not value_frames:
        return pd.DataFrame(columns=["date", "total_value_usd"])

    historical_df = value_frames[0]
    for value_frame in value_frames[1:]:
        historical_df = historical_df.merge(value_frame, on="date", how="outer")

    historical_df = historical_df.sort_values("date").reset_index(drop=True)
    asset_value_columns = [
        column for column in historical_df.columns if column.endswith("_value_usd")
    ]
    historical_df[asset_value_columns] = historical_df[asset_value_columns].ffill()
    historical_df["total_value_usd"] = historical_df[asset_value_columns].sum(
        axis=1,
        min_count=1,
    )
    historical_df = historical_df.dropna(subset=["total_value_usd"])

    return historical_df[["date", "total_value_usd", *asset_value_columns]]


def build_demo_price_history(
    prices: dict[str, float],
    days: int = 90,
) -> dict[str, pd.DataFrame]:
    """Build simple demo price histories from current prices for fallback display."""
    if not prices or days <= 0:
        return {}

    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days)
    trend = np.linspace(0.92, 1.0, num=days)
    return {
        coingecko_id: pd.DataFrame(
            {
                "date": dates,
                "price": float(price) * trend,
            }
        )
        for coingecko_id, price in prices.items()
    }


def calculate_daily_returns(historical_value_df: pd.DataFrame) -> pd.Series:
    """Calculate daily percentage returns from historical portfolio value."""
    if historical_value_df.empty or "total_value_usd" not in historical_value_df:
        return pd.Series(dtype=float, name="daily_return")

    returns = historical_value_df["total_value_usd"].pct_change()
    returns = returns.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    returns.name = "daily_return"
    return returns


def calculate_cumulative_return(historical_value_df: pd.DataFrame) -> pd.Series:
    """Calculate cumulative portfolio return from historical portfolio value."""
    if historical_value_df.empty or "total_value_usd" not in historical_value_df:
        return pd.Series(dtype=float, name="cumulative_return")

    values = historical_value_df["total_value_usd"]
    first_valid_value = values[values > 0].iloc[0] if (values > 0).any() else np.nan
    if pd.isna(first_valid_value):
        return pd.Series(0.0, index=historical_value_df.index, name="cumulative_return")

    cumulative_return = (values / first_valid_value) - 1
    cumulative_return = cumulative_return.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    cumulative_return.name = "cumulative_return"
    return cumulative_return
