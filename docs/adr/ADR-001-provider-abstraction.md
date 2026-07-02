# ADR-001: Market Data Provider Abstraction

**Date:** 2024-01-01
**Status:** ACCEPTED
**Decider:** Architecture Review

---

## Context

MarketMind requires market data (OHLCV, corporate actions) from external sources.
Yahoo Finance is the natural starting point — it is free, well-documented, and supported by `yfinance`.

However, free data providers are unreliable: they change APIs without notice, impose rate limits, go offline, and sometimes serve incorrect data. If the codebase imported `yfinance` directly everywhere, replacing it would require changes across dozens of files.

Additionally, the research platform needs a deterministic **mock provider** for tests that runs without network access, and a **snapshot provider** for point-in-time correct backtests. Both must be drop-in replacements.

---

## Decision

Introduce a `MarketDataProvider` protocol (abstract interface) in `marketmind/core/protocols.py`.

Every data source — Yahoo Finance, Alpha Vantage, Polygon, mock — implements this protocol.

No code outside `marketmind/data/providers/` may import from a specific provider module.
All downstream code (validation, features, models) depends only on the protocol.

The active provider is selected by configuration (`data.providers.primary`), not by code.

---

## Rationale

- **Vendor isolation:** swapping Yahoo Finance for Polygon requires writing one new class and changing one config value.
- **Testability:** the mock provider makes every test deterministic and network-free.
- **Point-in-time correctness:** the snapshot provider can guarantee PIT correctness; other providers document their limitation via `provider_metadata()`.
- **Python structural subtyping:** the `Protocol` class from `typing` requires no inheritance — any class that implements the right methods satisfies the interface automatically.

---

## Alternatives Considered

### Option A: Import yfinance directly everywhere
**Rejected because:** creates a hard dependency on a single vendor with no migration path and makes testing require network access.

### Option B: Abstract base class (ABC) with inheritance
**Rejected because:** Protocol is more Pythonic (structural subtyping), requires no inheritance coupling, and is the modern Python approach. ABCs would require every provider to explicitly inherit from our base class, adding coupling with no benefit.

### Option C: Dependency injection framework
**Rejected because:** overkill for Phase 1. Simple factory function controlled by config is sufficient.

---

## Consequences

**What becomes easier:**
- Swapping data providers is a config change.
- Testing without network access is the default.
- Adding a paid provider later (Polygon, Bloomberg) doesn't touch downstream code.

**What becomes harder:**
- Every new provider must implement the full protocol.
- Provider-specific features (e.g. Polygon's unusual options data) cannot be exposed through the abstract interface without changing it.

**New problems introduced:**
- The protocol must be kept stable once multiple providers implement it. Changing the interface requires updating all implementations.

---

## Review Date

Reconsider if: a second data type (options, fundamentals) requires a substantially different interface. At that point, consider whether a single `MarketDataProvider` covers all asset types or whether specialised protocols are needed.
