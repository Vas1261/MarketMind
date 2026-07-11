"""
Base Market Data Provider
==========================

Abstract base class that every concrete provider inherits from.

Design: Template Method pattern.
  - fetch_ohlcv()         — public, final: validates request, delegates, validates result
  - _fetch_ohlcv_impl()   — abstract: provider-specific network/file I/O
  - list_available_symbols() — public, final: logs and delegates
  - _list_symbols_impl()  — abstract: provider-specific symbol discovery
  - fetch_asset_metadata()   — abstract: provider-specific metadata fetch

This guarantees that:
  1. Every provider gets identical request validation (as_of boundary, date ordering).
  2. Every provider call is logged consistently.
  3. The as_of boundary is validated on the *returned* OHLCVDataset, not just on the
     request — catching misbehaving provider implementations before data reaches
     the validation or feature pipeline.
  4. Concrete providers cannot accidentally skip these safety steps by overriding
     the public methods.

Import rule: this module imports from marketmind.core and
marketmind.data.providers.models only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from marketmind.core.exceptions import (
    DataIntegrityError,
    ProviderError,
)
from marketmind.data.providers.models import (
    AssetMetadata,
    OHLCVRequest,
    ProviderCapabilities,
)
from marketmind.logging import get_logger

if TYPE_CHECKING:
    from marketmind.core.domain.asset import Asset
    from marketmind.core.domain.market_data import OHLCVDataset


class BaseMarketDataProvider(ABC):
    """
    Abstract base class for all market data providers.

    Subclasses must implement:
      - capabilities property  → ProviderCapabilities descriptor
      - _fetch_ohlcv_impl()    → the actual data fetch
      - _list_symbols_impl()   → available symbol list
      - fetch_asset_metadata() → per-asset metadata

    Subclasses must NOT override:
      - fetch_ohlcv()            → validation + delegation + result audit
      - list_available_symbols() → logging + delegation
      - provider_metadata()      → derived from capabilities

    Thread safety: not guaranteed. Providers are not expected to be shared
    across threads. Create one instance per thread if concurrency is needed.
    """

    def __init__(self) -> None:
        self._log = get_logger(f"{__name__}.{type(self).__name__}")

    # ------------------------------------------------------------------
    # Abstract interface — subclasses implement these
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """
        Return this provider's capability descriptor.

        Called on every fetch_ohlcv() call to validate the request is
        serviceable. Must be cheap (no I/O) — return a pre-built instance.
        """

    @abstractmethod
    def _fetch_ohlcv_impl(self, request: OHLCVRequest) -> OHLCVDataset:
        """
        Fetch OHLCV data for the validated request.

        Called by fetch_ohlcv() after all request validation has passed.
        Implementations must:
          - Return bars in strictly ascending timestamp order.
          - Return only bars with timestamp <= request.as_of.
          - Raise ProviderError (or subclass) on network/auth failures.
          - Raise InvalidTickerError if the symbol does not exist.
          - Raise DataUnavailableError if data exists but is temporarily inaccessible.
          - Return an empty OHLCVDataset (no bars) if no data exists for
            the date range — do not raise for empty but valid ranges.
        """

    @abstractmethod
    def _list_symbols_impl(self, exchange: str) -> list[str]:
        """
        Return all ticker symbols available from this provider for `exchange`.

        Called by list_available_symbols() after logging.
        Returns a list of uppercase ticker strings.
        Empty list is valid (means no symbols known for this exchange).
        """

    @abstractmethod
    def fetch_asset_metadata(self, symbol: str, exchange: str) -> AssetMetadata:
        """
        Return descriptive metadata for a single asset.

        Raises InvalidTickerError if the symbol is not found.
        Raises ProviderError on network/auth failures.
        """

    # ------------------------------------------------------------------
    # Concrete public methods — shared implementation, not overridable
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self,
        asset: Asset,
        start: datetime,
        end: datetime,
        as_of: datetime,
    ) -> OHLCVDataset:
        """
        Fetch and return validated OHLCV data for one asset.

        This method is the single entry point for all OHLCV data access.
        It performs three layers of safety work around the provider implementation:

        Layer 1 — Request validation:
          Builds an OHLCVRequest which enforces timezone-awareness, date ordering,
          and that end <= as_of (requesting future data is not permitted).

        Layer 2 — Capability check:
          Verifies this provider supports the requested exchange and asset class
          before making any I/O call.

        Layer 3 — Result audit:
          Verifies the returned OHLCVDataset has symbol and exchange matching
          the request. The OHLCVDataset's own __post_init__ already validates
          bar ordering and the as_of boundary.

        Parameters
        ----------
        asset:
            The asset to fetch data for.
        start:
            Inclusive start date (UTC, timezone-aware).
        end:
            Inclusive end date (UTC, timezone-aware). Must be <= as_of.
        as_of:
            Point-in-time boundary. No bar may have timestamp > as_of.

        Returns
        -------
        OHLCVDataset
            Validated, time-ordered dataset. May have zero bars if no data
            exists for the date range — callers must handle this case.

        Raises
        ------
        ValueError
            If the request parameters are internally inconsistent.
        DataIntegrityError
            If the provider returns bars that violate the as_of boundary.
        InvalidTickerError
            If the symbol is not known to this provider.
        ProviderError
            On network, auth, or rate-limit failures.
        """
        request = OHLCVRequest(asset=asset, start=start, end=end, as_of=as_of)

        self._log.debug(
            "fetch_ohlcv.start",
            provider=self.capabilities.provider_id,
            symbol=asset.uid,
            start=start.isoformat(),
            end=end.isoformat(),
            as_of=as_of.isoformat(),
        )

        if not self.capabilities.can_serve(request):
            raise ProviderError(
                f"Provider '{self.capabilities.provider_id}' cannot serve "
                f"{asset.uid}: unsupported exchange or asset class. "
                f"Supported exchanges: {[e.value for e in self.capabilities.supported_exchanges]}, "
                f"supported asset classes: "
                f"{[a.value for a in self.capabilities.supported_asset_classes]}."
            )

        dataset = self._fetch_ohlcv_impl(request)

        # Audit the result — provider implementation may be buggy
        self._audit_result(dataset, request)

        self._log.debug(
            "fetch_ohlcv.complete",
            provider=self.capabilities.provider_id,
            symbol=asset.uid,
            bars=dataset.row_count,
        )

        return dataset

    def list_available_symbols(self, exchange: str) -> list[str]:
        """
        Return all ticker symbols available from this provider for `exchange`.

        Parameters
        ----------
        exchange:
            Exchange identifier string (e.g. "NYSE", "NASDAQ").

        Returns
        -------
        list[str]
            Uppercase ticker strings. Empty list if none available.
        """
        self._log.debug(
            "list_symbols.start",
            provider=self.capabilities.provider_id,
            exchange=exchange,
        )

        symbols = self._list_symbols_impl(exchange)
        symbols = [s.upper() for s in symbols]

        self._log.debug(
            "list_symbols.complete",
            provider=self.capabilities.provider_id,
            exchange=exchange,
            count=len(symbols),
        )

        return symbols

    def provider_metadata(self) -> dict[str, Any]:
        """
        Return a metadata dict describing this provider's capabilities.

        Satisfies the MarketDataProvider protocol contract.
        Derived from the structured ProviderCapabilities object.
        """
        return self.capabilities.to_metadata_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _audit_result(self, dataset: OHLCVDataset, request: OHLCVRequest) -> None:
        """
        Verify the dataset returned by the implementation matches the request.

        OHLCVDataset.__post_init__ already validates bar ordering and the
        as_of boundary. This method checks the logical consistency between
        the request and the returned dataset identity fields.

        Raises DataIntegrityError for any mismatch.
        """
        if dataset.symbol != request.asset.symbol:
            raise DataIntegrityError(
                f"Provider returned symbol '{dataset.symbol}' "
                f"but '{request.asset.symbol}' was requested."
            )

        if dataset.exchange != request.asset.exchange.value:
            raise DataIntegrityError(
                f"Provider returned exchange '{dataset.exchange}' "
                f"but '{request.asset.exchange.value}' was requested."
            )

        # Verify as_of on each bar (belt-and-suspenders — OHLCVDataset also checks)
        for bar in dataset.bars:
            if bar.timestamp > request.as_of:
                raise DataIntegrityError(
                    f"Provider '{self.capabilities.provider_id}' returned a bar "
                    f"with timestamp {bar.timestamp.isoformat()} that exceeds "
                    f"as_of boundary {request.as_of.isoformat()} for "
                    f"{request.asset.uid}. This is a provider implementation bug."
                )

    def _now_utc(self) -> datetime:
        """Return the current UTC time. Extracted for testability."""
        return datetime.now(UTC)
