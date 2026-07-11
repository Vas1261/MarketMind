"""
Provider Models
===============

Request, response, and capability value objects for the market data
provider abstraction layer.

Design decisions:
  - All models are frozen dataclasses, consistent with core domain objects.
  - No Pydantic here: these are simple structural types, not config objects.
  - All datetimes are timezone-aware UTC (enforced by __post_init__).
  - ProviderCapabilities is the machine-readable contract every provider
    exposes via capabilities property, replacing the dict-based
    provider_metadata() approach in the protocol with a typed equivalent.

Import rule: this module may import from marketmind.core only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from marketmind.core.domain.asset import Asset, AssetClass, Exchange


@dataclass(frozen=True)
class OHLCVRequest:
    """
    A validated, immutable request for OHLCV data from a provider.

    Encapsulates all parameters required to fetch a time series so they
    can be logged, cached, or replayed as a unit.

    Attributes
    ----------
    asset:
        The asset to fetch data for.
    start:
        Inclusive start of the requested date range (UTC).
    end:
        Inclusive end of the requested date range (UTC).
    as_of:
        Point-in-time boundary. The provider must not return any bar with
        timestamp > as_of. This enforces look-ahead-free data access.
    """

    asset: Asset
    start: datetime
    end: datetime
    as_of: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None:
            raise ValueError("OHLCVRequest.start must be timezone-aware (UTC).")
        if self.end.tzinfo is None:
            raise ValueError("OHLCVRequest.end must be timezone-aware (UTC).")
        if self.as_of.tzinfo is None:
            raise ValueError("OHLCVRequest.as_of must be timezone-aware (UTC).")
        if self.start > self.end:
            raise ValueError(
                f"start ({self.start.date()}) must not be after end ({self.end.date()})."
            )
        if self.end > self.as_of:
            raise ValueError(
                f"end ({self.end.date()}) must not be after as_of ({self.as_of.date()}). "
                "Requesting data beyond the as_of boundary would introduce look-ahead bias."
            )

    @property
    def symbol(self) -> str:
        """Convenience accessor for the asset symbol."""
        return self.asset.symbol

    @property
    def exchange(self) -> str:
        """Convenience accessor for the exchange value."""
        return self.asset.exchange.value

    def __str__(self) -> str:
        return (
            f"OHLCVRequest({self.asset.uid} "
            f"{self.start.date()} to {self.end.date()}, "
            f"as_of={self.as_of.date()})"
        )


@dataclass(frozen=True)
class ProviderCapabilities:
    """
    Machine-readable descriptor of what a data provider supports.

    Every provider exposes this via its `capabilities` property. Downstream
    components use it to determine whether a provider can serve a given request
    before attempting the call.

    Attributes
    ----------
    provider_id:
        Unique slug identifying the provider. Matches the key used in config.
        Examples: "yahoo", "polygon", "mock"
    display_name:
        Human-readable provider name for logs and UI.
    point_in_time_guaranteed:
        True only if the provider guarantees that data returned for a given
        as_of date reflects only information available at that date.
        Most free providers are False — historical data is restated retroactively.
    pit_limitation_description:
        If point_in_time_guaranteed is False, explains the limitation so it can
        appear in model cards and research logs.
    supported_exchanges:
        Exchanges this provider can serve. Empty frozenset means no restriction
        (provider claims all-exchange support).
    supported_asset_classes:
        Asset classes this provider can serve.
    data_delay_minutes:
        Typical delay between market close and data availability.
        0 for real-time providers, 1440 (24h) for end-of-day only.
    max_history_years:
        Maximum historical lookback in years. None means no documented limit.
    requires_authentication:
        True if an API key or token is required.
    supports_real_time:
        True if the provider can serve intraday / tick data.
    """

    provider_id: str
    display_name: str
    point_in_time_guaranteed: bool
    pit_limitation_description: str
    supported_exchanges: frozenset[Exchange]
    supported_asset_classes: frozenset[AssetClass]
    data_delay_minutes: int
    max_history_years: int | None
    requires_authentication: bool
    supports_real_time: bool

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("provider_id cannot be empty.")
        if not self.display_name:
            raise ValueError("display_name cannot be empty.")
        if self.data_delay_minutes < 0:
            raise ValueError("data_delay_minutes cannot be negative.")
        if self.max_history_years is not None and self.max_history_years <= 0:
            raise ValueError("max_history_years must be positive if set.")
        if not self.point_in_time_guaranteed and not self.pit_limitation_description:
            raise ValueError(
                "pit_limitation_description is required when point_in_time_guaranteed is False."
            )

    def supports_exchange(self, exchange: Exchange) -> bool:
        """
        True if this provider can serve data for the given exchange.

        An empty supported_exchanges set means the provider claims universal
        coverage — interpret with appropriate scepticism.
        """
        if not self.supported_exchanges:
            return True  # empty set = no restriction claimed
        return exchange in self.supported_exchanges

    def supports_asset_class(self, asset_class: AssetClass) -> bool:
        """True if this provider can serve the given asset class."""
        if not self.supported_asset_classes:
            return True
        return asset_class in self.supported_asset_classes

    def can_serve(self, request: OHLCVRequest) -> bool:
        """
        True if this provider is capable of serving the given request.

        This is a capability check only — it does not guarantee the data
        exists for the specific asset and date range.
        """
        return self.supports_exchange(request.asset.exchange) and self.supports_asset_class(
            request.asset.asset_class
        )

    def to_metadata_dict(self) -> dict[str, object]:
        """
        Return a dict representation matching the MarketDataProvider protocol.

        Used by provider_metadata() to satisfy the protocol contract while
        still exposing the structured ProviderCapabilities object internally.
        """
        return {
            "provider_id": self.provider_id,
            "name": self.display_name,
            "point_in_time_guaranteed": self.point_in_time_guaranteed,
            "pit_limitation_description": self.pit_limitation_description,
            "supported_exchanges": [e.value for e in self.supported_exchanges],
            "supported_asset_classes": [a.value for a in self.supported_asset_classes],
            "data_delay_minutes": self.data_delay_minutes,
            "max_history_years": self.max_history_years,
            "requires_authentication": self.requires_authentication,
            "supports_real_time": self.supports_real_time,
        }


@dataclass(frozen=True)
class AssetMetadata:
    """
    Descriptive metadata about a single asset returned by a provider.

    Distinct from the core Asset domain object: AssetMetadata is provider-
    sourced information that may be incomplete, delayed, or incorrect.
    It is never used as a primary key — only for enrichment and display.

    Attributes
    ----------
    symbol:
        Ticker symbol as recognised by the provider.
    exchange:
        Exchange on which the asset is primarily listed.
    name:
        Full legal or display name of the asset.
    asset_class:
        Classification of the asset.
    currency:
        ISO 4217 currency code for the asset's prices. e.g. "USD", "GBP".
    sector:
        GICS or equivalent sector classification. Empty string if unknown.
    country:
        ISO 3166-1 alpha-2 country code of primary listing. Empty if unknown.
    is_active:
        True if the asset is currently trading. False if delisted or halted.
    retrieved_at:
        UTC timestamp when this metadata was fetched from the provider.
    """

    symbol: str
    exchange: Exchange
    name: str
    asset_class: AssetClass
    currency: str
    sector: str
    country: str
    is_active: bool
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("AssetMetadata.symbol cannot be empty.")
        if not self.currency:
            raise ValueError("AssetMetadata.currency cannot be empty.")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("AssetMetadata.retrieved_at must be timezone-aware (UTC).")

    def to_asset(self) -> Asset:
        """
        Convert this metadata into a core Asset domain object.

        The resulting Asset uses the information available from the provider.
        Fields not available from the provider (market_cap_tier) default to UNKNOWN.
        """
        return Asset(
            symbol=self.symbol,
            exchange=self.exchange,
            asset_class=self.asset_class,
            name=self.name,
            sector=self.sector,
            country=self.country,
        )

    def __str__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"AssetMetadata({self.symbol}@{self.exchange.value}, {self.currency}, {status})"
