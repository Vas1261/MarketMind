"""
Data Providers
==============

Market data provider abstraction layer.

Public API
----------
    from marketmind.data.providers import (
        BaseMarketDataProvider,
        MockProvider,
        YahooFinanceProvider,
        ProviderRegistry,
        OHLCVRequest,
        ProviderCapabilities,
        AssetMetadata,
    )

Architecture
------------
Every provider inherits from BaseMarketDataProvider and implements:
  - capabilities        -> ProviderCapabilities descriptor
  - _fetch_ohlcv_impl() -> actual data retrieval
  - _list_symbols_impl() -> available symbol discovery
  - fetch_asset_metadata() -> per-asset metadata

The ProviderRegistry resolves providers by configuration name.
No downstream component imports a concrete provider class directly.

Phase 2.1 providers:
  mock     -> MockProvider (deterministic synthetic data, no network)

Phase 2.2 providers:
  yahoo    -> YahooFinanceProvider (Yahoo Finance via yfinance)
"""

from marketmind.data.providers.base import BaseMarketDataProvider
from marketmind.data.providers.mock import MockProvider
from marketmind.data.providers.models import AssetMetadata, OHLCVRequest, ProviderCapabilities
from marketmind.data.providers.registry import ProviderRegistry
from marketmind.data.providers.yahoo import YahooFinanceProvider

__all__ = [
    "AssetMetadata",
    "BaseMarketDataProvider",
    "MockProvider",
    "OHLCVRequest",
    "ProviderCapabilities",
    "ProviderRegistry",
    "YahooFinanceProvider",
]
