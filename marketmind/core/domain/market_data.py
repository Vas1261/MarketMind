"""
Market Data Domain Objects
==========================

Value objects representing validated market data and data quality.

These objects are what the rest of the system operates on. Raw data from
providers is never passed further than the validation boundary — everything
downstream receives OHLCVDataset or DataQualityScore, never raw dicts or
untyped DataFrames.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class DataQualityLevel(StrEnum):
    """
    Qualitative interpretation of a DataQualityScore.

    The numeric score is the authoritative value; this level is derived
    from it for human display and alert triggering.
    """

    EXCELLENT = "EXCELLENT"  # ≥ 0.95
    GOOD = "GOOD"  # ≥ 0.85
    ACCEPTABLE = "ACCEPTABLE"  # ≥ 0.75 (gate threshold)
    POOR = "POOR"  # ≥ 0.60
    UNACCEPTABLE = "UNACCEPTABLE"  # < 0.60  → predictions blocked

    @classmethod
    def from_score(cls, score: float) -> DataQualityLevel:
        if score >= 0.95:
            return cls.EXCELLENT
        if score >= 0.85:
            return cls.GOOD
        if score >= 0.75:
            return cls.ACCEPTABLE
        if score >= 0.60:
            return cls.POOR
        return cls.UNACCEPTABLE


@dataclass(frozen=True)
class ValidationRuleResult:
    """
    The outcome of a single validation rule applied to a dataset.

    Attributes
    ----------
    rule_name:
        Identifier of the rule that produced this result.
    passed:
        True if the dataset passed this rule.
    severity:
        "error" rules that fail block the dataset.
        "warning" rules that fail reduce the quality score but do not block.
    message:
        Human-readable explanation of the result.
    affected_rows:
        Number of rows affected by the issue (0 if passed).
    """

    rule_name: str
    passed: bool
    severity: str  # "error" | "warning"
    message: str
    affected_rows: int = 0

    def __post_init__(self) -> None:
        if self.severity not in ("error", "warning"):
            raise ValueError(f"severity must be 'error' or 'warning', got {self.severity!r}")
        if self.affected_rows < 0:
            raise ValueError("affected_rows cannot be negative.")


@dataclass(frozen=True)
class DataQualityScore:
    """
    The aggregated quality assessment of a single validated dataset.

    This is the output of the ValidationEngine and the gating signal
    for the prediction pipeline.

    Attributes
    ----------
    symbol:
        The asset ticker this score relates to.
    score:
        Numeric quality score in [0.0, 1.0]. Higher is better.
    level:
        Qualitative interpretation derived from score.
    rule_results:
        Per-rule breakdown. Enables users to see exactly which rules
        passed or failed, and what the data issues were.
    dataset_hash:
        Content hash of the validated dataset. Links this score to
        the exact data version it was computed on.
    computed_at:
        UTC timestamp when this score was computed.
    """

    symbol: str
    score: float
    level: DataQualityLevel
    rule_results: tuple[ValidationRuleResult, ...]
    dataset_hash: str
    computed_at: datetime

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"DataQualityScore must be in [0.0, 1.0], got {self.score}")

    @property
    def passed_rules(self) -> list[ValidationRuleResult]:
        return [r for r in self.rule_results if r.passed]

    @property
    def failed_rules(self) -> list[ValidationRuleResult]:
        return [r for r in self.rule_results if not r.passed]

    @property
    def failed_error_rules(self) -> list[ValidationRuleResult]:
        """Rules with severity='error' that failed. These block the pipeline."""
        return [r for r in self.rule_results if not r.passed and r.severity == "error"]

    @property
    def is_blocked(self) -> bool:
        """True if any error-severity rule failed. Prediction must be blocked."""
        return len(self.failed_error_rules) > 0

    def __str__(self) -> str:
        return (
            f"DataQualityScore({self.symbol}: {self.score:.3f} [{self.level.value}]"
            f", blocked={self.is_blocked})"
        )


@dataclass(frozen=True)
class OHLCVBar:
    """
    A single OHLCV bar for one asset on one trading day.

    All prices are in the asset's native currency, adjusted for splits
    and dividends (total return basis).

    Attributes
    ----------
    timestamp:
        UTC close timestamp of the bar.
    open, high, low, close:
        Adjusted prices. All must be positive.
    volume:
        Number of shares/units traded. Must be non-negative.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        for price_name, price_val in [
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ]:
            if price_val <= 0:
                raise ValueError(f"Price field '{price_name}' must be positive, got {price_val}")
        if self.volume < 0:
            raise ValueError(f"Volume must be non-negative, got {self.volume}")
        if not (self.low <= self.open <= self.high and self.low <= self.close <= self.high):
            raise ValueError(
                f"Price relationship violated: low={self.low}, open={self.open}, "
                f"close={self.close}, high={self.high}"
            )


@dataclass
class OHLCVDataset:
    """
    A validated, versioned collection of OHLCV bars for a single asset.

    This is the canonical data type that crosses the validation boundary.
    Everything downstream receives an OHLCVDataset — never a raw DataFrame
    or untyped dict. This makes leakage detectable at the type level.

    The `as_of` field is the point-in-time boundary. Any bar with
    timestamp > as_of is a violation and must be rejected by the provider.

    Attributes
    ----------
    symbol:
        Asset ticker.
    exchange:
        Primary listing exchange.
    provider:
        Name of the data provider that sourced this data.
    as_of:
        The point-in-time boundary. No bar may have timestamp > as_of.
    bars:
        Time-ordered sequence of validated OHLCV bars.
    dataset_hash:
        SHA-256 content hash. Set by the DatasetRegistry after persisting.
    quality_score:
        Set by the ValidationEngine after validation passes.
    schema_version:
        Version of the OHLCVDataset schema. Used for forward compatibility.
    """

    symbol: str
    exchange: str
    provider: str
    as_of: datetime
    bars: list[OHLCVBar] = field(default_factory=list)
    dataset_hash: str = ""
    quality_score: DataQualityScore | None = None
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        # Verify temporal ordering
        for i in range(1, len(self.bars)):
            if self.bars[i].timestamp <= self.bars[i - 1].timestamp:
                raise ValueError(
                    f"OHLCV bars must be in strictly ascending timestamp order. "
                    f"Bar {i} timestamp {self.bars[i].timestamp} is not after "
                    f"bar {i - 1} timestamp {self.bars[i - 1].timestamp}."
                )

        # Verify as_of boundary
        for bar in self.bars:
            if bar.timestamp > self.as_of:
                raise ValueError(
                    f"Data integrity violation: bar timestamp {bar.timestamp} "
                    f"exceeds as_of boundary {self.as_of}. "
                    f"This would introduce look-ahead bias."
                )

    @property
    def row_count(self) -> int:
        return len(self.bars)

    @property
    def date_start(self) -> datetime | None:
        return self.bars[0].timestamp if self.bars else None

    @property
    def date_end(self) -> datetime | None:
        return self.bars[-1].timestamp if self.bars else None

    def is_empty(self) -> bool:
        return len(self.bars) == 0

    def __str__(self) -> str:
        return (
            f"OHLCVDataset({self.symbol} via {self.provider}, "
            f"{self.row_count} bars, "
            f"{self.date_start} → {self.date_end}, "
            f"as_of={self.as_of})"
        )
