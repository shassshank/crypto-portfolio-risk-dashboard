"""Plotly chart builders for dashboard views."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


CHART_TEMPLATE = "plotly_white"
PRIMARY_COLOR = "#2563eb"
GAIN_COLOR = "#16a34a"
LOSS_COLOR = "#dc2626"


def portfolio_value_line_chart(df: pd.DataFrame) -> go.Figure:
    """Create a line chart for historical portfolio value."""
    fig = px.line(
        df,
        x="date",
        y="total_value_usd",
        labels={
            "date": "Date",
            "total_value_usd": "Portfolio Value (USD)",
        },
        template=CHART_TEMPLATE,
    )
    fig.update_traces(line={"color": PRIMARY_COLOR, "width": 2.5})
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        yaxis_tickprefix="$",
        hovermode="x unified",
        showlegend=False,
    )
    return fig


def allocation_pie_chart(valuation_df: pd.DataFrame) -> go.Figure:
    """Create an allocation pie chart from valuation data."""
    fig = px.pie(
        valuation_df,
        names="asset_symbol",
        values="current_value_usd",
        hole=0.45,
        template=CHART_TEMPLATE,
    )
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        legend_title_text="Asset",
    )
    return fig


def pnl_bar_chart(valuation_df: pd.DataFrame) -> go.Figure:
    """Create a bar chart of unrealized PnL by asset."""
    fig = px.bar(
        valuation_df,
        x="asset_symbol",
        y="unrealized_pnl_usd",
        labels={
            "asset_symbol": "Asset",
            "unrealized_pnl_usd": "Unrealized PnL (USD)",
        },
        template=CHART_TEMPLATE,
    )
    colors = [
        GAIN_COLOR if value >= 0 else LOSS_COLOR
        for value in valuation_df["unrealized_pnl_usd"]
    ]
    fig.update_traces(marker_color=colors)
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        yaxis_tickprefix="$",
        showlegend=False,
    )
    return fig


def returns_histogram_chart(daily_returns: pd.Series) -> go.Figure:
    """Create a histogram of daily portfolio returns."""
    returns_df = pd.DataFrame({"daily_return": daily_returns})
    fig = px.histogram(
        returns_df,
        x="daily_return",
        nbins=30,
        labels={"daily_return": "Daily Return"},
        template=CHART_TEMPLATE,
    )
    fig.update_traces(marker_color=PRIMARY_COLOR)
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        xaxis_tickformat=".2%",
        yaxis_title="Days",
        showlegend=False,
    )
    return fig


def drawdown_chart(
    drawdown_series: pd.Series,
    dates: pd.Series | None = None,
) -> go.Figure:
    """Create a line chart of portfolio drawdowns."""
    drawdown_df = pd.DataFrame({"drawdown": drawdown_series})
    if dates is not None:
        drawdown_df["date"] = dates
        x_axis = "date"
    else:
        drawdown_df["period"] = drawdown_df.index
        x_axis = "period"

    fig = px.line(
        drawdown_df,
        x=x_axis,
        y="drawdown",
        labels={
            x_axis: "Date" if x_axis == "date" else "Period",
            "drawdown": "Drawdown",
        },
        template=CHART_TEMPLATE,
    )
    fig.update_traces(line={"color": LOSS_COLOR, "width": 2.5})
    fig.update_layout(
        margin={"l": 0, "r": 0, "t": 12, "b": 0},
        yaxis_tickformat=".2%",
        hovermode="x unified",
        showlegend=False,
    )
    return fig
