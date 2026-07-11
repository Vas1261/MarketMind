"""
Unit tests for marketmind.data.providers.mock

Tests all MockProvider behaviour: determinism, known assets, error simulation,
empty results, symbol listing, asset metadata, and the window-consistency
property of the synthetic data generator.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.exceptions import DataUnavailableError, InvalidTickerError
from marketmind.data.providers.mock import MockProvider

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

AAPL = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
MSFT = Asset(symbol="MSFT", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
SPY = Asset(symbol="SPY", exchange=Exchange.NYSE, asset_class=AssetClass.ETF)
RIO = Asset(symbol="RIO", exchange=Exchange.LSE, asset_class=AssetClass.STOCK)
FAKE = Asset(symbol="FAKE", exchange=Exchange.NYSE, asset_class=AssetClass.STOCK)

START = datetime(2023, 1, 3, 0, 0, tzinfo=UTC)
END = datetime(2023, 1, 31, 21, 0, tzinfo=UTC)
AS_OF = datetime(2023, 2, 1, 0, 0, tzinfo=UTC)


def fetch(
    provider: MockProvider,
    asset: Asset = AAPL,
    start: datetime = START,
    end: datetime = END,
    as_of: datetime = AS_OF,
):  # type: ignore[no-untyped-def]
    return provider.fetch_ohlcv(asset, start, end, as_of)


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestMockProviderCapabilities:
    """Tests for capabilities property."""

    def test_provider_id_is_mock(self) -> None:
        assert MockProvider().capabilities.provider_id == "mock"

    def test_pit_guaranteed(self) -> None:
        assert MockProvider().capabilities.point_in_time_guaranteed is True

    def test_no_auth_required(self) -> None:
        assert MockProvider().capabilities.requires_authentication is False

    def test_supports_all_exchanges(self) -> None:
        caps = MockProvider().capabilities
        for exchange in Exchange:
            assert caps.supports_exchange(exchange)

    def test_supports_all_asset_classes(self) -> None:
        caps = MockProvider().capabilities
        for ac in AssetClass:
            assert caps.supports_asset_class(ac)

    def test_provider_metadata_dict_is_complete(self) -> None:
        meta = MockProvider().provider_metadata()
        assert meta["provider_id"] == "mock"
        assert meta["point_in_time_guaranteed"] is True
        assert meta["requires_authentication"] is False


class TestMockProviderFetchOHLCV:
    """Tests for OHLCV data generation."""

    def test_returns_non_empty_dataset(self) -> None:
        ds = fetch(MockProvider())
        assert ds.row_count > 0

    def test_weekends_excluded(self) -> None:
        """All bars must be on Monday-Friday."""
        ds = fetch(MockProvider())
        for bar in ds.bars:
            assert bar.timestamp.weekday() < 5, (
                f"Bar on {bar.timestamp.strftime('%A %Y-%m-%d')} is a weekend"
            )

    def test_bars_in_ascending_order(self) -> None:
        ds = fetch(MockProvider())
        timestamps = [b.timestamp for b in ds.bars]
        assert timestamps == sorted(timestamps)

    def test_all_bars_before_as_of(self) -> None:
        ds = fetch(MockProvider())
        for bar in ds.bars:
            assert bar.timestamp <= AS_OF

    def test_price_relationship_invariant_on_every_bar(self) -> None:
        ds = fetch(MockProvider())
        for bar in ds.bars:
            assert bar.low <= bar.open <= bar.high, f"open violation at {bar.timestamp}"
            assert bar.low <= bar.close <= bar.high, f"close violation at {bar.timestamp}"

    def test_all_prices_positive(self) -> None:
        ds = fetch(MockProvider())
        for bar in ds.bars:
            assert bar.open > 0
            assert bar.high > 0
            assert bar.low > 0
            assert bar.close > 0

    def test_all_volumes_non_negative(self) -> None:
        ds = fetch(MockProvider())
        for bar in ds.bars:
            assert bar.volume >= 0

    def test_symbol_matches_request(self) -> None:
        ds = fetch(MockProvider())
        assert ds.symbol == "AAPL"

    def test_exchange_matches_request(self) -> None:
        ds = fetch(MockProvider())
        assert ds.exchange == "NASDAQ"

    def test_provider_field_is_mock(self) -> None:
        ds = fetch(MockProvider())
        assert ds.provider == "mock"


class TestMockProviderDeterminism:
    """Tests for reproducibility guarantees."""

    def test_same_args_same_result(self) -> None:
        p = MockProvider()
        ds1 = fetch(p)
        ds2 = fetch(p)
        closes1 = [b.close for b in ds1.bars]
        closes2 = [b.close for b in ds2.bars]
        assert closes1 == closes2

    def test_fresh_instances_same_result(self) -> None:
        ds1 = fetch(MockProvider())
        ds2 = fetch(MockProvider())
        assert [b.close for b in ds1.bars] == [b.close for b in ds2.bars]

    def test_different_symbols_different_prices(self) -> None:
        p = MockProvider()
        ds_aapl = fetch(p, asset=AAPL)
        ds_msft = fetch(p, asset=MSFT)
        # First closes should differ (different seed per symbol)
        assert ds_aapl.bars[0].close != ds_msft.bars[0].close

    def test_window_consistency(self) -> None:
        """
        Critical determinism property:
        The bars within a narrow window must be identical whether fetched as
        part of a wider request or as a standalone narrow request.
        """
        p = MockProvider()

        narrow_start = datetime(2023, 1, 10, 0, 0, tzinfo=UTC)
        narrow_end = datetime(2023, 1, 20, 21, 0, tzinfo=UTC)

        ds_full = fetch(p, start=START, end=END)
        ds_narrow = fetch(p, start=narrow_start, end=narrow_end)

        bars_in_range = [b for b in ds_full.bars if narrow_start <= b.timestamp <= narrow_end]

        assert len(bars_in_range) == len(ds_narrow.bars), (
            "Narrow fetch returned different number of bars than same window in full fetch"
        )
        for full_bar, narrow_bar in zip(bars_in_range, ds_narrow.bars, strict=False):
            assert full_bar.close == narrow_bar.close, (
                f"Close price mismatch at {full_bar.timestamp}: "
                f"full={full_bar.close}, narrow={narrow_bar.close}"
            )


class TestMockProviderKnownAssets:
    """Tests for the known-asset catalogue."""

    def test_known_nasdaq_stocks_return_data(self) -> None:
        p = MockProvider()
        for asset in [AAPL, MSFT]:
            ds = fetch(p, asset=asset)
            assert ds.row_count > 0

    def test_known_nyse_etf_returns_data(self) -> None:
        ds = fetch(MockProvider(), asset=SPY)
        assert ds.row_count > 0

    def test_known_lse_stock_returns_data(self) -> None:
        lse_start = START
        lse_end = END
        lse_as_of = AS_OF
        ds = MockProvider().fetch_ohlcv(RIO, lse_start, lse_end, lse_as_of)
        assert ds.row_count > 0

    def test_unknown_symbol_raises_invalid_ticker_error(self) -> None:
        with pytest.raises(InvalidTickerError) as exc_info:
            fetch(MockProvider(), asset=FAKE)
        assert "FAKE" in str(exc_info.value)

    def test_empty_dataset_for_force_empty_symbol(self) -> None:
        p = MockProvider(force_empty_symbols={"AAPL"})
        ds = fetch(p)
        assert ds.is_empty()
        assert ds.row_count == 0


class TestMockProviderErrorSimulation:
    """Tests for configurable error behaviour."""

    def test_fail_symbol_raises_invalid_ticker_error(self) -> None:
        p = MockProvider(fail_symbols={"AAPL"})
        with pytest.raises(InvalidTickerError) as exc_info:
            fetch(p)
        assert exc_info.value.symbol == "AAPL"
        assert exc_info.value.exchange == "NASDAQ"

    def test_unavailable_symbol_raises_data_unavailable_error(self) -> None:
        p = MockProvider(unavailable_symbols={"AAPL"})
        with pytest.raises(DataUnavailableError):
            fetch(p)

    def test_fail_symbol_on_metadata_raises(self) -> None:
        p = MockProvider(fail_symbols={"AAPL"})
        with pytest.raises(InvalidTickerError):
            p.fetch_asset_metadata("AAPL", "NASDAQ")

    def test_unavailable_symbol_on_metadata_raises(self) -> None:
        p = MockProvider(unavailable_symbols={"AAPL"})
        with pytest.raises(DataUnavailableError):
            p.fetch_asset_metadata("AAPL", "NASDAQ")

    def test_non_failing_symbol_unaffected_by_fail_list(self) -> None:
        p = MockProvider(fail_symbols={"MSFT"})
        ds = fetch(p, asset=AAPL)
        assert ds.row_count > 0


class TestMockProviderSymbolListing:
    """Tests for list_available_symbols()."""

    def test_lists_nasdaq_symbols(self) -> None:
        symbols = MockProvider().list_available_symbols("NASDAQ")
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_lists_nyse_symbols(self) -> None:
        symbols = MockProvider().list_available_symbols("NYSE")
        assert "JPM" in symbols

    def test_unknown_exchange_returns_empty_list(self) -> None:
        symbols = MockProvider().list_available_symbols("UNKNOWN_EXCHANGE")
        assert symbols == []

    def test_all_symbols_uppercase(self) -> None:
        symbols = MockProvider().list_available_symbols("NASDAQ")
        assert all(s == s.upper() for s in symbols)


class TestMockProviderMetadata:
    """Tests for fetch_asset_metadata()."""

    def test_known_symbol_returns_metadata(self) -> None:
        meta = MockProvider().fetch_asset_metadata("AAPL", "NASDAQ")
        assert meta.symbol == "AAPL"
        assert meta.currency == "USD"
        assert meta.is_active is True

    def test_delisted_symbol_is_inactive(self) -> None:
        meta = MockProvider().fetch_asset_metadata("DELISTED", "NYSE")
        assert meta.is_active is False

    def test_unknown_symbol_raises(self) -> None:
        with pytest.raises(InvalidTickerError):
            MockProvider().fetch_asset_metadata("NOTREAL", "NYSE")

    def test_to_asset_produces_correct_asset(self) -> None:
        meta = MockProvider().fetch_asset_metadata("AAPL", "NASDAQ")
        asset = meta.to_asset()
        assert asset.symbol == "AAPL"
        assert asset.exchange == Exchange.NASDAQ


class TestMockProviderGetKnownAsset:
    """Tests for the get_known_asset() convenience method."""

    def test_returns_asset_for_known_symbol(self) -> None:
        asset = MockProvider().get_known_asset("AAPL")
        assert isinstance(asset, Asset)
        assert asset.symbol == "AAPL"

    def test_case_insensitive(self) -> None:
        asset = MockProvider().get_known_asset("aapl")
        assert asset.symbol == "AAPL"

    def test_unknown_symbol_raises(self) -> None:
        with pytest.raises(InvalidTickerError):
            MockProvider().get_known_asset("NOTREAL")
