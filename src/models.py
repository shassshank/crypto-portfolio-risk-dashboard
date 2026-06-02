"""Pydantic models for portfolio data validation."""

from pydantic import BaseModel, Field, field_validator


class Holding(BaseModel):
    """A single crypto asset holding in the portfolio."""

    asset_symbol: str
    coingecko_id: str
    quantity: float = Field(ge=0)
    avg_buy_price_usd: float = Field(ge=0)

    @field_validator("asset_symbol")
    @classmethod
    def normalize_asset_symbol(cls, value: str) -> str:
        """Normalize asset symbols to uppercase."""
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("asset_symbol is required")
        return normalized

    @field_validator("coingecko_id")
    @classmethod
    def normalize_coingecko_id(cls, value: str) -> str:
        """Normalize CoinGecko IDs to lowercase."""
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("coingecko_id is required")
        return normalized


class Portfolio(BaseModel):
    """A collection of validated crypto holdings."""

    holdings: list[Holding]
