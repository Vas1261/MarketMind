"""
Unit tests for marketmind.data.providers.yahoo

All yfinance network calls are mocked via unittest.mock.patch.
Zero live network access — safe to run in CI.

Test strategy
-------------
- Build realistic pandas DataFrames that match yfinance's actual output
  (columns: Open, High, Low, Close, Volume; DatetimeIndex tz-aware).
- Patch yfinance.Ticker so history() returns our controlled DataFrame.
- Patch fast_info attributes for metadata tests.
- Each error path is tested by making history() raise the corresponding
  yfinance exception and asserting the correct MarketMind exception emerges.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.exceptions import (
    AuthenticationError,
    InvalidTickerError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from marketmind.data.providers.yahoo import (
    _YF_EXCHANGE_MAP,
    _YF_QUOTE_TYPE_MAP,
    YahooFinanceProvider,
)

# ---------------------------------------------------------------------------
# Shared test assets
# ---------------------------------------------------------------------------

AAPL = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
SPY = Asset(symbol="SPY", exchange=Exchange.NYSE, asset_class=AssetClass.ETF)
FAKE = Asset(symbol="FAKE", exchange=Exchange.NYSE, asset_class=AssetClass.STOCK)

START = datetime(2024, 1, 2, tzinfo=UTC)
END = datetime(2024, 1, 12, 21, 0, tzinfo=UTC)
AS_OF = datetime(2024, 1, 15, tzinfo=UTC)


# ---------------------------------------------------------------------------
# DataFrame builders matching yfinance output format
# ---------------------------------------------------------------------------


def _make_ohlcv_df(
    dates: list[str],
    base_price: float = 100.0,
    tz: str = "America/New_York",
) -> pd.DataFrame:
    """
    Build a DataFrame that matches yfinance history() output:
    - DatetimeIndex, tz-aware
    - Columns: Open, High, Low, Close, Volume
    - All prices positive, OHLCV invariants satisfied
    """
    index = pd.DatetimeIndex(
        [pd.Timestamp(d, tz=tz) for d in dates],
        name="Date",
    )
    n = len(dates)
    data = {
        "Open": [base_price + i * 0.5 for i in range(n)],
        "High": [base_price + i * 0.5 + 2.0 for i in range(n)],
        "Low": [base_price + i * 0.5 - 1.0 for i in range(n)],
        "Close": [base_price + i * 0.5 + 0.5 for i in range(n)],
        "Volume": [1_000_000.0 + i * 10_000 for i in range(n)],
    }
    return pd.DataFrame(data, index=index)


def _make_fast_info(
    quote_type: str = "EQUITY",
    exchange: str = "NMS",
    currency: str = "USD",
    timezone: str = "America/New_York",
) -> MagicMock:
    """Build a mock fast_info object matching yfinance's FastInfo interface."""
    fi = MagicMock()
    fi.quote_type = quote_type
    fi.exchange = exchange
    fi.currency = currency
    fi.timezone = timezone
    return fi


# ---------------------------------------------------------------------------
# Capability tests (no mocking needed)
# ---------------------------------------------------------------------------


class TestYahooCapabilities:
    """Tests that do not require network access."""

    def test_provider_id(self) -> None:
        assert YahooFinanceProvider().capabilities.provider_id == "yahoo"

    def test_not_point_in_time_guaranteed(self) -> None:
        assert YahooFinanceProvider().capabilities.point_in_time_guaranteed is False

    def test_pit_limitation_description_present(self) -> None:
        desc = YahooFinanceProvider().capabilities.pit_limitation_description
        assert len(desc) > 20

    def test_no_auth_required(self) -> None:
        assert YahooFinanceProvider().capabilities.requires_authentication is False

    def test_supports_nyse_and_nasdaq(self) -> None:
        caps = YahooFinanceProvider().capabilities
        assert caps.supports_exchange(Exchange.NYSE)
        assert caps.supports_exchange(Exchange.NASDAQ)

    def test_supports_stock_and_etf(self) -> None:
        caps = YahooFinanceProvider().capabilities
        assert caps.supports_asset_class(AssetClass.STOCK)
        assert caps.supports_asset_class(AssetClass.ETF)

    def test_data_delay_minutes_positive(self) -> None:
        assert YahooFinanceProvider().capabilities.data_delay_minutes > 0

    def test_provider_metadata_dict_complete(self) -> None:
        meta = YahooFinanceProvider().provider_metadata()
        for key in ("provider_id", "name", "point_in_time_guaranteed", "data_delay_minutes"):
            assert key in meta

    def test_invalid_timeout_raises(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            YahooFinanceProvider(timeout_seconds=0)

    def test_custom_timeout_accepted(self) -> None:
        p = YahooFinanceProvider(timeout_seconds=60)
        assert p._timeout == 60


# ---------------------------------------------------------------------------
# Successful OHLCV fetch
# ---------------------------------------------------------------------------


class TestYahooFetchOHLCVSuccess:
    """Tests for successful data retrieval paths."""

    def _make_provider(self) -> YahooFinanceProvider:
        return YahooFinanceProvider()

    def test_returns_ohlcv_dataset(self) -> None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        df = _make_ohlcv_df(dates)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        assert result.symbol == "AAPL"
        assert result.exchange == "NASDAQ"
        assert result.provider == "yahoo"
        assert result.row_count == 4

    def test_bars_have_correct_structure(self) -> None:
        dates = ["2024-01-02", "2024-01-03"]
        df = _make_ohlcv_df(dates, base_price=182.0)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        bar = result.bars[0]
        assert bar.close > 0
        assert bar.high >= bar.close >= bar.low
        assert bar.volume >= 0
        assert bar.timestamp.tzinfo is not None

    def test_all_bars_are_utc_aware(self) -> None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        df = _make_ohlcv_df(dates)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        for bar in result.bars:
            assert bar.timestamp.tzinfo is not None

    def test_bars_in_ascending_order(self) -> None:
        dates = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
        df = _make_ohlcv_df(dates)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        timestamps = [b.timestamp for b in result.bars]
        assert timestamps == sorted(timestamps)

    def test_history_called_with_correct_params(self) -> None:
        dates = ["2024-01-02"]
        df = _make_ohlcv_df(dates)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_instance = mock_ticker_cls.return_value
            mock_instance.history.return_value = df
            self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        call_kwargs = mock_instance.history.call_args.kwargs
        assert call_kwargs["interval"] == "1d"
        assert call_kwargs["auto_adjust"] is True
        assert call_kwargs["actions"] is False
        assert call_kwargs["start"] == "2024-01-02"

    def test_etf_asset_works(self) -> None:
        dates = ["2024-01-02", "2024-01-03"]
        df = _make_ohlcv_df(dates, base_price=480.0)
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(SPY, START, END, AS_OF)

        assert result.symbol == "SPY"
        assert result.exchange == "NYSE"

    def test_tz_naive_index_handled(self) -> None:
        """yfinance sometimes returns tz-naive timestamps for certain tickers."""
        dates = ["2024-01-02", "2024-01-03"]
        # Build a tz-naive DataFrame
        index = pd.DatetimeIndex(
            [pd.Timestamp(d) for d in dates],
            name="Date",
        )
        df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.0],
                "Volume": [1_000_000.0, 1_100_000.0],
            },
            index=index,
        )
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = self._make_provider().fetch_ohlcv(AAPL, START, END, AS_OF)

        assert result.row_count == 2
        for bar in result.bars:
            assert bar.timestamp.tzinfo is not None


# ---------------------------------------------------------------------------
# Empty / missing data
# ---------------------------------------------------------------------------


class TestYahooEmptyResponse:
    """Tests for empty DataFrame responses."""

    def test_empty_dataframe_returns_empty_dataset(self) -> None:
        empty_df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = empty_df
            result = YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)

        assert result.is_empty()
        assert result.row_count == 0
        assert result.symbol == "AAPL"

    def test_nan_rows_are_dropped(self) -> None:
        """Rows with NaN prices must be excluded from the output."""
        import math

        dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
        df = _make_ohlcv_df(dates)
        # Inject NaN into row 1
        df.iloc[1, df.columns.get_loc("Close")] = float("nan")

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)

        assert result.row_count == 2
        for bar in result.bars:
            assert not math.isnan(bar.close)

    def test_zero_price_rows_are_dropped(self) -> None:
        dates = ["2024-01-02", "2024-01-03"]
        df = _make_ohlcv_df(dates)
        df.iloc[0, df.columns.get_loc("Close")] = 0.0
        df.iloc[0, df.columns.get_loc("Low")] = 0.0

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)

        assert result.row_count == 1

    def test_bars_after_as_of_excluded(self) -> None:
        """Bars timestamped after as_of must be filtered out."""
        dates = ["2024-01-12", "2024-01-16"]  # Jan 16 is after AS_OF (Jan 15)
        df = _make_ohlcv_df(dates)

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            result = YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)

        # Jan 16 bar should be excluded
        assert result.row_count == 1


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestYahooErrorMapping:
    """Tests that yfinance exceptions map to correct MarketMind exceptions."""

    def _fetch(self, exc: Exception) -> None:
        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.side_effect = exc
            YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)

    def test_yf_rate_limit_maps_to_rate_limit_error(self) -> None:
        from yfinance.exceptions import YFRateLimitError

        with pytest.raises(RateLimitError):
            self._fetch(YFRateLimitError())

    def test_yf_prices_missing_maps_to_invalid_ticker(self) -> None:
        from yfinance.exceptions import YFPricesMissingError

        with pytest.raises(InvalidTickerError) as exc_info:
            self._fetch(YFPricesMissingError("FAKE", "no data"))
        assert exc_info.value.symbol == "AAPL"

    def test_yf_ticker_missing_maps_to_invalid_ticker(self) -> None:
        from yfinance.exceptions import YFTickerMissingError

        with pytest.raises(InvalidTickerError):
            self._fetch(YFTickerMissingError("FAKE", "delisted"))

    def test_yf_exception_auth_maps_to_auth_error(self) -> None:
        from yfinance.exceptions import YFException

        with pytest.raises(AuthenticationError):
            self._fetch(YFException("HTTP Error 403: Forbidden"))

    def test_yf_exception_rate_string_maps_to_rate_limit(self) -> None:
        from yfinance.exceptions import YFException

        with pytest.raises(RateLimitError):
            self._fetch(YFException("429 rate limit exceeded"))

    def test_yf_generic_exception_maps_to_provider_error(self) -> None:
        from yfinance.exceptions import YFException

        with pytest.raises(ProviderError):
            self._fetch(YFException("Unexpected server error"))

    def test_network_403_maps_to_provider_unavailable(self) -> None:
        with pytest.raises(ProviderUnavailableError):
            self._fetch(
                Exception("HTTP Error 403: Host not in allowlist: query2.finance.yahoo.com")
            )

    def test_raw_yf_exception_never_leaks(self) -> None:
        """No yfinance exception type should ever propagate to callers."""
        from yfinance.exceptions import YFException, YFRateLimitError

        for exc in [
            YFException("some error"),
            YFRateLimitError(),
        ]:
            with pytest.raises(ProviderError):  # All are subclasses of ProviderError
                self._fetch(exc)

    def test_chained_exception_preserved(self) -> None:
        """Original exception must be chained via __cause__."""
        from yfinance.exceptions import YFRateLimitError

        with pytest.raises(RateLimitError) as exc_info:
            self._fetch(YFRateLimitError())
        assert exc_info.value.__cause__ is not None


# ---------------------------------------------------------------------------
# Missing columns
# ---------------------------------------------------------------------------


class TestYahooMalformedResponse:
    """Tests for DataFrames with unexpected structure."""

    def test_missing_close_column_raises_provider_error(self) -> None:
        dates = ["2024-01-02"]
        df = _make_ohlcv_df(dates)
        df = df.drop(columns=["Close"])

        with patch("yfinance.Ticker") as mock_ticker_cls:
            mock_ticker_cls.return_value.history.return_value = df
            with pytest.raises(ProviderError, match="missing columns"):
                YahooFinanceProvider().fetch_ohlcv(AAPL, START, END, AS_OF)


# ---------------------------------------------------------------------------
# Asset metadata
# ---------------------------------------------------------------------------


class TestYahooAssetMetadata:
    """Tests for fetch_asset_metadata()."""

    def _make_ticker_mock(
        self,
        quote_type: str = "EQUITY",
        exchange: str = "NMS",
        currency: str = "USD",
        long_name: str = "Apple Inc.",
    ) -> MagicMock:
        ticker = MagicMock()
        ticker.fast_info = _make_fast_info(quote_type, exchange, currency)
        ticker.info = {"longName": long_name}
        return ticker

    def test_returns_asset_metadata(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock()
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.symbol == "AAPL"
        assert meta.currency == "USD"

    def test_equity_maps_to_stock_class(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(quote_type="EQUITY")
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.asset_class == AssetClass.STOCK

    def test_etf_maps_to_etf_class(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(
                quote_type="ETF", exchange="NYQ", long_name="SPDR S&P 500 ETF"
            )
            meta = YahooFinanceProvider().fetch_asset_metadata("SPY", "NYSE")

        assert meta.asset_class == AssetClass.ETF

    def test_nms_exchange_maps_to_nasdaq(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(exchange="NMS")
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.exchange == Exchange.NASDAQ

    def test_nyq_exchange_maps_to_nyse(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(exchange="NYQ")
            meta = YahooFinanceProvider().fetch_asset_metadata("JPM", "NYSE")

        assert meta.exchange == Exchange.NYSE

    def test_unknown_exchange_maps_to_unknown(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(exchange="EXOTIC")
            meta = YahooFinanceProvider().fetch_asset_metadata("XYZ", "UNKNOWN")

        assert meta.exchange == Exchange.UNKNOWN

    def test_name_from_long_name(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock(long_name="Apple Inc.")
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.name == "Apple Inc."

    def test_name_falls_back_to_symbol(self) -> None:
        ticker = self._make_ticker_mock()
        ticker.info = {}  # No name fields
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = ticker
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.name == "AAPL"

    def test_retrieved_at_is_utc_aware(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock()
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.retrieved_at.tzinfo is not None

    def test_symbol_uppercased(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock()
            meta = YahooFinanceProvider().fetch_asset_metadata("aapl", "NASDAQ")

        assert meta.symbol == "AAPL"

    def test_is_active_true_on_success(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock()
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        assert meta.is_active is True

    def test_ticker_missing_raises_invalid_ticker(self) -> None:
        from yfinance.exceptions import YFTickerMissingError

        ticker = MagicMock()
        # Make accessing any property on fast_info raise YFTickerMissingError
        type(ticker).fast_info = property(
            lambda self: (_ for _ in ()).throw(YFTickerMissingError("FAKE", "delisted"))
        )
        with patch("yfinance.Ticker", return_value=ticker), pytest.raises(InvalidTickerError):
            YahooFinanceProvider().fetch_asset_metadata("FAKE", "NYSE")

    def test_to_asset_produces_valid_domain_asset(self) -> None:
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = self._make_ticker_mock()
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        asset = meta.to_asset()
        assert isinstance(asset, Asset)
        assert asset.symbol == "AAPL"


# ---------------------------------------------------------------------------
# Symbol listing
# ---------------------------------------------------------------------------


class TestYahooSymbolListing:
    """Tests for list_available_symbols() (not supported by Yahoo)."""

    def test_returns_empty_list(self) -> None:
        result = YahooFinanceProvider().list_available_symbols("NYSE")
        assert result == []

    def test_returns_list_type(self) -> None:
        result = YahooFinanceProvider().list_available_symbols("NASDAQ")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Exchange and quote-type mapping tables
# ---------------------------------------------------------------------------


class TestMappingTables:
    """Tests for the _YF_EXCHANGE_MAP and _YF_QUOTE_TYPE_MAP constants."""

    def test_nms_maps_to_nasdaq(self) -> None:
        assert _YF_EXCHANGE_MAP["NMS"] == Exchange.NASDAQ

    def test_nyq_maps_to_nyse(self) -> None:
        assert _YF_EXCHANGE_MAP["NYQ"] == Exchange.NYSE

    def test_lse_maps_to_lse(self) -> None:
        assert _YF_EXCHANGE_MAP["LSE"] == Exchange.LSE

    def test_ger_maps_to_xetra(self) -> None:
        assert _YF_EXCHANGE_MAP["GER"] == Exchange.XETRA

    def test_equity_maps_to_stock(self) -> None:
        assert _YF_QUOTE_TYPE_MAP["EQUITY"] == AssetClass.STOCK

    def test_etf_maps_to_etf(self) -> None:
        assert _YF_QUOTE_TYPE_MAP["ETF"] == AssetClass.ETF


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------


class TestYahooRegistration:
    """Tests that YahooFinanceProvider registers itself correctly."""

    def test_yahoo_is_registered(self) -> None:
        from marketmind.data.providers.registry import ProviderRegistry

        assert ProviderRegistry.is_registered("yahoo")

    def test_registry_get_returns_yahoo_instance(self) -> None:
        from marketmind.data.providers.registry import ProviderRegistry

        provider = ProviderRegistry.get("yahoo")
        assert isinstance(provider, YahooFinanceProvider)

    def test_to_asset_conversion_roundtrip(self) -> None:
        """Metadata from Yahoo should produce a valid Asset via to_asset()."""
        with patch("yfinance.Ticker") as mock_cls:
            mock_cls.return_value = _make_ticker_mock_fn()
            meta = YahooFinanceProvider().fetch_asset_metadata("AAPL", "NASDAQ")

        asset = meta.to_asset()
        assert asset.uid == "NASDAQ:AAPL"


def _make_ticker_mock_fn() -> MagicMock:
    ticker = MagicMock()
    ticker.fast_info = _make_fast_info("EQUITY", "NMS", "USD")
    ticker.info = {"longName": "Apple Inc."}
    return ticker
