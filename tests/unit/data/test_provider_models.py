"""
Unit tests for marketmind.data.providers.models

Tests all invariants of OHLCVRequest, ProviderCapabilities, and AssetMetadata.
Zero I/O — pure structural validation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.data.providers.models import (
    AssetMetadata,
    OHLCVRequest,
    ProviderCapabilities,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

AAPL = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
T0 = datetime(2023, 1, 3, 0, 0, tzinfo=UTC)
T1 = datetime(2023, 1, 31, 21, 0, tzinfo=UTC)
AS_OF = datetime(2023, 2, 1, 0, 0, tzinfo=UTC)


class TestOHLCVRequest:
    """Tests for OHLCVRequest value object."""

    def _make(self, **kw: object) -> OHLCVRequest:
        defaults: dict[str, object] = {
            "asset": AAPL,
            "start": T0,
            "end": T1,
            "as_of": AS_OF,
        }
        defaults.update(kw)
        return OHLCVRequest(**defaults)  # type: ignore[arg-type]

    def test_creates_valid_request(self) -> None:
        req = self._make()
        assert req.symbol == "AAPL"
        assert req.exchange == "NASDAQ"

    def test_is_immutable(self) -> None:
        req = self._make()
        with pytest.raises(FrozenInstanceError):
            req.asset = AAPL  # type: ignore[misc]

    def test_naive_start_raises(self) -> None:
        with pytest.raises(ValueError, match="start must be timezone-aware"):
            self._make(start=datetime(2023, 1, 3))

    def test_naive_end_raises(self) -> None:
        with pytest.raises(ValueError, match="end must be timezone-aware"):
            self._make(end=datetime(2023, 1, 31))

    def test_naive_as_of_raises(self) -> None:
        with pytest.raises(ValueError, match="as_of must be timezone-aware"):
            self._make(as_of=datetime(2023, 2, 1))

    def test_start_after_end_raises(self) -> None:
        with pytest.raises(ValueError, match=r"start.*must not be after end"):
            self._make(start=T1, end=T0)

    def test_end_equals_start_is_valid(self) -> None:
        req = self._make(start=T0, end=T0, as_of=AS_OF)
        assert req.start == req.end

    def test_end_after_as_of_raises(self) -> None:
        with pytest.raises(ValueError, match=r"end.*must not be after as_of"):
            self._make(end=AS_OF + timedelta(days=1), as_of=AS_OF)

    def test_end_equal_to_as_of_is_valid(self) -> None:
        req = self._make(end=AS_OF, as_of=AS_OF)
        assert req.end == req.as_of

    def test_symbol_convenience_property(self) -> None:
        req = self._make()
        assert req.symbol == "AAPL"

    def test_exchange_convenience_property(self) -> None:
        req = self._make()
        assert req.exchange == "NASDAQ"

    def test_str_representation(self) -> None:
        req = self._make()
        s = str(req)
        assert "AAPL" in s
        assert "2023-01-03" in s
        assert "2023-01-31" in s


class TestProviderCapabilities:
    """Tests for ProviderCapabilities descriptor."""

    def _make(self, **kw: object) -> ProviderCapabilities:
        defaults: dict[str, object] = {
            "provider_id": "test",
            "display_name": "Test Provider",
            "point_in_time_guaranteed": True,
            "pit_limitation_description": "",
            "supported_exchanges": frozenset(Exchange),
            "supported_asset_classes": frozenset(AssetClass),
            "data_delay_minutes": 0,
            "max_history_years": 10,
            "requires_authentication": False,
            "supports_real_time": False,
        }
        defaults.update(kw)
        return ProviderCapabilities(**defaults)  # type: ignore[arg-type]

    def test_creates_valid_capabilities(self) -> None:
        caps = self._make()
        assert caps.provider_id == "test"

    def test_empty_provider_id_raises(self) -> None:
        with pytest.raises(ValueError, match="provider_id cannot be empty"):
            self._make(provider_id="")

    def test_empty_display_name_raises(self) -> None:
        with pytest.raises(ValueError, match="display_name cannot be empty"):
            self._make(display_name="")

    def test_negative_delay_raises(self) -> None:
        with pytest.raises(ValueError, match="data_delay_minutes cannot be negative"):
            self._make(data_delay_minutes=-1)

    def test_zero_max_history_raises(self) -> None:
        with pytest.raises(ValueError, match="max_history_years must be positive"):
            self._make(max_history_years=0)

    def test_none_max_history_is_valid(self) -> None:
        caps = self._make(max_history_years=None)
        assert caps.max_history_years is None

    def test_non_pit_without_description_raises(self) -> None:
        with pytest.raises(ValueError, match="pit_limitation_description is required"):
            self._make(point_in_time_guaranteed=False, pit_limitation_description="")

    def test_non_pit_with_description_is_valid(self) -> None:
        caps = self._make(
            point_in_time_guaranteed=False,
            pit_limitation_description="Data may be restated retroactively.",
        )
        assert not caps.point_in_time_guaranteed

    def test_supports_exchange_with_full_set(self) -> None:
        caps = self._make(supported_exchanges=frozenset(Exchange))
        assert caps.supports_exchange(Exchange.NYSE)
        assert caps.supports_exchange(Exchange.LSE)

    def test_supports_exchange_with_empty_set_means_all(self) -> None:
        caps = self._make(supported_exchanges=frozenset())
        assert caps.supports_exchange(Exchange.NYSE)

    def test_supports_exchange_with_restricted_set(self) -> None:
        caps = self._make(supported_exchanges=frozenset({Exchange.NYSE}))
        assert caps.supports_exchange(Exchange.NYSE)
        assert not caps.supports_exchange(Exchange.LSE)

    def test_can_serve_checks_both_exchange_and_class(self) -> None:
        caps = self._make(
            supported_exchanges=frozenset({Exchange.NASDAQ}),
            supported_asset_classes=frozenset({AssetClass.STOCK}),
        )
        stock_req = OHLCVRequest(asset=AAPL, start=T0, end=T1, as_of=AS_OF)
        assert caps.can_serve(stock_req)

    def test_can_serve_fails_wrong_exchange(self) -> None:
        caps = self._make(
            supported_exchanges=frozenset({Exchange.NYSE}),
        )
        nasdaq_req = OHLCVRequest(asset=AAPL, start=T0, end=T1, as_of=AS_OF)
        assert not caps.can_serve(nasdaq_req)

    def test_to_metadata_dict_contains_required_keys(self) -> None:
        caps = self._make()
        meta = caps.to_metadata_dict()
        for key in (
            "provider_id",
            "name",
            "point_in_time_guaranteed",
            "pit_limitation_description",
            "data_delay_minutes",
            "requires_authentication",
        ):
            assert key in meta, f"Missing key: {key}"

    def test_is_immutable(self) -> None:
        caps = self._make()
        with pytest.raises(FrozenInstanceError):
            caps.provider_id = "tampered"  # type: ignore[misc]


class TestAssetMetadata:
    """Tests for AssetMetadata value object."""

    def _make(self, **kw: object) -> AssetMetadata:
        defaults: dict[str, object] = {
            "symbol": "AAPL",
            "exchange": Exchange.NASDAQ,
            "name": "Apple Inc.",
            "asset_class": AssetClass.STOCK,
            "currency": "USD",
            "sector": "Technology",
            "country": "US",
            "is_active": True,
            "retrieved_at": datetime(2023, 1, 1, tzinfo=UTC),
        }
        defaults.update(kw)
        return AssetMetadata(**defaults)  # type: ignore[arg-type]

    def test_creates_valid_metadata(self) -> None:
        meta = self._make()
        assert meta.symbol == "AAPL"

    def test_empty_symbol_raises(self) -> None:
        with pytest.raises(ValueError, match="symbol cannot be empty"):
            self._make(symbol="")

    def test_empty_currency_raises(self) -> None:
        with pytest.raises(ValueError, match="currency cannot be empty"):
            self._make(currency="")

    def test_naive_retrieved_at_raises(self) -> None:
        with pytest.raises(ValueError, match="retrieved_at must be timezone-aware"):
            self._make(retrieved_at=datetime(2023, 1, 1))

    def test_to_asset_produces_valid_asset(self) -> None:
        meta = self._make()
        asset = meta.to_asset()
        assert isinstance(asset, Asset)
        assert asset.symbol == "AAPL"
        assert asset.exchange == Exchange.NASDAQ
        assert asset.asset_class == AssetClass.STOCK

    def test_is_immutable(self) -> None:
        meta = self._make()
        with pytest.raises(FrozenInstanceError):
            meta.symbol = "MSFT"  # type: ignore[misc]

    def test_str_representation(self) -> None:
        meta = self._make()
        s = str(meta)
        assert "AAPL" in s
        assert "NASDAQ" in s

    def test_inactive_asset(self) -> None:
        meta = self._make(is_active=False)
        assert not meta.is_active
        s = str(meta)
        assert "inactive" in s

    def test_default_retrieved_at_is_utc_aware(self) -> None:
        # No retrieved_at supplied → default_factory kicks in
        meta = AssetMetadata(
            symbol="MSFT",
            exchange=Exchange.NASDAQ,
            name="Microsoft",
            asset_class=AssetClass.STOCK,
            currency="USD",
            sector="",
            country="US",
            is_active=True,
        )
        assert meta.retrieved_at.tzinfo is not None
