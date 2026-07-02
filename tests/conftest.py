"""
Root pytest conftest.py
========================

Fixtures and configuration shared across the entire test suite.

Scoping rules:
  - session-scoped fixtures: created once for the whole test run.
  - function-scoped fixtures (default): created fresh for each test.

Isolation rules:
  - Every test runs with MM_ENVIRONMENT=test.
  - Settings cache is cleared between tests that manipulate config.
  - No test writes to the production or research database.
  - No test makes network requests (mock provider in test config).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator

# Force test environment before any application code is imported
os.environ.setdefault("MM_ENVIRONMENT", "test")


# ---------------------------------------------------------------------------
# Settings & Configuration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def test_environment() -> Generator[None, None, None]:
    """Ensure MM_ENVIRONMENT=test for the entire session."""
    original = os.environ.get("MM_ENVIRONMENT")
    os.environ["MM_ENVIRONMENT"] = "test"
    yield
    if original is None:
        os.environ.pop("MM_ENVIRONMENT", None)
    else:
        os.environ["MM_ENVIRONMENT"] = original


@pytest.fixture
def settings():  # type: ignore[no-untyped-def]
    """Return test Settings, clearing the cache before and after."""
    from marketmind.config.settings import clear_settings_cache, get_settings

    clear_settings_cache()
    s = get_settings()
    yield s
    clear_settings_cache()


# ---------------------------------------------------------------------------
# Domain Object Factories
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_asset():  # type: ignore[no-untyped-def]
    """A valid Asset for use in tests."""
    from marketmind.core.domain.asset import Asset, AssetClass, Exchange

    return Asset(
        symbol="AAPL",
        exchange=Exchange.NASDAQ,
        asset_class=AssetClass.STOCK,
        name="Apple Inc.",
        sector="Information Technology",
        country="US",
    )


@pytest.fixture
def sample_ohlcv_bar():  # type: ignore[no-untyped-def]
    """A valid OHLCVBar for use in tests."""
    from marketmind.core.domain.market_data import OHLCVBar

    return OHLCVBar(
        timestamp=datetime(2023, 1, 3, 21, 0, 0, tzinfo=UTC),
        open=130.28,
        high=130.90,
        low=124.17,
        close=125.07,
        volume=112_117_500.0,
    )


@pytest.fixture
def sample_ohlcv_bars():  # type: ignore[no-untyped-def]
    """A sequence of 10 valid OHLCVBars spanning 10 trading days."""
    from marketmind.core.domain.market_data import OHLCVBar

    base_prices = [
        (130.28, 130.90, 124.17, 125.07),
        (126.89, 128.66, 126.12, 126.36),
        (127.13, 127.77, 124.76, 126.54),
        (126.01, 130.29, 125.87, 130.15),
        (130.47, 133.41, 129.89, 133.23),
        (132.03, 134.08, 131.21, 133.49),
        (133.88, 134.26, 131.44, 132.03),
        (134.13, 136.80, 133.92, 134.76),
        (135.28, 138.98, 135.02, 137.87),
        (138.05, 143.15, 137.71, 141.91),
    ]
    bars = []
    for i, (open_, high, low, close) in enumerate(base_prices):
        bars.append(
            OHLCVBar(
                timestamp=datetime(2023, 1, 3 + i, 21, 0, 0, tzinfo=UTC),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=100_000_000.0 + i * 1_000_000,
            )
        )
    return bars


@pytest.fixture
def sample_dataset(sample_ohlcv_bars):  # type: ignore[no-untyped-def]
    """A valid OHLCVDataset with 10 bars."""
    from marketmind.core.domain.market_data import OHLCVDataset

    return OHLCVDataset(
        symbol="AAPL",
        exchange="NASDAQ",
        provider="mock",
        as_of=datetime(2023, 1, 15, 21, 0, 0, tzinfo=UTC),
        bars=sample_ohlcv_bars,
    )


@pytest.fixture
def sample_pre_registration():  # type: ignore[no-untyped-def]
    """A valid PreRegistration for use in research workflow tests."""
    from marketmind.core.domain.experiment import (
        AcceptanceCriteria,
        KillCriteria,
        PreRegistration,
    )

    return PreRegistration(
        experiment_id="EXP-001",
        title="Test experiment",
        research_question="Does this feature contain signal?",
        hypothesis="H1: The feature predicts direction above persistence baseline.",
        null_hypothesis="H0: No directional accuracy above persistence baseline.",
        justification="Test justification.",
        universe_id="UNIVERSE-V1",
        dataset_version_hash="abc123",
        feature_list=("rsi_14",),
        model_type="LogisticRegression",
        model_params={"C": 1.0, "solver": "lbfgs"},
        validation_scheme="walk_forward",
        validation_params={"train_window_years": 3, "test_window_months": 6},
        acceptance_criteria=AcceptanceCriteria(
            primary_metric="deflated_sharpe_ratio",
            primary_threshold="> 0.0 at 95% CI lower bound",
        ),
        kill_criteria=KillCriteria(criteria=("Deflated Sharpe CI lower bound <= 0.0",)),
        final_validation_set_hash="sealed_xyz",
        protocol_version="1.0",
        git_commit="test_commit_abc",
        created_at=datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC),
    )
