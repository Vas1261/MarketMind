"""
Core Protocols
==============

Abstract interfaces (Protocols) for all major component boundaries.

These are the "ports" in the hexagonal architecture. Each protocol defines
what a component must provide, without dictating how it provides it.

Design rules:
  - Protocols live in core and import nothing from outside core.
  - Concrete implementations live in their respective modules
    (data/, models/, features/) and import these protocols.
  - This guarantees the dependency arrow always points inward.
  - Protocols use Python's runtime-checkable Protocol where appropriate,
    but structural subtyping (duck typing) is the primary mechanism.

The benefit: swapping a Yahoo Finance provider for Polygon.io is a matter
of writing a new class that satisfies MarketDataProvider — nothing else changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    from marketmind.core.domain.asset import Asset
    from marketmind.core.domain.market_data import OHLCVDataset

# ---------------------------------------------------------------------------
# Data Layer Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MarketDataProvider(Protocol):
    """
    Abstract interface for all market data sources.

    Every data vendor (Yahoo Finance, Polygon, Alpha Vantage, Mock) must
    implement this protocol. No downstream code may import from a specific
    provider module — only from this protocol.

    The `as_of` parameter is mandatory and represents the point-in-time
    boundary. Providers must not return data with timestamps after `as_of`.
    Providers that cannot guarantee this must document it explicitly in
    provider_metadata().
    """

    def fetch_ohlcv(
        self,
        asset: Asset,
        start: datetime,
        end: datetime,
        as_of: datetime,
    ) -> OHLCVDataset:
        """
        Fetch OHLCV data for a single asset.

        Parameters
        ----------
        asset:
            The asset to fetch data for.
        start:
            Inclusive start date.
        end:
            Inclusive end date.
        as_of:
            Point-in-time boundary. No bar may have timestamp > as_of.

        Raises
        ------
        DataIntegrityError:
            If any returned bar has timestamp > as_of.
        ProviderError:
            If the provider returns an error or unexpected response.
        DataNotFoundError:
            If no data exists for the requested asset and date range.
        """
        ...

    def list_available_symbols(self, exchange: str) -> list[str]:
        """List all symbols available from this provider for a given exchange."""
        ...

    def provider_metadata(self) -> dict[str, Any]:
        """
        Metadata about this provider's capabilities and known limitations.

        Must include:
          - "name": str
          - "point_in_time_guaranteed": bool
          - "pit_limitation_description": str (if not guaranteed)
          - "supported_exchanges": list[str]
          - "data_delay_minutes": int
        """
        ...


@runtime_checkable
class ValidationRule(Protocol):
    """
    Abstract interface for a single dataset validation rule.

    Every rule must be independently testable and produce a result
    that can be included in a DataQualityScore.

    Attributes
    ----------
    rule_name:
        Unique identifier for this rule.
    severity:
        "error" — failure blocks the dataset from downstream use.
        "warning" — failure reduces quality score but does not block.
    """

    rule_name: str
    severity: str

    def validate(self, dataset: OHLCVDataset) -> ValidationRuleResult:  # type: ignore[name-defined]  # noqa: F821
        """
        Apply this rule to the dataset.

        Returns a ValidationRuleResult regardless of pass/fail —
        never raises an exception for a validation failure.
        Only raises if the rule itself is broken (programming error).
        """
        ...


# ---------------------------------------------------------------------------
# Feature Layer Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class FeatureTransformer(Protocol):
    """
    Abstract interface for a feature engineering transformer.

    Transformers follow the fit/transform pattern to ensure that
    parameters are estimated only on training data, never on test data.

    The fit() step computes statistics (means, stds, percentile boundaries)
    from training data only. The transform() step applies those statistics
    to both training and test data, guaranteeing no look-ahead.
    """

    transformer_name: str

    def fit(self, dataset: OHLCVDataset) -> FeatureTransformer:
        """
        Estimate parameters from training data.

        Must not modify the input dataset.
        Must return self to enable method chaining.

        Critical: this method must only be called on training-fold data.
        Calling fit() on data that includes the test period is leakage.
        """
        ...

    def transform(self, dataset: OHLCVDataset) -> dict[str, list[float]]:
        """
        Apply fitted parameters to produce feature values.

        Returns a dict mapping feature_name → list of values, one per bar.
        Values must be aligned with dataset.bars by index.

        Must be called only after fit(). May be called on both train and
        test data, but must produce identical results for identical inputs.
        """
        ...

    def get_feature_names(self) -> list[str]:
        """Return the list of feature names this transformer produces."""
        ...

    def get_lookback_bars(self) -> int:
        """
        Return the number of bars consumed by the longest window in this transformer.

        Used by the leakage audit to verify window alignment.
        The first `get_lookback_bars()` rows of any output will be NaN or missing.
        """
        ...


# ---------------------------------------------------------------------------
# Model Layer Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MLModel(Protocol):
    """
    Abstract interface for all machine learning models.

    MarketMind treats classification as the primary task (direction prediction)
    and regression as secondary. All models must support predict_proba()
    to enable calibration and confidence estimation.

    Models that do not naturally produce probabilities (e.g. tree depth=1)
    must implement a calibration wrapper before implementing this protocol.
    """

    model_id: str
    model_type: str

    def fit(
        self,
        features: dict[str, list[float]],
        labels: list[int],
    ) -> MLModel:
        """
        Train the model on the provided features and labels.

        Labels must be binary integers: +1 (up) or -1 (down) for classification.
        Returns self to enable chaining.
        """
        ...

    def predict_proba(self, features: dict[str, list[float]]) -> list[float]:
        """
        Return calibrated probability that next-day direction is UP (+1).

        Returns a list of floats in [0.0, 1.0], one per row.
        Values closer to 1.0 indicate higher confidence in UP direction.
        Values closer to 0.0 indicate higher confidence in DOWN direction.

        Raises ModelNotFittedError if called before fit().
        """
        ...

    def predict(self, features: dict[str, list[float]]) -> list[int]:
        """
        Return binary direction predictions: +1 (up) or -1 (down).

        Derived from predict_proba() with threshold=0.5.
        Raises ModelNotFittedError if called before fit().
        """
        ...

    def get_feature_importances(self) -> dict[str, float] | None:
        """
        Return feature importance scores, or None if not supported.

        Keys are feature names, values are importance scores.
        Scores are normalised to sum to 1.0 where possible.
        """
        ...


# ---------------------------------------------------------------------------
# Experiment Tracking Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class ExperimentTracker(Protocol):
    """
    Abstract interface for experiment tracking backends.

    Version 1 uses a file-based implementation.
    MLflow can be swapped in by implementing this protocol.

    This is exactly the pattern described in the architecture document:
    MLflow is not a mandatory dependency, but the interface is already clean.
    """

    def start_run(self, experiment_id: str, run_name: str) -> str:
        """Start a tracked run. Returns a run_id string."""
        ...

    def log_params(self, run_id: str, params: dict[str, Any]) -> None:
        """Log hyperparameters for the given run."""
        ...

    def log_metrics(self, run_id: str, metrics: dict[str, float]) -> None:
        """Log evaluation metrics for the given run."""
        ...

    def log_artifact(self, run_id: str, artifact_path: str) -> None:
        """Log a file artifact (model, report, chart) for the given run."""
        ...

    def end_run(self, run_id: str) -> None:
        """Mark the run as complete."""
        ...
