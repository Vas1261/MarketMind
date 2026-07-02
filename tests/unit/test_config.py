"""
Unit tests for marketmind.config

Tests that Settings loads correctly, validates constraints,
and that environment isolation works in tests.
"""

from __future__ import annotations

import pytest

from marketmind.config.settings import Settings, clear_settings_cache, get_settings


class TestGetSettings:
    """Tests for the get_settings() singleton behaviour."""

    def setup_method(self) -> None:
        clear_settings_cache()

    def teardown_method(self) -> None:
        clear_settings_cache()

    def test_returns_settings_instance(self) -> None:
        s = get_settings()
        assert isinstance(s, Settings)

    def test_returns_same_instance_when_called_twice(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_test_environment_is_active(self) -> None:
        s = get_settings()
        assert s.environment == "test"

    def test_clear_cache_allows_fresh_load(self) -> None:
        s1 = get_settings()
        clear_settings_cache()
        s2 = get_settings()
        assert s1 is not s2


class TestSettingsDefaults:
    """Tests for Settings default values and validation."""

    def setup_method(self) -> None:
        clear_settings_cache()

    def teardown_method(self) -> None:
        clear_settings_cache()

    def test_quality_gate_threshold_in_range(self) -> None:
        s = get_settings()
        assert 0.0 <= s.data.validation.quality_gate_threshold <= 1.0

    def test_outlier_sigma_positive(self) -> None:
        s = get_settings()
        assert s.data.validation.outlier_sigma > 0

    def test_database_url_is_sqlite_in_test(self) -> None:
        s = get_settings()
        assert s.database.url.startswith("sqlite")

    def test_provider_is_mock_in_test(self) -> None:
        s = get_settings()
        assert s.data.providers.primary == "mock"

    def test_walk_forward_train_window_positive(self) -> None:
        s = get_settings()
        assert s.evaluation.walk_forward.train_window_years > 0

    def test_bootstrap_iterations_positive(self) -> None:
        s = get_settings()
        assert s.evaluation.bootstrap.iterations > 0

    def test_transaction_cost_round_trip_positive(self) -> None:
        s = get_settings()
        assert s.evaluation.transaction_costs.round_trip_bps > 0

    def test_min_direction_probability_above_half(self) -> None:
        s = get_settings()
        assert s.recommendation.min_direction_probability >= 0.5

    def test_invalid_environment_raises(self) -> None:
        with pytest.raises(ValueError, match="must be one of"):
            Settings(environment="invalid_env")  # type: ignore[arg-type]

    def test_invalid_provider_raises(self) -> None:
        from marketmind.config.settings import ProviderSettings

        with pytest.raises(ValueError, match="Provider must be one of"):
            ProviderSettings(primary="bloomberg")

    def test_invalid_database_url_raises(self) -> None:
        from marketmind.config.settings import DatabaseSettings

        with pytest.raises(ValueError, match="must be sqlite or postgresql"):
            DatabaseSettings(url="mysql://localhost/db")


class TestTransactionCostModel:
    """Tests for the transaction cost round-trip computation."""

    def test_round_trip_is_double_one_way(self) -> None:
        from marketmind.config.settings import TransactionCostSettings

        costs = TransactionCostSettings(
            commission_bps=5.0,
            market_impact_bps=5.0,
            spread_bps=5.0,
        )
        assert costs.round_trip_bps == 30.0

    def test_zero_costs_produce_zero_round_trip(self) -> None:
        from marketmind.config.settings import TransactionCostSettings

        costs = TransactionCostSettings(
            commission_bps=0.0,
            market_impact_bps=0.0,
            spread_bps=0.0,
        )
        assert costs.round_trip_bps == 0.0
