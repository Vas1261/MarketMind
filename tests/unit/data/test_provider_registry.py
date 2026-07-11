"""
Unit tests for marketmind.data.providers.registry

Tests provider registration, resolution by name, settings-driven
resolution, and error paths.

Important: every test that mutates the registry must restore it afterward.
We use a fixture that saves and restores the registry state so tests
do not interfere with each other or with the auto-registered MockProvider.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.domain.market_data import OHLCVDataset
from marketmind.core.exceptions import ConfigurationError, InvalidTickerError
from marketmind.data.providers.base import BaseMarketDataProvider
from marketmind.data.providers.models import (
    AssetMetadata,
    OHLCVRequest,
    ProviderCapabilities,
)
from marketmind.data.providers.registry import ProviderRegistry

if TYPE_CHECKING:
    from collections.abc import Generator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def clean_registry() -> Generator[None, None, None]:
    """
    Save the registry state before a test and restore it afterward.

    Tests that need to call register() or clear() must use this fixture
    to avoid poisoning subsequent tests.
    """
    saved = dict(ProviderRegistry._registry)
    yield
    ProviderRegistry._registry.clear()
    ProviderRegistry._registry.update(saved)


class _StubProvider(BaseMarketDataProvider):
    """Minimal concrete provider for registry tests."""

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id="stub",
            display_name="Stub",
            point_in_time_guaranteed=True,
            pit_limitation_description="",
            supported_exchanges=frozenset(Exchange),
            supported_asset_classes=frozenset(AssetClass),
            data_delay_minutes=0,
            max_history_years=None,
            requires_authentication=False,
            supports_real_time=False,
        )

    def _fetch_ohlcv_impl(self, request: OHLCVRequest) -> OHLCVDataset:
        return OHLCVDataset(
            symbol=request.asset.symbol,
            exchange=request.asset.exchange.value,
            provider="stub",
            as_of=request.as_of,
            bars=[],
        )

    def _list_symbols_impl(self, exchange: str) -> list[str]:
        return []

    def fetch_asset_metadata(self, symbol: str, exchange: str) -> AssetMetadata:
        raise InvalidTickerError(symbol=symbol, exchange=exchange)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProviderRegistryDefaultState:
    """Tests for the state after module import (mock is auto-registered)."""

    def test_mock_is_registered_by_default(self) -> None:
        assert ProviderRegistry.is_registered("mock")

    def test_available_includes_mock(self) -> None:
        assert "mock" in ProviderRegistry.available()

    def test_get_mock_returns_mock_provider(self) -> None:
        from marketmind.data.providers.mock import MockProvider

        provider = ProviderRegistry.get("mock")
        assert isinstance(provider, MockProvider)


class TestProviderRegistryRegistration:
    """Tests for the register() method."""

    def test_register_new_provider(self, clean_registry: None) -> None:
        ProviderRegistry.register("stub", _StubProvider)
        assert ProviderRegistry.is_registered("stub")

    def test_get_registered_provider(self, clean_registry: None) -> None:
        ProviderRegistry.register("stub", _StubProvider)
        provider = ProviderRegistry.get("stub")
        assert isinstance(provider, _StubProvider)

    def test_empty_name_raises(self, clean_registry: None) -> None:
        with pytest.raises(ConfigurationError, match="cannot be empty"):
            ProviderRegistry.register("", _StubProvider)

    def test_uppercase_name_raises(self, clean_registry: None) -> None:
        with pytest.raises(ConfigurationError, match="must be lowercase"):
            ProviderRegistry.register("Stub", _StubProvider)

    def test_non_provider_class_raises(self, clean_registry: None) -> None:
        with pytest.raises(TypeError, match="subclass of BaseMarketDataProvider"):
            ProviderRegistry.register("bad", object)  # type: ignore[arg-type]

    def test_re_registration_overwrites(self, clean_registry: None) -> None:
        ProviderRegistry.register("stub", _StubProvider)
        ProviderRegistry.register("stub", _StubProvider)  # should not raise
        assert ProviderRegistry.is_registered("stub")

    def test_available_is_sorted(self, clean_registry: None) -> None:
        ProviderRegistry.register("zebra_provider", _StubProvider)
        available = ProviderRegistry.available()
        assert available == sorted(available)


class TestProviderRegistryGet:
    """Tests for the get() method."""

    def test_unknown_provider_raises_configuration_error(self) -> None:
        with pytest.raises(ConfigurationError, match="No provider registered"):
            ProviderRegistry.get("nonexistent")

    def test_error_message_lists_available(self) -> None:
        with pytest.raises(ConfigurationError, match="mock"):
            ProviderRegistry.get("totally_unknown")

    def test_get_creates_fresh_instance_each_call(self) -> None:
        p1 = ProviderRegistry.get("mock")
        p2 = ProviderRegistry.get("mock")
        assert p1 is not p2

    def test_kwargs_passed_to_constructor(self) -> None:
        from marketmind.data.providers.mock import MockProvider

        provider = ProviderRegistry.get("mock", fail_symbols={"AAPL"})
        assert isinstance(provider, MockProvider)
        # Verify the kwarg was accepted (AAPL should fail)
        aapl = Asset(symbol="AAPL", exchange=Exchange.NASDAQ, asset_class=AssetClass.STOCK)
        from marketmind.core.exceptions import InvalidTickerError

        with pytest.raises(InvalidTickerError):
            provider.fetch_ohlcv(
                aapl,
                datetime(2023, 1, 3, tzinfo=UTC),
                datetime(2023, 1, 31, tzinfo=UTC),
                datetime(2023, 2, 1, tzinfo=UTC),
            )


class TestProviderRegistryClear:
    """Tests for the clear() method (test isolation utility)."""

    def test_clear_removes_all_providers(self, clean_registry: None) -> None:
        ProviderRegistry.clear()
        assert ProviderRegistry.available() == []

    def test_is_registered_returns_false_after_clear(self, clean_registry: None) -> None:
        ProviderRegistry.clear()
        assert not ProviderRegistry.is_registered("mock")


class TestProviderRegistryGetFromSettings:
    """Tests for settings-driven provider resolution."""

    def test_returns_mock_provider_in_test_environment(self) -> None:
        # test.yaml sets providers.primary = mock
        from marketmind.data.providers.mock import MockProvider

        provider = ProviderRegistry.get_from_settings()
        assert isinstance(provider, MockProvider)

    def test_falls_back_when_primary_not_registered(self, clean_registry: None) -> None:
        # Register only the fallback (mock), not the primary
        ProviderRegistry.register("mock", _StubProvider)
        # Settings primary=mock, fallback=mock in test env → both resolve to mock
        provider = ProviderRegistry.get_from_settings()
        assert isinstance(provider, _StubProvider)

    def test_raises_when_neither_primary_nor_fallback_registered(
        self, clean_registry: None
    ) -> None:
        ProviderRegistry.clear()
        with pytest.raises(ConfigurationError, match="Neither primary provider"):
            ProviderRegistry.get_from_settings()
