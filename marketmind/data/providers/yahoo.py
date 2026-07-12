"""
Yahoo Finance Market Data Provider
====================================

Wraps the ``yfinance`` library and converts its output into MarketMind
domain objects. No yfinance types, DataFrames, or raw exceptions cross
the boundary of this module.

Design decisions
----------------
- ``Ticker.history()`` is used (not ``yf.download()``) because it gives
  per-ticker control, cleaner error handling, and respects ``auto_adjust``
  transparently.
- ``auto_adjust=True`` is always set so we receive split-and-dividend-
  adjusted prices without manually processing corporate-action columns.
- ``actions=False`` removes Dividends/Stock-Splits columns from the
  returned DataFrame; we do not need them here.
- ``fast_info`` is used for metadata where possible; it avoids a second
  heavy network call that ``.info`` triggers.
- Every yfinance exception is caught at the call site and re-raised as
  the appropriate MarketMind exception. The original exception is chained
  (``raise MarketMindError(...) from e``) for debuggability.

Point-in-time limitation
-------------------------
Yahoo Finance restates historical prices retroactively after splits and
dividends. Data fetched today for 2020-01-01 may differ from data fetched
in 2020 for the same date. This provider is NOT point-in-time correct and
documents that limitation in its ProviderCapabilities.

Exchange mapping
-----------------
yfinance returns short exchange identifiers (e.g. "NMS" for NASDAQ,
"NYQ" for NYSE). ``_YF_EXCHANGE_MAP`` normalises these to our Exchange
enum. Unknown codes are mapped to ``Exchange.UNKNOWN``.

Asset class mapping
-------------------
yfinance ``quote_type`` values ("EQUITY", "ETF", "INDEX", ...) are mapped
to our ``AssetClass`` enum via ``_YF_QUOTE_TYPE_MAP``.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import yfinance as yf
from yfinance.exceptions import (
    YFException,
    YFPricesMissingError,
    YFRateLimitError,
    YFTickerMissingError,
)

from marketmind.core.domain.asset import AssetClass, Exchange
from marketmind.core.domain.market_data import OHLCVBar, OHLCVDataset
from marketmind.core.exceptions import (
    AuthenticationError,
    InvalidTickerError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from marketmind.data.providers.base import BaseMarketDataProvider
from marketmind.data.providers.models import (
    AssetMetadata,
    OHLCVRequest,
    ProviderCapabilities,
)
from marketmind.data.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    import pandas as pd


# ---------------------------------------------------------------------------
# Mapping tables: yfinance strings -> MarketMind enums
# ---------------------------------------------------------------------------

#: Maps yfinance ``fast_info.exchange`` short codes to our Exchange enum.
#: Codes sourced from Yahoo Finance API documentation and empirical observation.
_YF_EXCHANGE_MAP: dict[str, Exchange] = {
    # NYSE variants
    "NYQ": Exchange.NYSE,
    "NYE": Exchange.NYSE,
    "NYSE": Exchange.NYSE,
    "NYB": Exchange.NYSE,
    # NASDAQ variants
    "NMS": Exchange.NASDAQ,
    "NGM": Exchange.NASDAQ,
    "NCM": Exchange.NASDAQ,
    "NASDAQ": Exchange.NASDAQ,
    # London Stock Exchange
    "LSE": Exchange.LSE,
    "IOB": Exchange.LSE,  # International Order Book (LSE)
    # Deutsche Boerse / XETRA
    "GER": Exchange.XETRA,
    "FRA": Exchange.XETRA,
    "XETRA": Exchange.XETRA,
    # Toronto Stock Exchange
    "TOR": Exchange.TSX,
    "TSX": Exchange.TSX,
    # Australian Securities Exchange
    "ASX": Exchange.ASX,
    "AXW": Exchange.ASX,
}

#: Maps yfinance ``quote_type`` instrument type strings to our AssetClass enum.
_YF_QUOTE_TYPE_MAP: dict[str, AssetClass] = {
    "EQUITY": AssetClass.STOCK,
    "ETF": AssetClass.ETF,
    # The following are not in our V1 scope but are mapped to avoid errors
    # if encountered — they will pass through as STOCK (best available guess).
    "MUTUALFUND": AssetClass.ETF,
    "INDEX": AssetClass.STOCK,
    "CRYPTOCURRENCY": AssetClass.STOCK,
    "CURRENCY": AssetClass.STOCK,
    "FUTURE": AssetClass.STOCK,
    "OPTION": AssetClass.STOCK,
}

# ---------------------------------------------------------------------------
# Provider capabilities (constructed once)
# ---------------------------------------------------------------------------

_YAHOO_CAPABILITIES = ProviderCapabilities(
    provider_id="yahoo",
    display_name="Yahoo Finance (via yfinance)",
    point_in_time_guaranteed=False,
    pit_limitation_description=(
        "Yahoo Finance restates historical prices after corporate actions "
        "(splits, dividends). Data fetched today for a past date may differ "
        "from data fetched on that past date. Backtest results may therefore "
        "be optimistic. Document this limitation in every model card that uses "
        "Yahoo Finance data."
    ),
    supported_exchanges=frozenset(
        {Exchange.NYSE, Exchange.NASDAQ, Exchange.LSE, Exchange.XETRA, Exchange.TSX, Exchange.ASX}
    ),
    supported_asset_classes=frozenset({AssetClass.STOCK, AssetClass.ETF}),
    data_delay_minutes=15,  # Yahoo free tier is 15-minute delayed
    max_history_years=None,  # No documented limit; varies by ticker
    requires_authentication=False,
    supports_real_time=False,
)


# ---------------------------------------------------------------------------
# YahooFinanceProvider
# ---------------------------------------------------------------------------


class YahooFinanceProvider(BaseMarketDataProvider):
    """
    Market data provider backed by Yahoo Finance via the ``yfinance`` library.

    All yfinance objects and pandas DataFrames are confined to this class.
    Everything returned through the public interface is a MarketMind domain
    object (``OHLCVDataset``, ``AssetMetadata``).

    Parameters
    ----------
    timeout_seconds : int
        Network timeout passed to yfinance calls. Default: 30.
    """

    def __init__(self, *, timeout_seconds: int = 30) -> None:
        super().__init__()
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}.")
        self._timeout = timeout_seconds

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _YAHOO_CAPABILITIES

    # ------------------------------------------------------------------
    # OHLCV fetch
    # ------------------------------------------------------------------

    def _fetch_ohlcv_impl(self, request: OHLCVRequest) -> OHLCVDataset:
        symbol = request.asset.symbol
        exchange_value = request.asset.exchange.value
        t_start = time.monotonic()

        self._log.debug(
            "yahoo.fetch_ohlcv.start",
            symbol=symbol,
            start=request.start.date().isoformat(),
            end=request.end.date().isoformat(),
            as_of=request.as_of.date().isoformat(),
        )

        ticker = yf.Ticker(symbol)
        df = self._call_history(ticker, request)

        if df is None or df.empty:
            self._log.info(
                "yahoo.fetch_ohlcv.empty",
                symbol=symbol,
                duration_ms=round((time.monotonic() - t_start) * 1000),
            )
            return OHLCVDataset(
                symbol=symbol,
                exchange=exchange_value,
                provider=self.capabilities.provider_id,
                as_of=request.as_of,
                bars=[],
            )

        bars = self._dataframe_to_bars(df, symbol, request.as_of)

        elapsed_ms = round((time.monotonic() - t_start) * 1000)
        self._log.info(
            "yahoo.fetch_ohlcv.complete",
            symbol=symbol,
            bars=len(bars),
            duration_ms=elapsed_ms,
        )

        return OHLCVDataset(
            symbol=symbol,
            exchange=exchange_value,
            provider=self.capabilities.provider_id,
            as_of=request.as_of,
            bars=bars,
        )

    def _call_history(
        self,
        ticker: yf.Ticker,
        request: OHLCVRequest,
    ) -> pd.DataFrame | None:
        """
        Call ``ticker.history()`` and map yfinance exceptions to ours.

        Returns the raw DataFrame, or None on an empty response.
        Raises appropriate MarketMind exceptions for all error conditions.
        """

        try:
            df: pd.DataFrame = ticker.history(
                start=request.start.strftime("%Y-%m-%d"),
                end=request.end.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=True,
                actions=False,
                timeout=self._timeout,
            )
            return df if not df.empty else None

        except YFRateLimitError as e:
            self._log.warning(
                "yahoo.rate_limit",
                symbol=request.asset.symbol,
                error=str(e),
            )
            raise RateLimitError(
                f"Yahoo Finance rate limit exceeded for '{request.asset.symbol}'. "
                "Wait before retrying."
            ) from e

        except YFPricesMissingError as e:
            self._log.warning(
                "yahoo.prices_missing",
                symbol=request.asset.symbol,
                error=str(e),
            )
            raise InvalidTickerError(
                symbol=request.asset.symbol,
                exchange=request.asset.exchange.value,
            ) from e

        except YFTickerMissingError as e:
            self._log.warning(
                "yahoo.ticker_missing",
                symbol=request.asset.symbol,
                error=str(e),
            )
            raise InvalidTickerError(
                symbol=request.asset.symbol,
                exchange=request.asset.exchange.value,
            ) from e

        except YFException as e:
            msg = str(e).lower()
            if "401" in msg or "403" in msg or "unauthorized" in msg:
                raise AuthenticationError(
                    f"Yahoo Finance rejected the request for '{request.asset.symbol}' "
                    f"with an authentication error: {e}"
                ) from e
            if "429" in msg or "rate" in msg:
                raise RateLimitError(f"Yahoo Finance rate limit: {e}") from e
            raise ProviderError(f"Yahoo Finance error for '{request.asset.symbol}': {e}") from e

        except Exception as e:
            msg = str(e).lower()
            if "403" in msg or "host not in allowlist" in msg:
                raise ProviderUnavailableError(
                    f"Yahoo Finance is unreachable (network/firewall): {e}"
                ) from e
            raise ProviderError(
                f"Unexpected error fetching '{request.asset.symbol}' from Yahoo Finance: {e}"
            ) from e

    def _dataframe_to_bars(
        self,
        df: pd.DataFrame,
        symbol: str,
        as_of: datetime,
    ) -> list[OHLCVBar]:
        """
        Convert a yfinance history DataFrame to a list of OHLCVBar objects.

        Rules applied:
        - Rows with NaN in any price column are silently dropped.
        - Rows where close <= 0 are silently dropped (invalid prices).
        - Timestamps are converted to UTC-aware datetimes.
        - Bars with timestamp > as_of are excluded (as_of boundary enforcement).
        - The resulting list is in ascending timestamp order (yfinance guarantees this).
        """
        bars: list[OHLCVBar] = []

        required = {"Open", "High", "Low", "Close", "Volume"}
        missing = required - set(df.columns)
        if missing:
            raise ProviderError(
                f"Yahoo Finance response for '{symbol}' is missing columns: {missing}. "
                f"Got: {list(df.columns)}"
            )

        for ts, row in df.iterrows():
            # Convert index timestamp to UTC-aware datetime
            bar_dt = self._to_utc(ts)

            # Skip bars beyond the as_of boundary
            if bar_dt > as_of:
                continue

            open_ = float(row["Open"])
            high = float(row["High"])
            low = float(row["Low"])
            close = float(row["Close"])
            volume = float(row["Volume"])

            # Drop rows with invalid or NaN prices
            import math

            if any(math.isnan(v) for v in (open_, high, low, close, volume)):
                continue
            if close <= 0 or low <= 0:
                continue

            # Clamp open within [low, high] to satisfy OHLCVBar invariant.
            # yfinance occasionally returns open slightly outside the range
            # due to decimal rounding in adjusted prices.
            open_ = max(low, min(high, open_))

            try:
                bars.append(
                    OHLCVBar(
                        timestamp=bar_dt,
                        open=round(open_, 6),
                        high=round(high, 6),
                        low=round(low, 6),
                        close=round(close, 6),
                        volume=max(0.0, round(volume, 0)),
                    )
                )
            except ValueError:
                # Log and skip bars that still violate price invariants
                # after clamping (e.g. low > high due to data corruption)
                self._log.warning(
                    "yahoo.bar_skipped",
                    symbol=symbol,
                    timestamp=bar_dt.isoformat(),
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                )

        return bars

    @staticmethod
    def _to_utc(ts: Any) -> datetime:
        """
        Convert a pandas Timestamp (possibly tz-aware) to a UTC datetime.

        yfinance returns tz-aware timestamps when the ticker's exchange has
        a known timezone, and tz-naive otherwise. We normalise all to UTC.
        """

        import pandas as pd

        if isinstance(ts, pd.Timestamp):
            if ts.tzinfo is not None:
                result: datetime = ts.to_pydatetime().astimezone(UTC).replace(tzinfo=UTC)
            else:
                # tz-naive: assume market close time in UTC
                result = ts.to_pydatetime().replace(tzinfo=UTC)
            return result
        # Fallback for non-Timestamp index entries (datetime subclasses)
        if isinstance(ts, datetime):
            if ts.tzinfo is not None:
                return ts.astimezone(UTC).replace(tzinfo=UTC)
            return ts.replace(tzinfo=UTC)
        # Last resort: attempt replace() — will fail loudly if ts is wrong type
        converted: datetime = ts.replace(tzinfo=UTC)
        return converted

    # ------------------------------------------------------------------
    # Symbol listing
    # ------------------------------------------------------------------

    def _list_symbols_impl(self, exchange: str) -> list[str]:
        """
        Yahoo Finance does not provide an exchange-level symbol list via its
        free API. This method returns an empty list and logs a warning.

        Callers should use a curated universe list rather than relying on
        this method for symbol discovery.
        """
        self._log.warning(
            "yahoo.list_symbols.not_supported",
            exchange=exchange,
            reason="Yahoo Finance free API does not support exchange symbol listing.",
        )
        return []

    # ------------------------------------------------------------------
    # Asset metadata
    # ------------------------------------------------------------------

    def fetch_asset_metadata(self, symbol: str, exchange: str) -> AssetMetadata:
        """
        Fetch metadata for a single asset using yfinance's fast_info.

        Uses ``fast_info`` (lightweight) rather than ``.info`` (heavyweight)
        to avoid unnecessary network calls. Falls back gracefully when
        fast_info attributes are None.

        Raises
        ------
        InvalidTickerError
            If yfinance cannot find the ticker.
        ProviderError
            On network or parsing failures.
        """
        self._log.debug("yahoo.fetch_metadata.start", symbol=symbol)
        t_start = time.monotonic()

        try:
            ticker = yf.Ticker(symbol)
            fast = ticker.fast_info

            quote_type: str = self._safe_str(fast, "quote_type", "EQUITY")
            yf_exchange: str = self._safe_str(fast, "exchange", exchange)
            currency: str = self._safe_str(fast, "currency", "USD")
            self._safe_str(fast, "timezone", "UTC")

            asset_class = _YF_QUOTE_TYPE_MAP.get(quote_type.upper(), AssetClass.STOCK)
            resolved_exchange = _YF_EXCHANGE_MAP.get(yf_exchange.upper(), Exchange.UNKNOWN)

            # Try to get the company name from .info if fast_info doesn't have it.
            # We use a try/except so a failed .info call doesn't abort metadata.
            name = self._fetch_name(ticker, symbol)

        except YFTickerMissingError as e:
            raise InvalidTickerError(symbol=symbol, exchange=exchange) from e
        except YFException as e:
            raise ProviderError(f"Yahoo Finance metadata error for '{symbol}': {e}") from e
        except Exception as e:
            msg = str(e).lower()
            if "403" in msg or "host not in allowlist" in msg:
                raise ProviderUnavailableError(f"Yahoo Finance is unreachable: {e}") from e
            raise ProviderError(f"Unexpected error fetching metadata for '{symbol}': {e}") from e

        elapsed_ms = round((time.monotonic() - t_start) * 1000)
        self._log.info(
            "yahoo.fetch_metadata.complete",
            symbol=symbol,
            exchange=resolved_exchange.value,
            asset_class=asset_class.value,
            duration_ms=elapsed_ms,
        )

        return AssetMetadata(
            symbol=symbol.upper(),
            exchange=resolved_exchange,
            name=name,
            asset_class=asset_class,
            currency=currency.upper(),
            sector="",  # Requires .info which is a heavy call; omit here
            country="",  # Same reason
            is_active=True,  # If we got here without exception, assume active
            retrieved_at=datetime.now(UTC),
        )

    @staticmethod
    def _safe_str(fast_info: Any, attr: str, default: str) -> str:
        """Return fast_info attribute as string, or default if None/missing."""
        try:
            val = getattr(fast_info, attr, None)
            if val is None:
                return default
            return str(val)
        except Exception:
            return default

    def _fetch_name(self, ticker: yf.Ticker, symbol: str) -> str:
        """
        Attempt to get the company name without raising on failure.

        Returns the symbol itself if name cannot be determined.
        """
        try:
            info: dict[str, Any] = ticker.info or {}
            return str(info.get("longName") or info.get("shortName") or symbol)
        except Exception:
            return symbol


# ---------------------------------------------------------------------------
# Auto-register with the provider registry
# ---------------------------------------------------------------------------

ProviderRegistry.register("yahoo", YahooFinanceProvider)
