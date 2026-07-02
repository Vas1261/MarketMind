"""
Test fixtures: sample datasets for unit and integration tests.

Provides deterministic, small datasets that are sufficient to exercise
pipeline logic without requiring network access or large files.

All data is synthetic - not intended to be realistic, only structurally
valid so tests can exercise code paths reliably.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.domain.market_data import OHLCVBar, OHLCVDataset


def make_trading_days(start: datetime, count: int) -> list[datetime]:
    """
    Generate a list of weekday timestamps starting from `start`.

    Skips Saturday (5) and Sunday (6) - approximates a trading calendar
    without exchange-specific holidays. Sufficient for unit tests.
    """
    days = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:  # Monday-Friday
            days.append(current)
        current += timedelta(days=1)
    return days


def make_synthetic_ohlcv(
    symbol: str = "AAPL",
    exchange: str = "NASDAQ",
    start_price: float = 100.0,
    bar_count: int = 252,
    start_date: datetime | None = None,
    as_of_lag_days: int = 1,
) -> OHLCVDataset:
    """
    Generate a synthetic OHLCVDataset with deterministic prices.

    Prices follow a simple random walk seeded by `start_price`.
    The walk is deterministic - the same inputs always produce the same output.

    Parameters
    ----------
    symbol:
        Ticker symbol.
    exchange:
        Exchange name.
    start_price:
        Opening price of the first bar.
    bar_count:
        Number of bars to generate.
    start_date:
        First bar date. Defaults to 2020-01-02 UTC close.
    as_of_lag_days:
        as_of is set to bar_count + as_of_lag_days trading days after start.
    """
    if start_date is None:
        start_date = datetime(2020, 1, 2, 21, 0, 0, tzinfo=UTC)

    timestamps = make_trading_days(start_date, bar_count + as_of_lag_days + 5)
    bar_timestamps = timestamps[:bar_count]
    as_of = timestamps[bar_count + as_of_lag_days - 1]

    bars = []
    price = start_price

    # Deterministic walk using a linear congruential generator
    seed = int(start_price * 1000) % (2**31)

    for ts in bar_timestamps:
        seed = (seed * 1664525 + 1013904223) % (2**32)
        change_pct = (seed / (2**32) - 0.5) * 0.04  # +/-2% daily move
        close = max(0.01, price * (1 + change_pct))

        spread_seed = (seed * 22695477 + 1) % (2**32)
        spread_pct = (spread_seed / (2**32)) * 0.01  # 0-1% spread

        high = close * (1 + spread_pct)
        low = close * (1 - spread_pct)
        open_price = max(low, min(high, price))

        vol_seed = (seed * 214013 + 2531011) % (2**32)
        volume = 500_000 + (vol_seed % 2_000_000)

        bars.append(
            OHLCVBar(
                timestamp=ts,
                open=round(open_price, 4),
                high=round(high, 4),
                low=round(low, 4),
                close=round(close, 4),
                volume=float(volume),
            )
        )
        price = close

    return OHLCVDataset(
        symbol=symbol.upper(),
        exchange=exchange,
        provider="mock",
        as_of=as_of,
        bars=bars,
    )


# ---------------------------------------------------------------------------
# Pre-built fixture instances (ready to use in tests via import)
# ---------------------------------------------------------------------------

AAPL_SMALL = make_synthetic_ohlcv(symbol="AAPL", bar_count=50, start_price=130.0)
MSFT_SMALL = make_synthetic_ohlcv(symbol="MSFT", bar_count=50, start_price=250.0)
AAPL_YEAR = make_synthetic_ohlcv(symbol="AAPL", bar_count=252, start_price=130.0)

SAMPLE_ASSET_AAPL = Asset(
    symbol="AAPL",
    exchange=Exchange.NASDAQ,
    asset_class=AssetClass.STOCK,
    name="Apple Inc.",
    sector="Information Technology",
    country="US",
)
