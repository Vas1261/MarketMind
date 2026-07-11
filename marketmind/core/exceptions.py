"""
Core Exceptions
===============

All MarketMind exceptions inherit from MarketMindError.

This single hierarchy makes it easy for callers to catch all platform errors
at any granularity:

    except MarketMindError:           # catch everything
    except DataIntegrityError:        # catch data problems only
    except ValidationError:           # catch validation problems only

Design rule: exceptions belong to the domain layer. No infrastructure-specific
exception class should appear in domain code — wrap them at the adapter boundary.
"""


class MarketMindError(Exception):
    """Base class for all MarketMind exceptions."""


# ---------------------------------------------------------------------------
# Data Layer
# ---------------------------------------------------------------------------


class DataError(MarketMindError):
    """Base class for all data-related errors."""


class DataIntegrityError(DataError):
    """
    Raised when point-in-time data integrity is violated.

    Example: requesting historical data with an as_of date in the future,
    or a provider returning data timestamped after the declared as_of boundary.
    """


class ProviderError(DataError):
    """Raised when a market data provider fails or returns unexpected data."""


class ProviderUnavailableError(ProviderError):
    """Raised when a market data provider is unreachable or returns a server error."""


class AuthenticationError(ProviderError):
    """
    Raised when a provider rejects the request due to missing or invalid credentials.

    Callers should not retry — the fix is to supply correct API credentials.
    """


class RateLimitError(ProviderError):
    """
    Raised when a provider rejects the request because the rate limit is exceeded.

    Attributes
    ----------
    retry_after_seconds:
        Number of seconds the caller should wait before retrying.
        None if the provider did not supply a retry-after value.
    """

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


class DataUnavailableError(ProviderError):
    """
    Raised when data for the requested asset and date range is temporarily unavailable.

    Distinct from DataNotFoundError: the data may exist but cannot be served right now
    (e.g. market data feed is delayed, exchange data is embargoed).
    """


class InvalidTickerError(ProviderError):
    """
    Raised when the requested ticker symbol does not exist on the specified exchange.

    Attributes
    ----------
    symbol:
        The invalid symbol that was requested.
    exchange:
        The exchange on which the symbol was not found.
    """

    def __init__(self, symbol: str, exchange: str) -> None:
        self.symbol = symbol
        self.exchange = exchange
        super().__init__(
            f"Ticker '{symbol}' not found on exchange '{exchange}'. "
            "Verify the symbol is correct and listed on the specified exchange."
        )


class DataNotFoundError(DataError):
    """Raised when requested data does not exist in the registry."""


# ---------------------------------------------------------------------------
# Validation Layer
# ---------------------------------------------------------------------------


class ValidationError(MarketMindError):
    """Base class for dataset validation errors."""


class DataQualityGateError(ValidationError):
    """
    Raised when a dataset's quality score falls below the configured threshold.

    Predictions are blocked when this exception is raised — the pipeline
    must not silently degrade to serving low-quality results.
    """

    def __init__(self, score: float, threshold: float, symbol: str) -> None:
        self.score = score
        self.threshold = threshold
        self.symbol = symbol
        super().__init__(
            f"Data quality gate failed for {symbol}: score {score:.3f} < threshold {threshold:.3f}"
        )


class SchemaValidationError(ValidationError):
    """Raised when a dataset does not conform to the expected schema."""


# ---------------------------------------------------------------------------
# Research Layer
# ---------------------------------------------------------------------------


class ResearchError(MarketMindError):
    """Base class for research workflow errors."""


class PreRegistrationError(ResearchError):
    """Raised when a pre-registration document is missing or malformed."""


class ExperimentStateError(ResearchError):
    """Raised when an experiment operation is invalid for its current state."""


class SealedDatasetViolationError(ResearchError):
    """
    Raised when code attempts to use the sealed final validation dataset
    outside of the permitted one-shot final evaluation step.

    This is a research integrity protection, not a user-facing error.
    """


# ---------------------------------------------------------------------------
# Feature Layer
# ---------------------------------------------------------------------------


class FeatureError(MarketMindError):
    """Base class for feature engineering errors."""


class LeakageError(FeatureError):
    """
    Raised when a feature transformation would introduce look-ahead bias.

    Example: a rolling window whose right edge extends beyond the bar
    for which we are computing the feature.
    """


class FeatureNotFoundError(FeatureError):
    """Raised when a requested feature does not exist in the feature store."""


# ---------------------------------------------------------------------------
# Model Layer
# ---------------------------------------------------------------------------


class ModelError(MarketMindError):
    """Base class for model errors."""


class ModelNotFoundError(ModelError):
    """Raised when a requested model version does not exist in the registry."""


class ModelNotFittedError(ModelError):
    """Raised when predict is called on a model that has not been fitted."""


# ---------------------------------------------------------------------------
# Configuration Layer
# ---------------------------------------------------------------------------


class ConfigurationError(MarketMindError):
    """Raised when configuration is missing, malformed, or contradictory."""
