"""
Asset Domain Objects
====================

Value objects representing financial assets and their classification.

All domain objects are immutable (frozen dataclasses or Pydantic models).
Immutability is enforced by the dataclass frozen=True parameter — any code
that attempts to mutate an asset will raise a FrozenInstanceError at runtime,
not silently produce wrong results.

These objects carry no behaviour beyond validation and representation.
Business logic lives in service and pipeline classes, not here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    """
    Supported asset classes.

    Only STOCK and ETF are in scope for Version 1.
    The enum exists now so that every domain object that carries an asset class
    reference is already typed correctly — adding CRYPTO later requires only
    a new enum member, not a type change across the codebase.
    """

    STOCK = "STOCK"
    ETF = "ETF"
    # Future versions:
    # CRYPTO = "CRYPTO"
    # FOREX = "FOREX"
    # COMMODITY = "COMMODITY"


class Exchange(StrEnum):
    """
    Supported exchanges for Version 1.

    The exchange determines which trading calendar is used for validation
    and which timezone is applied to market data timestamps.
    """

    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    LSE = "LSE"  # London Stock Exchange
    XETRA = "XETRA"  # Deutsche Börse
    TSX = "TSX"  # Toronto Stock Exchange
    ASX = "ASX"  # Australian Securities Exchange
    UNKNOWN = "UNKNOWN"  # For assets whose exchange is not yet identified


class MarketCapTier(StrEnum):
    """
    Market capitalisation tier.

    Used in universe construction to ensure sector and size diversity.
    Thresholds are approximate and for classification purposes only.
    """

    SMALL = "SMALL"  # < $2B
    MID = "MID"  # $2B - $10B
    LARGE = "LARGE"  # > $10B
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Asset:
    """
    Immutable representation of a single financial asset.

    An Asset is the fundamental unit of the research universe.
    Every pipeline component — data ingestion, feature engineering,
    model training — operates on one or more Assets.

    Attributes
    ----------
    symbol:
        The ticker symbol as used by the primary data provider.
        Examples: "AAPL", "SPY", "TSLA"
    exchange:
        The primary listing exchange.
    asset_class:
        Whether this is a stock, ETF, etc.
    name:
        Human-readable name. Optional; used for display only.
    sector:
        GICS sector. Optional; used for universe diversity checks.
    country:
        ISO 3166-1 alpha-2 country code of the primary listing.
    market_cap_tier:
        Size tier for universe construction.

    Notes
    -----
    Symbol alone is not a unique identifier — the same ticker can exist on
    multiple exchanges. The canonical identifier is (symbol, exchange).
    """

    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    name: str = ""
    sector: str = ""
    country: str = ""
    market_cap_tier: MarketCapTier = MarketCapTier.UNKNOWN

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("Asset symbol cannot be empty.")
        if not self.symbol.isupper():
            # Normalise silently rather than raising — tickers are always upper
            object.__setattr__(self, "symbol", self.symbol.upper())

    @property
    def uid(self) -> str:
        """
        Canonical unique identifier for this asset.

        Format: "{EXCHANGE}:{SYMBOL}"
        Example: "NYSE:AAPL"

        Use this as dict keys and database primary keys — never bare symbol.
        """
        return f"{self.exchange.value}:{self.symbol}"

    def __str__(self) -> str:
        return self.uid

    def __repr__(self) -> str:
        return (
            f"Asset(symbol={self.symbol!r}, exchange={self.exchange.value!r}, "
            f"asset_class={self.asset_class.value!r})"
        )


@dataclass(frozen=True)
class Universe:
    """
    A fixed, immutable research universe.

    The universe is the set of assets used for all experiments.

    Critical invariant: once a universe is sealed (locked_at is set),
    its asset list must never change. Changing the universe after observing
    experimental results is a form of selection bias that invalidates all
    conclusions produced against it.

    Attributes
    ----------
    universe_id:
        Unique identifier. Convention: "UNIVERSE-V{N}" e.g. "UNIVERSE-V1"
    assets:
        Frozenset of assets. Immutable by construction.
    description:
        Human-readable description of how this universe was constructed.
    is_sealed:
        True once the universe is locked for use in experiments.
        A sealed universe cannot be modified.
    """

    universe_id: str
    assets: frozenset[Asset]
    description: str = ""
    is_sealed: bool = False

    def __post_init__(self) -> None:
        if not self.universe_id:
            raise ValueError("Universe ID cannot be empty.")
        if len(self.assets) == 0:
            raise ValueError("Universe must contain at least one asset.")

    @property
    def size(self) -> int:
        """Number of assets in the universe."""
        return len(self.assets)

    def get_by_symbol(self, symbol: str) -> Asset | None:
        """Look up an asset by symbol. Returns None if not found."""
        symbol = symbol.upper()
        return next((a for a in self.assets if a.symbol == symbol), None)

    def get_by_uid(self, uid: str) -> Asset | None:
        """Look up an asset by canonical UID (EXCHANGE:SYMBOL)."""
        return next((a for a in self.assets if a.uid == uid), None)

    def __str__(self) -> str:
        sealed_tag = " [SEALED]" if self.is_sealed else " [DRAFT]"
        return f"Universe({self.universe_id}{sealed_tag}, {self.size} assets)"

    def __repr__(self) -> str:
        return (
            f"Universe(universe_id={self.universe_id!r}, "
            f"size={self.size}, is_sealed={self.is_sealed})"
        )
