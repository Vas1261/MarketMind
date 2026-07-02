"""
Market Regime Domain Objects
=============================

Value objects representing market regimes.

Regime definitions must be fixed before any experiments begin.
They are never redefined after observing results — that would convert
a classification tool into a retrospective narrative device.

Version 1 uses a simple volatility-based regime classifier:
  - HIGH_VOL: trailing realised volatility in upper tercile
  - MED_VOL:  trailing realised volatility in middle tercile
  - LOW_VOL:  trailing realised volatility in lower tercile

The specific classifier and benchmark are defined in config, not here.
These objects carry the result of that classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


class MarketRegime(StrEnum):
    """
    Market regime labels.

    Definitions are deliberately simple and objective. Subjective labels
    like "bull" and "bear" are avoided because they require post-hoc
    knowledge about where a trend ended.

    Volatility terciles computed on a rolling basis are observable in
    real time without future information.
    """

    LOW_VOL = "LOW_VOL"  # Trailing realised vol in lower tercile
    MED_VOL = "MED_VOL"  # Trailing realised vol in middle tercile
    HIGH_VOL = "HIGH_VOL"  # Trailing realised vol in upper tercile
    UNKNOWN = "UNKNOWN"  # Regime cannot be determined (insufficient data)


@dataclass(frozen=True)
class RegimeClassification:
    """
    A single regime classification for a specific date.

    Attributes
    ----------
    date:
        The trading date this classification applies to.
    regime:
        The regime label.
    benchmark_symbol:
        The index used to compute the regime. e.g. "SPY"
    volatility_window_days:
        Number of trading days used for realised volatility computation.
    realised_volatility:
        The annualised realised volatility value that produced this label.
    classifier_version:
        Version of the regime classifier. Must remain fixed during experiments.
    """

    date: datetime
    regime: MarketRegime
    benchmark_symbol: str
    volatility_window_days: int
    realised_volatility: float
    classifier_version: str

    def __post_init__(self) -> None:
        if self.realised_volatility < 0:
            raise ValueError(
                f"realised_volatility cannot be negative, got {self.realised_volatility}"
            )
        if self.volatility_window_days <= 0:
            raise ValueError(
                f"volatility_window_days must be positive, got {self.volatility_window_days}"
            )
