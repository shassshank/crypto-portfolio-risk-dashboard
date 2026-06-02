"""Streamlit UI for the Crypto Portfolio Risk Dashboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from src.charts import (
    allocation_pie_chart,
    drawdown_chart,
    pnl_bar_chart,
    portfolio_value_line_chart,
    returns_histogram_chart,
)
from src.coingecko_client import (
    CoinGeckoAPIError,
    get_current_prices,
    get_last_data_source,
    get_market_chart,
)
from src.config import settings
from src.portfolio import (
    build_demo_price_history,
    build_historical_portfolio_value,
    calculate_cumulative_return,
    calculate_portfolio_valuation,
    load_portfolio_csv,
    validate_portfolio_df,
)
from src.risk import (
    calculate_annualized_volatility,
    calculate_concentration_metrics,
    calculate_daily_returns,
    calculate_drawdown_series,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_max_drawdown,
    calculate_risk_score,
    calculate_stablecoin_allocation,
)
from src.stress import (
    PRESET_SCENARIOS,
    apply_stress_scenario,
    get_preset_scenario_shocks,
)
from src.utils import (
    format_currency,
    format_percentage,
    format_source_label,
    format_timestamp,
)

SAMPLE_PORTFOLIO_PATH = Path("data/sample_portfolio.csv")
LOOKBACK_OPTIONS = [30, 60, 90, 180]
CONFIDENCE_LEVELS = [0.95, 0.99]
FAKE_PRICES = {
    "bitcoin": 50000,
    "ethereum": 3000,
    "solana": 100,
    "chainlink": 15,
    "tether": 1,
}


def main() -> None:
    """Render the Streamlit dashboard."""
    st.set_page_config(page_title="Crypto Portfolio Risk Dashboard", layout="wide")
    st.title("Crypto Portfolio Risk Dashboard")
    st.caption(
        "Portfolio valuation, performance, risk, and stress testing using public "
        "CoinGecko market data with local caching and demo fallbacks."
    )

    controls = render_sidebar()
    portfolio_df = load_portfolio_from_controls(controls)
    data_quality: dict[str, Any] = {
        "portfolio_source": controls["portfolio_source"],
        "price_source": "unknown",
        "history_source": "unknown",
        "last_refresh": datetime.now(),
        "warnings": [],
        "api_messages": [],
        "missing_history_assets": [],
        "lookback_days": controls["lookback_days"],
        "confidence_level": controls["confidence_level"],
    }

    try:
        validate_portfolio_df(portfolio_df)
    except (ValidationError, ValueError) as exc:
        st.error("This portfolio could not be validated. Check symbols, CoinGecko IDs, quantities, and average buy prices.")
        st.caption(_friendly_error(exc))
        st.stop()

    coingecko_ids = portfolio_df["coingecko_id"].tolist()
    prices = fetch_current_prices(
        coingecko_ids,
        data_quality,
        force_refresh=controls["refresh_clicked"],
    )

    try:
        valuation_df = calculate_portfolio_valuation(portfolio_df, prices)
    except (ValidationError, ValueError) as exc:
        st.error("Valuation could not be calculated for this portfolio.")
        st.caption(_friendly_error(exc))
        st.stop()

    historical_value_df = build_historical_values(
        portfolio_df,
        coingecko_ids,
        prices,
        controls["lookback_days"],
        data_quality,
        force_refresh=controls["refresh_clicked"],
    )
    dashboard_metrics = calculate_dashboard_metrics(
        valuation_df,
        historical_value_df,
        controls["confidence_level"],
    )

    render_status_banner(data_quality)
    render_sidebar_status(data_quality)

    tabs = st.tabs(
        [
            "Overview",
            "Holdings",
            "Performance",
            "Risk",
            "Stress Testing",
            "Data Quality",
        ]
    )
    with tabs[0]:
        render_overview_tab(valuation_df, historical_value_df, dashboard_metrics)
    with tabs[1]:
        render_holdings_tab(valuation_df)
    with tabs[2]:
        render_performance_tab(historical_value_df, dashboard_metrics, data_quality)
    with tabs[3]:
        render_risk_tab(valuation_df, historical_value_df, dashboard_metrics)
    with tabs[4]:
        render_stress_tab(valuation_df)
    with tabs[5]:
        render_data_quality_tab(data_quality)


def render_sidebar() -> dict[str, Any]:
    """Render sidebar controls and return selected values."""
    st.sidebar.header("Portfolio")
    use_demo_portfolio = st.sidebar.checkbox("Use demo portfolio", value=True)
    uploaded_file = st.sidebar.file_uploader(
        "Upload portfolio CSV",
        type=["csv"],
        disabled=use_demo_portfolio,
    )

    st.sidebar.header("Data Settings")
    lookback_days = st.sidebar.selectbox("Lookback days", LOOKBACK_OPTIONS, index=2)
    confidence_level = st.sidebar.selectbox(
        "Confidence level",
        CONFIDENCE_LEVELS,
        format_func=lambda value: f"{value:.0%}",
    )
    refresh_clicked = st.sidebar.button("Refresh data", width="stretch")
    if refresh_clicked:
        st.sidebar.success("Data refresh requested.")

    st.sidebar.header("API / Cache Status")
    st.sidebar.caption(
        f"CoinGecko public API | Cache TTL: {settings.cache_ttl_seconds}s"
    )
    st.sidebar.caption("Status updates after data loads.")

    return {
        "use_demo_portfolio": use_demo_portfolio,
        "uploaded_file": uploaded_file,
        "portfolio_source": "Demo portfolio" if use_demo_portfolio else "Uploaded CSV",
        "lookback_days": lookback_days,
        "confidence_level": confidence_level,
        "refresh_clicked": refresh_clicked,
    }


def load_portfolio_from_controls(controls: dict[str, Any]) -> pd.DataFrame:
    """Load either the demo portfolio or the uploaded portfolio."""
    uploaded_file = controls["uploaded_file"]
    if not controls["use_demo_portfolio"] and uploaded_file is not None:
        try:
            return pd.read_csv(uploaded_file)
        except Exception as exc:
            st.error("The uploaded CSV could not be read.")
            st.caption(_friendly_error(exc))
            st.stop()

    return load_portfolio_csv(str(SAMPLE_PORTFOLIO_PATH))


def fetch_current_prices(
    coingecko_ids: list[str],
    data_quality: dict[str, Any],
    force_refresh: bool = False,
) -> dict[str, float]:
    """Fetch current prices, falling back to demo prices on failure."""
    try:
        prices = get_current_prices(
            coingecko_ids,
            settings.default_currency,
            force_refresh=force_refresh,
        )
        data_quality["price_source"] = get_last_data_source()
        return prices
    except CoinGeckoAPIError as exc:
        data_quality["price_source"] = "fallback"
        data_quality["warnings"].append("Current prices are using demo fallback data.")
        data_quality["api_messages"].append(_friendly_error(exc))
        return FAKE_PRICES


def build_historical_values(
    portfolio_df: pd.DataFrame,
    coingecko_ids: list[str],
    prices: dict[str, float],
    lookback_days: int,
    data_quality: dict[str, Any],
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Fetch market charts and build the historical portfolio value series."""
    price_history = {}
    history_sources = set()

    for coingecko_id in coingecko_ids:
        try:
            history_df = get_market_chart(
                coingecko_id,
                settings.default_currency,
                lookback_days,
                force_refresh=force_refresh,
            )
        except CoinGeckoAPIError as exc:
            data_quality["missing_history_assets"].append(coingecko_id)
            data_quality["api_messages"].append(
                f"{coingecko_id}: {_friendly_error(exc)}"
            )
            continue

        if history_df.empty:
            data_quality["missing_history_assets"].append(coingecko_id)
            continue

        price_history[coingecko_id] = history_df
        history_sources.add(get_last_data_source())

    if not price_history:
        data_quality["history_source"] = "fallback"
        data_quality["warnings"].append("Historical charts are using demo fallback data.")
        price_history = build_demo_price_history(prices, lookback_days)
    elif data_quality["missing_history_assets"]:
        data_quality["history_source"] = "partial api/cache"
        data_quality["warnings"].append("Some assets are missing historical data.")
    elif "api" in history_sources:
        data_quality["history_source"] = "api"
    else:
        data_quality["history_source"] = "cache"

    return build_historical_portfolio_value(portfolio_df, price_history)


def calculate_dashboard_metrics(
    valuation_df: pd.DataFrame,
    historical_value_df: pd.DataFrame,
    confidence_level: float,
) -> dict[str, Any]:
    """Calculate display metrics for all dashboard tabs."""
    total_portfolio_value = float(valuation_df["current_value_usd"].sum())
    total_cost_basis = float(valuation_df["cost_basis_usd"].sum())
    total_pnl = float(valuation_df["unrealized_pnl_usd"].sum())
    total_pnl_pct = total_pnl / total_cost_basis if total_cost_basis > 0 else 0.0

    daily_returns = calculate_daily_returns(historical_value_df["total_value_usd"])
    drawdown_series = calculate_drawdown_series(historical_value_df["total_value_usd"])
    cumulative_return = calculate_cumulative_return(historical_value_df)
    latest_cumulative_return = (
        float(cumulative_return.iloc[-1]) if not cumulative_return.empty else 0.0
    )
    annualized_volatility = calculate_annualized_volatility(daily_returns)
    max_drawdown = calculate_max_drawdown(historical_value_df["total_value_usd"])
    selected_var = calculate_historical_var(
        daily_returns,
        confidence_level=confidence_level,
    )
    selected_expected_shortfall = calculate_expected_shortfall(
        daily_returns,
        confidence_level=confidence_level,
    )
    concentration_metrics = calculate_concentration_metrics(valuation_df)
    stablecoin_allocation = calculate_stablecoin_allocation(valuation_df)
    risk_score = calculate_risk_score(
        volatility=annualized_volatility,
        max_drawdown=max_drawdown,
        largest_asset_allocation=concentration_metrics["largest_asset_allocation"],
        stablecoin_allocation=stablecoin_allocation,
        number_of_assets=len(valuation_df),
    )

    return {
        "total_portfolio_value": total_portfolio_value,
        "total_cost_basis": total_cost_basis,
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "daily_returns": daily_returns,
        "drawdown_series": drawdown_series,
        "latest_cumulative_return": latest_cumulative_return,
        "annualized_volatility": annualized_volatility,
        "max_drawdown": max_drawdown,
        "confidence_label": f"{confidence_level:.0%}",
        "selected_var": selected_var,
        "selected_expected_shortfall": selected_expected_shortfall,
        "concentration_metrics": concentration_metrics,
        "stablecoin_allocation": stablecoin_allocation,
        "risk_score": risk_score,
    }


def render_status_banner(data_quality: dict[str, Any]) -> None:
    """Render the top-level API/cache status indicator."""
    status_text = (
        f"Current prices: {format_source_label(data_quality['price_source'])} | "
        f"Historical prices: {format_source_label(data_quality['history_source'])} | "
        f"Last refresh: {format_timestamp(data_quality['last_refresh'])}"
    )
    if data_quality["price_source"] == "fallback" or data_quality["history_source"] == "fallback":
        st.warning(status_text)
    elif data_quality["warnings"]:
        st.info(status_text)
    else:
        st.success(status_text)


def render_sidebar_status(data_quality: dict[str, Any]) -> None:
    """Render sidebar data-source status after the data load finishes."""
    st.sidebar.divider()
    st.sidebar.header("Loaded Status")
    st.sidebar.metric("Current Prices", format_source_label(data_quality["price_source"]))
    st.sidebar.metric(
        "Historical Prices",
        format_source_label(data_quality["history_source"]),
    )
    st.sidebar.caption(f"Last refresh: {format_timestamp(data_quality['last_refresh'])}")


def render_overview_tab(
    valuation_df: pd.DataFrame,
    historical_value_df: pd.DataFrame,
    metrics: dict[str, Any],
) -> None:
    """Render the Overview tab."""
    st.subheader("Portfolio Snapshot")
    metric_cols = st.columns(4)
    metric_cols[0].metric(
        "Total Portfolio Value",
        format_currency(metrics["total_portfolio_value"]),
    )
    metric_cols[1].metric("Total Cost Basis", format_currency(metrics["total_cost_basis"]))
    metric_cols[2].metric(
        "Total PnL",
        format_currency(metrics["total_pnl"]),
        format_percentage(metrics["total_pnl_pct"]),
    )
    metric_cols[3].metric(
        "Cumulative Return",
        format_percentage(metrics["latest_cumulative_return"]),
    )

    chart_cols = st.columns([1, 2])
    with chart_cols[0]:
        st.markdown("#### Allocation")
        st.plotly_chart(
            allocation_pie_chart(valuation_df),
            width="stretch",
            key="overview_allocation_chart",
        )
    with chart_cols[1]:
        st.markdown("#### Portfolio Value")
        if historical_value_df.empty:
            st.info("Historical value will appear once price history is available.")
        else:
            st.plotly_chart(
                portfolio_value_line_chart(historical_value_df),
                width="stretch",
                key="overview_portfolio_value_chart",
            )


def render_holdings_tab(valuation_df: pd.DataFrame) -> None:
    """Render the Holdings tab."""
    st.subheader("Holdings")
    st.caption("Current value, cost basis, allocation, and unrealized PnL by asset.")
    display_df = valuation_df.copy()
    display_df["unrealized_pnl_pct"] = display_df["unrealized_pnl_pct"] * 100
    display_df["allocation_pct"] = display_df["allocation_pct"] * 100
    st.dataframe(
        display_df,
        width="stretch",
        hide_index=True,
        column_config={
            "asset_symbol": "Asset",
            "coingecko_id": "CoinGecko ID",
            "current_price_usd": st.column_config.NumberColumn(
                "Current Price",
                format="$%.2f",
            ),
            "cost_basis_usd": st.column_config.NumberColumn(
                "Cost Basis",
                format="$%.2f",
            ),
            "current_value_usd": st.column_config.NumberColumn(
                "Current Value",
                format="$%.2f",
            ),
            "unrealized_pnl_usd": st.column_config.NumberColumn(
                "Unrealized PnL",
                format="$%.2f",
            ),
            "unrealized_pnl_pct": st.column_config.NumberColumn(
                "PnL %",
                format="%.2f%%",
            ),
            "allocation_pct": st.column_config.NumberColumn(
                "Allocation",
                format="%.2f%%",
            ),
        },
    )

    chart_cols = st.columns([2, 1])
    with chart_cols[0]:
        st.markdown("#### Unrealized PnL")
        st.plotly_chart(
            pnl_bar_chart(valuation_df),
            width="stretch",
            key="holdings_pnl_chart",
        )
    with chart_cols[1]:
        st.markdown("#### Allocation Table")
        allocation_df = valuation_df[
            ["asset_symbol", "current_value_usd", "allocation_pct"]
        ].sort_values("allocation_pct", ascending=False)
        allocation_df = allocation_df.copy()
        allocation_df["allocation_pct"] = allocation_df["allocation_pct"] * 100
        st.dataframe(
            allocation_df,
            width="stretch",
            hide_index=True,
            column_config={
                "asset_symbol": "Asset",
                "current_value_usd": st.column_config.NumberColumn(
                    "Value",
                    format="$%.2f",
                ),
                "allocation_pct": st.column_config.NumberColumn(
                    "Allocation",
                    format="%.2f%%",
                ),
            },
        )


def render_performance_tab(
    historical_value_df: pd.DataFrame,
    metrics: dict[str, Any],
    data_quality: dict[str, Any],
) -> None:
    """Render the Performance tab."""
    st.subheader("Performance")
    st.caption(f"Historical lookback: {data_quality['lookback_days']} days.")
    if historical_value_df.empty:
        st.info("No historical price history is available yet.")
        return

    st.plotly_chart(
        portfolio_value_line_chart(historical_value_df),
        width="stretch",
        key="performance_value_chart",
    )
    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.markdown("#### Daily Returns")
        st.plotly_chart(
            returns_histogram_chart(metrics["daily_returns"]),
            width="stretch",
            key="performance_returns_histogram",
        )
    with chart_cols[1]:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            drawdown_chart(metrics["drawdown_series"], historical_value_df["date"]),
            width="stretch",
            key="performance_drawdown_chart",
        )


def render_risk_tab(
    valuation_df: pd.DataFrame,
    historical_value_df: pd.DataFrame,
    metrics: dict[str, Any],
) -> None:
    """Render the Risk tab."""
    st.subheader("Risk Metrics")
    if historical_value_df.empty:
        st.info("Risk metrics need historical portfolio values. Try a longer lookback or refresh data.")

    risk_cols = st.columns(4)
    risk_cols[0].metric(
        "Annualized Volatility",
        format_percentage(metrics["annualized_volatility"]),
    )
    risk_cols[1].metric("Max Drawdown", format_percentage(metrics["max_drawdown"]))
    risk_cols[2].metric(
        f"VaR {metrics.get('confidence_label', '')}".strip(),
        format_percentage(metrics["selected_var"]),
    )
    risk_cols[3].metric(
        "Expected Shortfall",
        format_percentage(metrics["selected_expected_shortfall"]),
    )

    concentration = metrics["concentration_metrics"]
    concentration_cols = st.columns(4)
    concentration_cols[0].metric(
        "Largest Asset",
        format_percentage(concentration["largest_asset_allocation"]),
    )
    concentration_cols[1].metric(
        "Top 3 Allocation",
        format_percentage(concentration["top_3_allocation"]),
    )
    concentration_cols[2].metric("HHI Score", f"{concentration['hhi_score']:.3f}")
    concentration_cols[3].metric(
        "Stablecoin Allocation",
        format_percentage(metrics["stablecoin_allocation"]),
    )

    st.markdown("#### Risk Score")
    score_cols = st.columns([1, 3])
    score_cols[0].metric("Score", f"{metrics['risk_score']['score']:.0f}/100")
    score_cols[1].caption(
        "Higher scores indicate higher estimated portfolio risk. Components are "
        "simple, explainable weights rather than a predictive model."
    )
    st.dataframe(
        pd.DataFrame(
            {
                "Component": list(metrics["risk_score"]["components"].keys()),
                "Points": list(metrics["risk_score"]["components"].values()),
            }
        ),
        width="stretch",
        hide_index=True,
    )
    for explanation in metrics["risk_score"]["explanation"]:
        st.caption(explanation)

    st.caption(f"Assets included in concentration metrics: {len(valuation_df)}")


def render_stress_tab(valuation_df: pd.DataFrame) -> None:
    """Render the Stress Testing tab."""
    st.subheader("Stress Testing")
    st.caption("Apply simple price shocks to estimate immediate portfolio impact.")
    scenario_name = st.selectbox("Scenario", list(PRESET_SCENARIOS.keys()))
    shocks = get_preset_scenario_shocks(valuation_df, scenario_name)

    if scenario_name == "Custom shock by asset":
        custom_cols = st.columns([2, 1])
        selected_asset = custom_cols[0].selectbox(
            "Asset",
            valuation_df["asset_symbol"].tolist(),
        )
        custom_shock_pct = custom_cols[1].number_input(
            "Shock %",
            min_value=-100.0,
            max_value=100.0,
            value=-10.0,
            step=1.0,
        )
        shocks = {selected_asset: custom_shock_pct / 100}

    stress_result = apply_stress_scenario(valuation_df, shocks)
    stress_summary = stress_result["summary"]
    stress_impact_df = stress_result["asset_impacts"].copy()
    stress_impact_df["pct_impact"] = stress_impact_df["pct_impact"] * 100

    stress_cols = st.columns(4)
    stress_cols[0].metric(
        "Current Value",
        format_currency(stress_summary["current_portfolio_value"]),
    )
    stress_cols[1].metric(
        "Shocked Value",
        format_currency(stress_summary["shocked_portfolio_value"]),
    )
    stress_cols[2].metric(
        "Total Dollar Loss",
        format_currency(stress_summary["total_dollar_loss"]),
    )
    stress_cols[3].metric(
        "Total % Loss",
        format_percentage(stress_summary["total_pct_loss"]),
    )

    st.dataframe(
        stress_impact_df,
        width="stretch",
        hide_index=True,
        column_config={
            "asset_symbol": "Asset",
            "current_value_usd": st.column_config.NumberColumn(
                "Current Value",
                format="$%.2f",
            ),
            "shocked_value_usd": st.column_config.NumberColumn(
                "Shocked Value",
                format="$%.2f",
            ),
            "dollar_impact": st.column_config.NumberColumn(
                "Dollar Impact",
                format="$%.2f",
            ),
            "pct_impact": st.column_config.NumberColumn("Shock", format="%.2f%%"),
        },
    )


def render_data_quality_tab(data_quality: dict[str, Any]) -> None:
    """Render data source and warning details."""
    st.subheader("Data Quality")
    source_df = pd.DataFrame(
        [
            {"Item": "Portfolio", "Status": data_quality["portfolio_source"]},
            {"Item": "Current Prices", "Status": format_source_label(data_quality["price_source"])},
            {"Item": "Historical Prices", "Status": format_source_label(data_quality["history_source"])},
            {"Item": "Lookback", "Status": f"{data_quality['lookback_days']} days"},
            {"Item": "Last Refresh", "Status": format_timestamp(data_quality["last_refresh"])},
        ]
    )
    st.dataframe(source_df, width="stretch", hide_index=True)

    if data_quality["warnings"]:
        st.markdown("#### Warnings")
        for warning in data_quality["warnings"]:
            st.warning(warning)
    else:
        st.success("No data quality warnings.")

    if data_quality["missing_history_assets"]:
        st.markdown("#### Missing Historical Data")
        st.write(", ".join(data_quality["missing_history_assets"]))

    if data_quality["api_messages"]:
        st.markdown("#### API Messages")
        for message in data_quality["api_messages"]:
            st.caption(message)
    else:
        st.caption("No API failure messages for this refresh.")


def _friendly_error(exc: Exception) -> str:
    """Return a concise non-traceback error message for the UI."""
    message = str(exc).strip()
    return message if message else exc.__class__.__name__


if __name__ == "__main__":
    main()
