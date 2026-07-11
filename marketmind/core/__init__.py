"""
Core - Domain Layer
===================

The innermost layer of the hexagonal architecture.

Contains:
  - Domain value objects (asset, market_data, experiment, regime)
  - Abstract protocols (interfaces for all major component boundaries)
  - Domain exceptions

Dependency rule: this module imports NOTHING from outside marketmind.core.
This is enforced by the import-linter CI check.
"""

from marketmind.core.domain.asset import Asset, AssetClass, Exchange, MarketCapTier, Universe
from marketmind.core.domain.experiment import (
    AcceptanceCriteria,
    Experiment,
    ExperimentStatus,
    KillCriteria,
    PreRegistration,
)
from marketmind.core.domain.market_data import (
    DataQualityLevel,
    DataQualityScore,
    OHLCVBar,
    OHLCVDataset,
    ValidationRuleResult,
)
from marketmind.core.domain.regime import MarketRegime, RegimeClassification
from marketmind.core.exceptions import (
    AuthenticationError,
    ConfigurationError,
    DataError,
    DataIntegrityError,
    DataNotFoundError,
    DataQualityGateError,
    DataUnavailableError,
    ExperimentStateError,
    FeatureError,
    InvalidTickerError,
    LeakageError,
    MarketMindError,
    ModelError,
    ModelNotFittedError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    ResearchError,
    ValidationError,
)

__all__ = [
    # Experiments
    "AcceptanceCriteria",
    # Assets
    "Asset",
    "AssetClass",
    # Exceptions — providers
    "AuthenticationError",
    # Exceptions — other layers
    "ConfigurationError",
    # Exceptions — data layer
    "DataError",
    "DataIntegrityError",
    "DataNotFoundError",
    "DataQualityGateError",
    # Market Data
    "DataQualityLevel",
    "DataQualityScore",
    "DataUnavailableError",
    "Exchange",
    "Experiment",
    "ExperimentStateError",
    "ExperimentStatus",
    "FeatureError",
    "InvalidTickerError",
    "KillCriteria",
    "LeakageError",
    "MarketCapTier",
    # Exceptions — base
    "MarketMindError",
    # Regime
    "MarketRegime",
    "ModelError",
    "ModelNotFittedError",
    "OHLCVBar",
    "OHLCVDataset",
    "PreRegistration",
    "ProviderError",
    "ProviderUnavailableError",
    "RateLimitError",
    "RegimeClassification",
    "ResearchError",
    "Universe",
    "ValidationError",
    "ValidationRuleResult",
]
