"""
Unit tests for marketmind.core.domain.asset

Tests every invariant, validation rule, and property of Asset and Universe.
These tests have zero I/O - they test pure domain logic only.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange, MarketCapTier, Universe


class TestAsset:
    """Tests for the Asset value object."""

    def test_creates_valid_asset(self) -> None:
        asset = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        assert asset.symbol == "AAPL"
        assert asset.exchange == Exchange.NASDAQ
        assert asset.asset_class == AssetClass.STOCK

    def test_uid_format(self) -> None:
        asset = Asset(symbol="MSFT", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        assert asset.uid == "NASDAQ:MSFT"

    def test_uid_used_in_str(self) -> None:
        asset = Asset(symbol="SPY", exchange=Exchange.NYSE, asset_class=AssetClass.ETF)
        assert str(asset) == "NYSE:SPY"

    def test_symbol_normalised_to_uppercase(self) -> None:
        asset = Asset(symbol="aapl", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        assert asset.symbol == "AAPL"

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            Asset(symbol="", exchange=Exchange.NYSE, asset_class=AssetClass.STOCK)

    def test_default_optional_fields(self) -> None:
        asset = Asset(symbol="IBM", exchange=Exchange.NYSE, asset_class=AssetClass.STOCK)
        assert asset.name == ""
        assert asset.sector == ""
        assert asset.country == ""
        assert asset.market_cap_tier == MarketCapTier.UNKNOWN

    def test_asset_is_immutable(self) -> None:
        asset = Asset(symbol="TSLA", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        with pytest.raises(FrozenInstanceError):
            asset.symbol = "AMZN"  # type: ignore[misc]

    def test_repr(self) -> None:
        asset = Asset(symbol="GOOG", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        r = repr(asset)
        assert "GOOG" in r
        assert "NASDAQ" in r
        assert "STOCK" in r

    def test_etf_asset_class(self) -> None:
        etf = Asset(symbol="QQQ", exchange=Exchange.NASDAQ, asset_class=AssetClass.ETF)
        assert etf.asset_class == AssetClass.ETF

    def test_two_identical_assets_are_equal(self) -> None:
        a1 = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        a2 = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        assert a1 == a2

    def test_same_symbol_different_exchange_not_equal(self) -> None:
        a1 = Asset(symbol="RIO", exchange=Exchange.NYSE, asset_class=AssetClass.STOCK)
        a2 = Asset(symbol="RIO", exchange=Exchange.LSE, asset_class=AssetClass.STOCK)
        assert a1 != a2
        assert a1.uid != a2.uid


class TestUniverse:
    """Tests for the Universe value object."""

    def _make_assets(self, count: int) -> frozenset[Asset]:
        return frozenset(
            Asset(
                symbol=f"SYM{i:02d}",
                exchange=Exchange.NYSE,
                asset_class=AssetClass.STOCK,
            )
            for i in range(count)
        )

    def test_creates_valid_universe(self) -> None:
        assets = self._make_assets(5)
        u = Universe(universe_id="UNIVERSE-V1", assets=assets)
        assert u.universe_id == "UNIVERSE-V1"
        assert u.size == 5

    def test_empty_universe_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one asset"):
            Universe(universe_id="UNIVERSE-V1", assets=frozenset())

    def test_empty_id_raises(self) -> None:
        assets = self._make_assets(3)
        with pytest.raises(ValueError, match="Universe ID cannot be empty"):
            Universe(universe_id="", assets=assets)

    def test_universe_is_immutable(self) -> None:
        assets = self._make_assets(3)
        u = Universe(universe_id="UNIVERSE-V1", assets=assets)
        with pytest.raises(FrozenInstanceError):
            u.universe_id = "TAMPERED"  # type: ignore[misc]

    def test_get_by_symbol_found(self) -> None:
        asset = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        u = Universe(universe_id="UNIVERSE-V1", assets=frozenset([asset]))
        assert u.get_by_symbol("AAPL") == asset

    def test_get_by_symbol_case_insensitive(self) -> None:
        asset = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        u = Universe(universe_id="UNIVERSE-V1", assets=frozenset([asset]))
        assert u.get_by_symbol("aapl") == asset

    def test_get_by_symbol_not_found_returns_none(self) -> None:
        assets = self._make_assets(3)
        u = Universe(universe_id="UNIVERSE-V1", assets=assets)
        assert u.get_by_symbol("NOTEXIST") is None

    def test_get_by_uid_found(self) -> None:
        asset = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        u = Universe(universe_id="UNIVERSE-V1", assets=frozenset([asset]))
        assert u.get_by_uid("NASDAQ:AAPL") == asset

    def test_get_by_uid_not_found_returns_none(self) -> None:
        assets = self._make_assets(2)
        u = Universe(universe_id="UNIVERSE-V1", assets=assets)
        assert u.get_by_uid("NYSE:PHANTOM") is None

    def test_universe_str_shows_sealed_status(self) -> None:
        assets = self._make_assets(3)
        draft = Universe(universe_id="UNIVERSE-V1", assets=assets, is_sealed=False)
        sealed = Universe(universe_id="UNIVERSE-V1", assets=assets, is_sealed=True)
        assert "DRAFT" in str(draft)
        assert "SEALED" in str(sealed)

    def test_size_property(self) -> None:
        assets = self._make_assets(30)
        u = Universe(universe_id="UNIVERSE-V1", assets=assets)
        assert u.size == 30
