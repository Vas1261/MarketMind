"""
Integration test: application startup chain.

Verifies that the full import -> configuration -> logging -> domain chain
works without errors.
"""

from __future__ import annotations


def test_package_imports_cleanly() -> None:
    """The root marketmind package must be importable."""
    import marketmind

    assert marketmind.__version__ == "0.1.0"


def test_core_domain_imports_cleanly() -> None:
    """All core domain objects must be importable from the public API."""
    from marketmind.core import (
        Asset,
        AssetClass,
        DataQualityLevel,
        DataQualityScore,
        Experiment,
        ExperimentStatus,
        KillCriteria,
        MarketRegime,
        OHLCVBar,
        OHLCVDataset,
        PreRegistration,
        Universe,
    )

    assert Asset is not None
    assert AssetClass is not None
    assert DataQualityLevel is not None
    assert DataQualityScore is not None
    assert Experiment is not None
    assert ExperimentStatus is not None
    assert KillCriteria is not None
    assert MarketRegime is not None
    assert OHLCVBar is not None
    assert OHLCVDataset is not None
    assert PreRegistration is not None
    assert Universe is not None


def test_exceptions_import_cleanly() -> None:
    """All exceptions must be importable and form the correct hierarchy."""
    from marketmind.core.exceptions import (
        DataIntegrityError,
        DataQualityGateError,
        ExperimentStateError,
        LeakageError,
        MarketMindError,
        ModelNotFittedError,
        SealedDatasetViolationError,
    )

    assert issubclass(DataIntegrityError, MarketMindError)
    assert issubclass(DataQualityGateError, MarketMindError)
    assert issubclass(ExperimentStateError, MarketMindError)
    assert issubclass(LeakageError, MarketMindError)
    assert issubclass(ModelNotFittedError, MarketMindError)
    assert issubclass(SealedDatasetViolationError, MarketMindError)


def test_config_loads_in_test_environment() -> None:
    """Settings must load cleanly in the test environment."""
    from marketmind.config import clear_settings_cache, get_settings

    clear_settings_cache()
    settings = get_settings()
    assert settings.environment == "test"
    clear_settings_cache()


def test_logging_initialises_without_error() -> None:
    """Logging framework must initialise without raising."""
    from marketmind.logging import configure_logging, get_logger

    configure_logging(level="WARNING", fmt="console")
    log = get_logger("integration_test")
    log.info("integration_test_running")


def test_data_quality_gate_error_carries_context() -> None:
    """DataQualityGateError should carry symbol, score, and threshold."""
    from marketmind.core.exceptions import DataQualityGateError

    err = DataQualityGateError(score=0.62, threshold=0.75, symbol="AAPL")
    assert "AAPL" in str(err)
    assert err.score == 0.62
    assert err.threshold == 0.75
    assert err.symbol == "AAPL"


def test_placeholder_modules_importable() -> None:
    """All Phase 2+ placeholder packages must be importable without errors."""
    import marketmind.data
    import marketmind.evaluation
    import marketmind.explainability
    import marketmind.features
    import marketmind.models
    import marketmind.monitoring
    import marketmind.recommendation
    import marketmind.regime
    import marketmind.research
    import marketmind.scheduler

    # Verify they are real modules, not None
    assert marketmind.data is not None
    assert marketmind.evaluation is not None
    assert marketmind.features is not None
    assert marketmind.models is not None
