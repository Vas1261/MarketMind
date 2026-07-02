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
    ConfigurationError,
    DataError,
    DataIntegrityError,
    DataNotFoundError,
    DataQualityGateError,
    ExperimentStateError,
    FeatureError,
    LeakageError,
    MarketMindError,
    ModelError,
    ModelNotFittedError,
    ProviderError,
    ResearchError,
    ValidationError,
)

__all__ = [
    # Experiments
    "AcceptanceCriteria",
    # Assets
    "Asset",
    "AssetClass",
    "ConfigurationError",
    "DataError",
    "DataIntegrityError",
    "DataNotFoundError",
    "DataQualityGateError",
    # Market Data
    "DataQualityLevel",
    "DataQualityScore",
    "Exchange",
    "Experiment",
    "ExperimentStateError",
    "ExperimentStatus",
    "FeatureError",
    "KillCriteria",
    "LeakageError",
    "MarketCapTier",
    # Exceptions
    "MarketMindError",
    # Regime
    "MarketRegime",
    "ModelError",
    "ModelNotFittedError",
    "OHLCVBar",
    "OHLCVDataset",
    "PreRegistration",
    "ProviderError",
    "RegimeClassification",
    "ResearchError",
    "Universe",
    "ValidationError",
    "ValidationRuleResult",
]
