"""
Unit tests for marketmind.core.domain.market_data

Tests all invariants of OHLCVBar, OHLCVDataset, DataQualityScore,
and DataQualityLevel. Pure domain tests with no I/O.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from marketmind.core.domain.market_data import (
    DataQualityLevel,
    DataQualityScore,
    OHLCVBar,
    OHLCVDataset,
    ValidationRuleResult,
)


class TestOHLCVBar:
    """Tests for the OHLCVBar value object."""

    def _make_bar(self, **kwargs) -> OHLCVBar:  # type: ignore[no-untyped-def]
        defaults = {
            "timestamp": datetime(2023, 1, 3, 21, 0, tzinfo=UTC),
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1_000_000.0,
        }
        defaults.update(kwargs)
        return OHLCVBar(**defaults)

    def test_creates_valid_bar(self) -> None:
        bar = self._make_bar()
        assert bar.close == 105.0

    def test_negative_close_raises(self) -> None:
        with pytest.raises(ValueError, match="'close' must be positive"):
            self._make_bar(close=-1.0)

    def test_zero_open_raises(self) -> None:
        with pytest.raises(ValueError, match="'open' must be positive"):
            self._make_bar(open=0.0)

    def test_negative_volume_raises(self) -> None:
        with pytest.raises(ValueError, match="Volume must be non-negative"):
            self._make_bar(volume=-1.0)

    def test_zero_volume_is_valid(self) -> None:
        bar = self._make_bar(volume=0.0)
        assert bar.volume == 0.0

    def test_price_relationship_violated_close_above_high(self) -> None:
        with pytest.raises(ValueError, match="Price relationship violated"):
            self._make_bar(high=100.0, close=101.0)

    def test_price_relationship_violated_open_below_low(self) -> None:
        with pytest.raises(ValueError, match="Price relationship violated"):
            self._make_bar(low=100.0, open=99.0, close=105.0, high=110.0)

    def test_high_equals_low_is_valid(self) -> None:
        bar = self._make_bar(open=100.0, high=100.0, low=100.0, close=100.0)
        assert bar.high == bar.low

    def test_bar_is_immutable(self) -> None:
        bar = self._make_bar()
        with pytest.raises(FrozenInstanceError):
            bar.close = 999.0  # type: ignore[misc]


class TestOHLCVDataset:
    """Tests for OHLCVDataset ordering and as_of enforcement."""

    def _make_bar(self, day: int, close: float = 100.0) -> OHLCVBar:
        return OHLCVBar(
            timestamp=datetime(2023, 1, day, 21, 0, tzinfo=UTC),
            open=close - 1,
            high=close + 2,
            low=close - 2,
            close=close,
            volume=1_000_000.0,
        )

    def test_creates_valid_dataset(self) -> None:
        bars = [self._make_bar(3), self._make_bar(4)]
        ds = OHLCVDataset(
            symbol="AAPL",
            exchange="NASDAQ",
            provider="mock",
            as_of=datetime(2023, 1, 10, 21, 0, tzinfo=UTC),
            bars=bars,
        )
        assert ds.row_count == 2
        assert ds.symbol == "AAPL"

    def test_empty_dataset_is_valid(self) -> None:
        ds = OHLCVDataset(
            symbol="AAPL",
            exchange="NASDAQ",
            provider="mock",
            as_of=datetime(2023, 1, 10, 21, 0, tzinfo=UTC),
        )
        assert ds.is_empty()
        assert ds.row_count == 0
        assert ds.date_start is None
        assert ds.date_end is None

    def test_unordered_bars_raise(self) -> None:
        bars = [self._make_bar(5), self._make_bar(3)]
        with pytest.raises(ValueError, match="strictly ascending"):
            OHLCVDataset(
                symbol="AAPL",
                exchange="NASDAQ",
                provider="mock",
                as_of=datetime(2023, 1, 10, 21, 0, tzinfo=UTC),
                bars=bars,
            )

    def test_duplicate_timestamp_raises(self) -> None:
        bars = [self._make_bar(3), self._make_bar(3)]
        with pytest.raises(ValueError, match="strictly ascending"):
            OHLCVDataset(
                symbol="AAPL",
                exchange="NASDAQ",
                provider="mock",
                as_of=datetime(2023, 1, 10, 21, 0, tzinfo=UTC),
                bars=bars,
            )

    def test_bar_after_as_of_raises(self) -> None:
        """
        This is the most important test in the data layer.
        A bar timestamped after as_of would introduce look-ahead bias.
        """
        bar_future = self._make_bar(20)
        with pytest.raises(ValueError, match="look-ahead bias"):
            OHLCVDataset(
                symbol="AAPL",
                exchange="NASDAQ",
                provider="mock",
                as_of=datetime(2023, 1, 15, 21, 0, tzinfo=UTC),
                bars=[bar_future],
            )

    def test_date_start_and_end(self) -> None:
        bars = [self._make_bar(3), self._make_bar(4), self._make_bar(5)]
        ds = OHLCVDataset(
            symbol="AAPL",
            exchange="NASDAQ",
            provider="mock",
            as_of=datetime(2023, 1, 10, 21, 0, tzinfo=UTC),
            bars=bars,
        )
        assert ds.date_start == datetime(2023, 1, 3, 21, 0, tzinfo=UTC)
        assert ds.date_end == datetime(2023, 1, 5, 21, 0, tzinfo=UTC)


class TestDataQualityLevel:
    """Tests for DataQualityLevel.from_score thresholds."""

    def test_excellent(self) -> None:
        assert DataQualityLevel.from_score(0.98) == DataQualityLevel.EXCELLENT
        assert DataQualityLevel.from_score(0.95) == DataQualityLevel.EXCELLENT

    def test_good(self) -> None:
        assert DataQualityLevel.from_score(0.90) == DataQualityLevel.GOOD
        assert DataQualityLevel.from_score(0.85) == DataQualityLevel.GOOD

    def test_acceptable(self) -> None:
        assert DataQualityLevel.from_score(0.80) == DataQualityLevel.ACCEPTABLE
        assert DataQualityLevel.from_score(0.75) == DataQualityLevel.ACCEPTABLE

    def test_poor(self) -> None:
        assert DataQualityLevel.from_score(0.70) == DataQualityLevel.POOR
        assert DataQualityLevel.from_score(0.60) == DataQualityLevel.POOR

    def test_unacceptable(self) -> None:
        assert DataQualityLevel.from_score(0.59) == DataQualityLevel.UNACCEPTABLE
        assert DataQualityLevel.from_score(0.0) == DataQualityLevel.UNACCEPTABLE


class TestDataQualityScore:
    """Tests for DataQualityScore gating logic."""

    def _make_result(self, passed: bool, severity: str = "warning") -> ValidationRuleResult:
        return ValidationRuleResult(
            rule_name="test_rule",
            passed=passed,
            severity=severity,
            message="test",
        )

    def test_creates_valid_score(self) -> None:
        score = DataQualityScore(
            symbol="AAPL",
            score=0.92,
            level=DataQualityLevel.EXCELLENT,
            rule_results=(self._make_result(True),),
            dataset_hash="abc123",
            computed_at=datetime(2023, 1, 3, tzinfo=UTC),
        )
        assert score.score == 0.92
        assert not score.is_blocked

    def test_score_above_1_raises(self) -> None:
        with pytest.raises(ValueError, match=r"\[0\.0, 1\.0\]"):
            DataQualityScore(
                symbol="AAPL",
                score=1.01,
                level=DataQualityLevel.EXCELLENT,
                rule_results=(),
                dataset_hash="x",
                computed_at=datetime(2023, 1, 3, tzinfo=UTC),
            )

    def test_failed_error_rule_blocks_pipeline(self) -> None:
        error_fail = self._make_result(passed=False, severity="error")
        score = DataQualityScore(
            symbol="AAPL",
            score=0.50,
            level=DataQualityLevel.UNACCEPTABLE,
            rule_results=(error_fail,),
            dataset_hash="abc",
            computed_at=datetime(2023, 1, 3, tzinfo=UTC),
        )
        assert score.is_blocked
        assert len(score.failed_error_rules) == 1

    def test_failed_warning_rule_does_not_block(self) -> None:
        warning_fail = self._make_result(passed=False, severity="warning")
        score = DataQualityScore(
            symbol="AAPL",
            score=0.80,
            level=DataQualityLevel.ACCEPTABLE,
            rule_results=(warning_fail,),
            dataset_hash="abc",
            computed_at=datetime(2023, 1, 3, tzinfo=UTC),
        )
        assert not score.is_blocked
        assert len(score.failed_rules) == 1
        assert len(score.failed_error_rules) == 0

    def test_passed_and_failed_rule_split(self) -> None:
        results = (
            self._make_result(True),
            self._make_result(True),
            self._make_result(False),
        )
        score = DataQualityScore(
            symbol="AAPL",
            score=0.80,
            level=DataQualityLevel.ACCEPTABLE,
            rule_results=results,
            dataset_hash="abc",
            computed_at=datetime(2023, 1, 3, tzinfo=UTC),
        )
        assert len(score.passed_rules) == 2
        assert len(score.failed_rules) == 1
