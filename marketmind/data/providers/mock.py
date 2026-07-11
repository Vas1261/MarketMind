"""
Mock Market Data Provider
==========================

A fully deterministic, network-free provider that returns synthetic OHLCV data.

Purpose:
  - Tests: every test that exercises the data pipeline uses this provider.
    Results are reproducible across machines and CI runs.
  - Local development: lets the pipeline run without API keys or rate limits.
  - Simulation: can be configured to raise specific errors to test error-handling paths.

Determinism guarantee:
  The same (symbol, start, end, as_of) arguments always produce the same bars.
  This is enforced by seeding a linear congruential generator (LCG) from the
  symbol name. The LCG is not cryptographically secure — it only needs to
  produce visually plausible, reproducible price series.

Synthetic data properties:
  - Prices start near a seed value derived from the symbol (100-500 range).
  - Daily returns follow a ±2 % random walk.
  - Volume varies between 500K and 2.5M shares.
  - All bars respect the OHLCV price-relationship invariant (low ≤ open,close ≤ high).
  - Weekends are skipped automatically.
  - No dividends, no splits (keep it simple for testing).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from marketmind.core.domain.asset import Asset, AssetClass, Exchange
from marketmind.core.domain.market_data import OHLCVBar, OHLCVDataset
from marketmind.core.exceptions import DataUnavailableError, InvalidTickerError
from marketmind.data.providers.base import BaseMarketDataProvider
from marketmind.data.providers.models import (
    AssetMetadata,
    OHLCVRequest,
    ProviderCapabilities,
)

# ---------------------------------------------------------------------------
# Known assets the mock provider "knows about"
# Any symbol not in this set raises InvalidTickerError.
# ---------------------------------------------------------------------------

_KNOWN_ASSETS: dict[str, AssetMetadata] = {
    "AAPL": AssetMetadata(
        symbol="AAPL",
        exchange=Exchange.NASDAQ,
        name="Apple Inc.",
        asset_class=AssetClass.STOCK,
        currency="USD",
        sector="Information Technology",
        country="US",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "MSFT": AssetMetadata(
        symbol="MSFT",
        exchange=Exchange.NASDAQ,
        name="Microsoft Corporation",
        asset_class=AssetClass.STOCK,
        currency="USD",
        sector="Information Technology",
        country="US",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "JPM": AssetMetadata(
        symbol="JPM",
        exchange=Exchange.NYSE,
        name="JPMorgan Chase & Co.",
        asset_class=AssetClass.STOCK,
        currency="USD",
        sector="Financials",
        country="US",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "RIO": AssetMetadata(
        symbol="RIO",
        exchange=Exchange.LSE,
        name="Rio Tinto Group",
        asset_class=AssetClass.STOCK,
        currency="GBP",
        sector="Materials",
        country="GB",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "SPY": AssetMetadata(
        symbol="SPY",
        exchange=Exchange.NYSE,
        name="SPDR S&P 500 ETF Trust",
        asset_class=AssetClass.ETF,
        currency="USD",
        sector="",
        country="US",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "QQQ": AssetMetadata(
        symbol="QQQ",
        exchange=Exchange.NASDAQ,
        name="Invesco QQQ Trust",
        asset_class=AssetClass.ETF,
        currency="USD",
        sector="",
        country="US",
        is_active=True,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
    "DELISTED": AssetMetadata(
        symbol="DELISTED",
        exchange=Exchange.NYSE,
        name="Delisted Corp",
        asset_class=AssetClass.STOCK,
        currency="USD",
        sector="",
        country="US",
        is_active=False,
        retrieved_at=datetime(2024, 1, 1, tzinfo=UTC),
    ),
}

# Symbols organised by exchange for list_available_symbols()
_SYMBOLS_BY_EXCHANGE: dict[str, list[str]] = {
    "NASDAQ": ["AAPL", "MSFT", "QQQ"],
    "NYSE": ["JPM", "SPY", "DELISTED"],
    "LSE": ["RIO"],
    "XETRA": [],
    "TSX": [],
    "ASX": [],
}

# ---------------------------------------------------------------------------
# MockProvider capabilities (defined once, reused)
# ---------------------------------------------------------------------------

_MOCK_CAPABILITIES = ProviderCapabilities(
    provider_id="mock",
    display_name="Mock Provider (Synthetic Data)",
    point_in_time_guaranteed=True,  # Synthetic data has no restatement
    pit_limitation_description="",  # Not needed when guaranteed
    supported_exchanges=frozenset(Exchange),  # Supports all exchanges
    supported_asset_classes=frozenset(AssetClass),  # Supports all asset classes
    data_delay_minutes=0,
    max_history_years=50,  # Arbitrary — synthetic data goes back as far as needed
    requires_authentication=False,
    supports_real_time=False,
)


# ---------------------------------------------------------------------------
# Linear Congruential Generator helpers
# ---------------------------------------------------------------------------


def _symbol_seed(symbol: str) -> int:
    """
    Derive a reproducible integer seed from a ticker symbol.

    Different symbols produce different seeds, giving each asset a unique
    but reproducible price series. The mapping is stable — adding new
    symbols to _KNOWN_ASSETS does not change existing series.
    """
    h = 0
    for ch in symbol.upper():
        h = (h * 31 + ord(ch)) % (2**32)
    return max(1, h)


def _lcg_step(seed: int) -> tuple[int, float]:
    """
    Single step of the Knuth/MMIX linear congruential generator.

    Returns (new_seed, uniform_float_in_[0,1)).
    """
    new_seed = (seed * 6364136223846793005 + 1442695040888963407) % (2**64)
    return new_seed, new_seed / (2**64)


def _seed_from_symbol_and_date(symbol: str, date: datetime) -> int:
    """
    Produce a date-specific seed to make daily returns independent.

    Combining the symbol seed with the date ensures that the bar for
    2023-01-05 is always the same regardless of which date range was
    requested — full reproducibility.
    """
    base = _symbol_seed(symbol)
    date_int = date.year * 10000 + date.month * 100 + date.day
    return (base ^ (date_int * 2654435761)) % (2**64)


def _start_price(symbol: str) -> float:
    """
    Derive a stable starting price from the symbol name.

    Produces values between 10.0 and 500.0.
    """
    seed = _symbol_seed(symbol)
    _, f = _lcg_step(seed)
    return round(10.0 + f * 490.0, 2)


def _is_weekday(dt: datetime) -> bool:
    return dt.weekday() < 5  # Monday=0 ... Friday=4


def _generate_bars(
    symbol: str,
    start: datetime,
    end: datetime,
    as_of: datetime,
) -> list[OHLCVBar]:
    """
    Generate synthetic weekday OHLCV bars for the given range.

    Algorithm:
      1. Walk from start to min(end, as_of) one calendar day at a time.
      2. Skip weekends.
      3. For each trading day, derive a per-day seed from (symbol, date).
      4. Draw a daily return ~ Uniform(-2%, +2%).
      5. Compute high/low as close ± small spread.
      6. Compute open as prev_close with tiny jitter.
      7. Draw volume ~ Uniform(500K, 2.5M).

    All generated bars satisfy OHLCVBar's price-relationship invariant.
    """
    ceiling = min(end, as_of)
    current_price = _start_price(symbol)

    # Walk from the symbol's "epoch" (2000-01-03) to start, updating price,
    # so that the price at `start` is consistent regardless of window size.
    epoch = datetime(2000, 1, 3, 21, 0, 0, tzinfo=UTC)
    walk_date = epoch
    price = _start_price(symbol)

    while walk_date < start:
        if _is_weekday(walk_date):
            day_seed = _seed_from_symbol_and_date(symbol, walk_date)
            day_seed, ret = _lcg_step(day_seed)
            daily_return = (ret - 0.5) * 0.04
            price = max(0.01, price * (1.0 + daily_return))
        walk_date += timedelta(days=1)

    current_price = price

    # Now generate bars from start to ceiling
    bars: list[OHLCVBar] = []
    bar_date = start

    while bar_date <= ceiling:
        if _is_weekday(bar_date):
            day_seed = _seed_from_symbol_and_date(symbol, bar_date)

            # Daily return
            day_seed, ret = _lcg_step(day_seed)
            daily_return = (ret - 0.5) * 0.04
            close = max(0.01, current_price * (1.0 + daily_return))

            # Spread
            day_seed, spread_r = _lcg_step(day_seed)
            spread_frac = spread_r * 0.012  # 0-1.2%
            high = close * (1.0 + spread_frac)
            low = max(0.01, close * (1.0 - spread_frac))

            # Open: prev close with tiny jitter
            day_seed, open_r = _lcg_step(day_seed)
            open_price = current_price * (1.0 + (open_r - 0.5) * 0.004)
            open_price = max(low, min(high, open_price))

            # Volume
            day_seed, vol_r = _lcg_step(day_seed)
            volume = 500_000.0 + vol_r * 2_000_000.0

            # Use exactly 21:00 UTC (NYSE/NASDAQ close proxy)
            bar_ts = bar_date.replace(hour=21, minute=0, second=0, microsecond=0, tzinfo=UTC)

            bars.append(
                OHLCVBar(
                    timestamp=bar_ts,
                    open=round(open_price, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    volume=round(volume, 0),
                )
            )
            current_price = close

        bar_date += timedelta(days=1)

    return bars


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------


class MockProvider(BaseMarketDataProvider):
    """
    Deterministic synthetic data provider for testing and local development.

    Configuration
    -------------
    fail_symbols : set[str]
        Symbols that raise InvalidTickerError instead of returning data.
        Default: empty.
    unavailable_symbols : set[str]
        Symbols that raise DataUnavailableError (simulating a service outage).
        Default: empty.
    force_empty_symbols : set[str]
        Symbols that return an empty OHLCVDataset (no bars). Useful for
        testing pipeline behaviour when data is absent.
        Default: empty.

    Usage
    -----
        # Standard — returns deterministic data for known symbols
        provider = MockProvider()

        # Error simulation
        provider = MockProvider(fail_symbols={"INVALID"})
        provider = MockProvider(unavailable_symbols={"AAPL"})
    """

    def __init__(
        self,
        *,
        fail_symbols: set[str] | None = None,
        unavailable_symbols: set[str] | None = None,
        force_empty_symbols: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._fail_symbols: frozenset[str] = frozenset(s.upper() for s in (fail_symbols or set()))
        self._unavailable_symbols: frozenset[str] = frozenset(
            s.upper() for s in (unavailable_symbols or set())
        )
        self._force_empty_symbols: frozenset[str] = frozenset(
            s.upper() for s in (force_empty_symbols or set())
        )

    @property
    def capabilities(self) -> ProviderCapabilities:
        return _MOCK_CAPABILITIES

    def _fetch_ohlcv_impl(self, request: OHLCVRequest) -> OHLCVDataset:
        symbol = request.asset.symbol.upper()
        exchange = request.asset.exchange.value

        # Simulate configured failures
        if symbol in self._fail_symbols:
            raise InvalidTickerError(symbol=symbol, exchange=exchange)

        if symbol in self._unavailable_symbols:
            raise DataUnavailableError(
                f"Mock provider: '{symbol}' is configured as temporarily unavailable."
            )

        # Validate the symbol is known (after failure simulation, so tests
        # can test InvalidTickerError via fail_symbols for any symbol)
        if symbol not in _KNOWN_ASSETS:
            raise InvalidTickerError(symbol=symbol, exchange=exchange)

        if symbol in self._force_empty_symbols:
            return OHLCVDataset(
                symbol=symbol,
                exchange=exchange,
                provider=self.capabilities.provider_id,
                as_of=request.as_of,
                bars=[],
            )

        bars = _generate_bars(
            symbol=symbol,
            start=request.start,
            end=request.end,
            as_of=request.as_of,
        )

        return OHLCVDataset(
            symbol=symbol,
            exchange=exchange,
            provider=self.capabilities.provider_id,
            as_of=request.as_of,
            bars=bars,
        )

    def _list_symbols_impl(self, exchange: str) -> list[str]:
        return list(_SYMBOLS_BY_EXCHANGE.get(exchange.upper(), []))

    def fetch_asset_metadata(self, symbol: str, exchange: str) -> AssetMetadata:
        symbol = symbol.upper()

        if symbol in self._fail_symbols:
            raise InvalidTickerError(symbol=symbol, exchange=exchange)

        if symbol in self._unavailable_symbols:
            raise DataUnavailableError(
                f"Mock provider: '{symbol}' is configured as temporarily unavailable."
            )

        if symbol not in _KNOWN_ASSETS:
            raise InvalidTickerError(symbol=symbol, exchange=exchange)

        return _KNOWN_ASSETS[symbol]

    def get_known_asset(self, symbol: str) -> Asset:
        """
        Convenience method for tests: return a core Asset for a known symbol.

        Raises InvalidTickerError if the symbol is not in the mock catalogue.
        """
        symbol = symbol.upper()
        if symbol not in _KNOWN_ASSETS:
            raise InvalidTickerError(symbol=symbol, exchange="UNKNOWN")
        meta = _KNOWN_ASSETS[symbol]
        return meta.to_asset()
