"""
Integration tests: provider layer end-to-end.

Exercises the full chain:
  Settings -> ProviderRegistry -> BaseMarketDataProvider -> OHLCVDataset

These tests do not mock any internal components — they exercise the real
provider implementation in the configured test environment.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.exceptions import DataUnavailableError, InvalidTickerError
from marketmind.data.providers import MockProvider, ProviderRegistry


class TestProviderRegistryIntegration:
    """Settings-driven provider resolution through the full stack."""

    def test_get_from_settings_returns_usable_provider(self) -> None:
        provider = ProviderRegistry.get_from_settings()
        assert provider is not None
        assert provider.capabilities.provider_id in ProviderRegistry.available()

    def test_fetched_provider_can_serve_request(self) -> None:
        provider = ProviderRegistry.get_from_settings()
        asset = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        ds = provider.fetch_ohlcv(
            asset,
            start=datetime(2023, 1, 3, tzinfo=UTC),
            end=datetime(2023, 1, 31, tzinfo=UTC),
            as_of=datetime(2023, 2, 1, tzinfo=UTC),
        )
        assert ds.row_count > 0
        assert ds.symbol == "AAPL"


class TestMockProviderFullChain:
    """Full chain: request -> MockProvider -> OHLCVDataset -> assertions."""

    def setup_method(self) -> None:
        self.provider = MockProvider()
        self.asset = Asset(
            symbol="AAPL",
            exchange=Exchange.NASDAQ,
            asset_class=AssetClass.STOCK,
        )
        self.start = datetime(2022, 1, 3, tzinfo=UTC)
        self.end = datetime(2022, 12, 30, 21, 0, tzinfo=UTC)
        self.as_of = datetime(2023, 1, 2, tzinfo=UTC)

    def test_full_year_fetch_returns_approximately_252_bars(self) -> None:
        ds = self.provider.fetch_ohlcv(self.asset, self.start, self.end, self.as_of)
        # A trading year has ~252 bars; 2022 had some holidays we don't model,
        # so accept anything between 240 and 265
        assert 240 <= ds.row_count <= 265, f"Expected ~252 bars for a full year, got {ds.row_count}"

    def test_dataset_has_correct_metadata(self) -> None:
        ds = self.provider.fetch_ohlcv(self.asset, self.start, self.end, self.as_of)
        assert ds.symbol == "AAPL"
        assert ds.exchange == "NASDAQ"
        assert ds.provider == "mock"
        assert ds.as_of == self.as_of

    def test_all_bars_have_positive_prices(self) -> None:
        ds = self.provider.fetch_ohlcv(self.asset, self.start, self.end, self.as_of)
        for bar in ds.bars:
            assert bar.open > 0
            assert bar.high > 0
            assert bar.low > 0
            assert bar.close > 0
            assert bar.high >= bar.low

    def test_as_of_exactly_at_end_of_range(self) -> None:
        """as_of equal to end is a valid edge case."""
        ds = self.provider.fetch_ohlcv(
            self.asset,
            start=self.start,
            end=self.end,
            as_of=self.end,
        )
        assert ds.row_count > 0

    def test_single_day_range(self) -> None:
        single_day = datetime(2023, 1, 3, 21, 0, tzinfo=UTC)
        ds = self.provider.fetch_ohlcv(
            self.asset,
            start=single_day,
            end=single_day,
            as_of=datetime(2023, 1, 4, tzinfo=UTC),
        )
        # Jan 3 2023 was a Tuesday (trading day)
        assert ds.row_count == 1

    def test_weekend_only_range_returns_empty(self) -> None:
        # 2023-01-07 is Saturday, 2023-01-08 is Sunday
        sat = datetime(2023, 1, 7, 0, 0, tzinfo=UTC)
        sun = datetime(2023, 1, 8, 21, 0, tzinfo=UTC)
        ds = self.provider.fetch_ohlcv(
            self.asset,
            start=sat,
            end=sun,
            as_of=datetime(2023, 1, 9, tzinfo=UTC),
        )
        assert ds.is_empty()

    def test_error_simulation_propagates_through_full_chain(self) -> None:
        provider = MockProvider(fail_symbols={"AAPL"})
        with pytest.raises(InvalidTickerError) as exc_info:
            provider.fetch_ohlcv(self.asset, self.start, self.end, self.as_of)
        assert exc_info.value.symbol == "AAPL"

    def test_unavailable_simulation_propagates(self) -> None:
        provider = MockProvider(unavailable_symbols={"AAPL"})
        with pytest.raises(DataUnavailableError):
            provider.fetch_ohlcv(self.asset, self.start, self.end, self.as_of)


class TestMultiAssetDeterminism:
    """Cross-asset determinism and independence."""

    def test_multiple_assets_independent(self) -> None:
        """Fetching AAPL should not affect subsequent MSFT results."""
        provider = MockProvider()
        aapl = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        msft = Asset(symbol="MSFT", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        start = datetime(2023, 1, 3, tzinfo=UTC)
        end = datetime(2023, 3, 31, 21, tzinfo=UTC)
        as_of = datetime(2023, 4, 1, tzinfo=UTC)

        ds_aapl1 = provider.fetch_ohlcv(aapl, start, end, as_of)
        _ = provider.fetch_ohlcv(msft, start, end, as_of)  # interleave
        ds_aapl2 = provider.fetch_ohlcv(aapl, start, end, as_of)

        closes1 = [b.close for b in ds_aapl1.bars]
        closes2 = [b.close for b in ds_aapl2.bars]
        assert closes1 == closes2, "AAPL prices changed after fetching MSFT"
