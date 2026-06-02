"""Small formatting helpers for dashboard display values."""

from datetime import datetime


def format_currency(value: float, currency_symbol: str = "$") -> str:
    """Format a number as currency with two decimal places."""
    return f"{currency_symbol}{value:,.2f}"


def format_percentage(value: float) -> str:
    """Format a decimal return as a percentage with two decimal places."""
    return f"{value:.2%}"


def format_source_label(source: str) -> str:
    """Format a data source label for UI display."""
    labels = {
        "api": "API",
        "cache": "Cache",
        "fallback": "Fallback",
        "partial api/cache": "Partial API/Cache",
        "unknown": "Unknown",
    }
    return labels.get(source.lower(), source.title())


def format_timestamp(value: datetime) -> str:
    """Format a datetime for dashboard display."""
    return value.strftime("%Y-%m-%d %H:%M:%S")
