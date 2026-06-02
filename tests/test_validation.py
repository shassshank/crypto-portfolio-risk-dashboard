"""Tests for portfolio data validation models."""

import pytest
from pydantic import ValidationError

from src.models import Holding


def test_valid_holding_passes() -> None:
    """A holding with valid values should pass validation."""
    holding = Holding(
        asset_symbol="BTC",
        coingecko_id="bitcoin",
        quantity=0.25,
        avg_buy_price_usd=42000,
    )

    assert holding.asset_symbol == "BTC"
    assert holding.coingecko_id == "bitcoin"
    assert holding.quantity == 0.25
    assert holding.avg_buy_price_usd == 42000


def test_negative_quantity_fails() -> None:
    """A negative quantity should fail validation."""
    with pytest.raises(ValidationError):
        Holding(
            asset_symbol="BTC",
            coingecko_id="bitcoin",
            quantity=-0.01,
            avg_buy_price_usd=42000,
        )


def test_negative_average_buy_price_fails() -> None:
    """A negative average buy price should fail validation."""
    with pytest.raises(ValidationError):
        Holding(
            asset_symbol="BTC",
            coingecko_id="bitcoin",
            quantity=0.25,
            avg_buy_price_usd=-1,
        )


def test_asset_symbol_is_normalized_to_uppercase() -> None:
    """Asset symbols should be stripped and converted to uppercase."""
    holding = Holding(
        asset_symbol=" eth ",
        coingecko_id="ethereum",
        quantity=2.5,
        avg_buy_price_usd=2400,
    )

    assert holding.asset_symbol == "ETH"


def test_coingecko_id_is_normalized_to_lowercase() -> None:
    """CoinGecko IDs should be stripped and converted to lowercase."""
    holding = Holding(
        asset_symbol="SOL",
        coingecko_id=" Solana ",
        quantity=40,
        avg_buy_price_usd=95,
    )

    assert holding.coingecko_id == "solana"
