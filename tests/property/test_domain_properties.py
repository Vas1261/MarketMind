"""
Property-based tests for core domain objects.

Uses the Hypothesis library to generate arbitrary inputs and verify
that domain invariants hold regardless of specific values.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.domain.market_data import DataQualityLevel, OHLCVBar


class TestOHLCVBarProperties:
    """Property-based tests for OHLCVBar invariants."""

    @given(
        price=st.floats(min_value=0.01, max_value=100_000.0, allow_nan=False),
        spread=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
        volume=st.floats(min_value=0.0, max_value=1e12, allow_nan=False),
    )
    def test_valid_ohlcv_bar_never_raises(self, price: float, spread: float, volume: float) -> None:
        """Any valid combination of prices should construct without error."""
        low = max(0.01, price - spread)
        high = price + spread
        bar = OHLCVBar(
            timestamp=datetime(2023, 1, 3, 21, 0, tzinfo=UTC),
            open=price,
            high=high,
            low=low,
            close=price,
            volume=volume,
        )
        assert bar.low <= bar.close <= bar.high

    @given(
        price=st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
    )
    def test_non_positive_close_always_raises(self, price: float) -> None:
        """Non-positive close price must always be rejected."""
        assume(price <= 0.0)
        with pytest.raises(ValueError, match="must be positive"):
            OHLCVBar(
                timestamp=datetime(2023, 1, 3, 21, 0, tzinfo=UTC),
                open=max(1.0, abs(price) + 0.01),
                high=max(2.0, abs(price) + 0.02),
                low=0.01,
                close=price,
                volume=1_000_000.0,
            )


class TestDataQualityLevelProperties:
    """Property-based tests for DataQualityLevel.from_score."""

    @given(score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False))
    def test_from_score_always_returns_a_level(self, score: float) -> None:
        """from_score must return a valid level for any score in [0, 1]."""
        level = DataQualityLevel.from_score(score)
        assert isinstance(level, DataQualityLevel)

    @given(
        s1=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        s2=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )
    @settings(max_examples=200)
    def test_higher_score_never_gives_lower_level(self, s1: float, s2: float) -> None:
        """Ordering invariant: if s1 > s2, level(s1) should be >= level(s2)."""
        assume(s1 > s2)
        level_order = [
            DataQualityLevel.UNACCEPTABLE,
            DataQualityLevel.POOR,
            DataQualityLevel.ACCEPTABLE,
            DataQualityLevel.GOOD,
            DataQualityLevel.EXCELLENT,
        ]
        l1 = DataQualityLevel.from_score(s1)
        l2 = DataQualityLevel.from_score(s2)
        assert level_order.index(l1) >= level_order.index(l2)


class TestAssetProperties:
    """Property-based tests for Asset invariants."""

    @given(
        symbol=st.text(
            alphabet=st.characters(whitelist_categories=("Lu",)),
            min_size=1,
            max_size=10,
        )
    )
    def test_uppercase_symbol_always_accepted(self, symbol: str) -> None:
        """Any non-empty uppercase alphabetic symbol should be valid."""
        asset = Asset(
            symbol=symbol,
            exchange=Exchange.NYSE,
            asset_class=AssetClass.STOCK,
        )
        assert asset.symbol == symbol.upper()

    @given(
        symbol=st.text(
            alphabet=st.characters(whitelist_categories=("Lu",)),
            min_size=1,
            max_size=10,
        )
    )
    def test_uid_always_contains_symbol(self, symbol: str) -> None:
        """UID must always contain the symbol."""
        asset = Asset(
            symbol=symbol,
            exchange=Exchange.NYSE,
            asset_class=AssetClass.STOCK,
        )
        assert asset.symbol in asset.uid
