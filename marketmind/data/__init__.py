"""
Data Layer
==========

Handles all market data acquisition, validation, and storage for MarketMind.

Phase 2.1 - Provider Abstraction (complete):
  marketmind.data.providers  - provider interface, MockProvider, registry

Phase 2.2 - Yahoo Finance Provider (complete):
  marketmind.data.providers.yahoo

Phase 2.3 - Validation Engine (planned):
  marketmind.data.validation

Phase 2.4 - Dataset Registry / Storage (planned):
  marketmind.data.storage
"""

from marketmind.data.providers import (
    AssetMetadata,
    BaseMarketDataProvider,
    MockProvider,
    OHLCVRequest,
    ProviderCapabilities,
    ProviderRegistry,
    YahooFinanceProvider,
)

__all__ = [
    "AssetMetadata",
    "BaseMarketDataProvider",
    "MockProvider",
    "OHLCVRequest",
    "ProviderCapabilities",
    "ProviderRegistry",
    "YahooFinanceProvider",
]
