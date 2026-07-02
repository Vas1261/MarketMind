"""
Configuration System
====================

MarketMind uses a layered configuration hierarchy:

  1. Default values (defined in this file)
  2. Environment YAML file (config/environments/{ENVIRONMENT}.yaml)
  3. Environment variables (prefixed MM_)
  4. CLI flags (for script invocations only)

Each layer overrides the one above it.

The environment is determined by the MM_ENVIRONMENT environment variable.
Valid values: local | research | test | production

All configuration is validated at startup via Pydantic. Unknown keys raise
an error — this prevents silent configuration drift.

Usage
-----
    from marketmind.config import get_settings

    settings = get_settings()
    threshold = settings.data.validation.quality_gate_threshold
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Sub-configuration models
# ---------------------------------------------------------------------------


class ProviderSettings(BaseSettings):
    """Configuration for market data providers."""

    model_config = SettingsConfigDict(extra="forbid")

    primary: str = "yahoo"
    fallback: str = "mock"

    @field_validator("primary", "fallback")
    @classmethod
    def validate_provider_name(cls, v: str) -> str:
        allowed = {"yahoo", "alpha_vantage", "polygon", "mock", "snapshot"}
        if v not in allowed:
            raise ValueError(f"Provider must be one of {allowed}, got {v!r}")
        return v


class ValidationSettings(BaseSettings):
    """Configuration for the data validation engine."""

    model_config = SettingsConfigDict(extra="forbid")

    quality_gate_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum quality score. Predictions blocked below this.",
    )
    outlier_sigma: float = Field(
        default=4.0,
        gt=0.0,
        description="Number of standard deviations to use for outlier detection.",
    )
    max_missing_ratio: float = Field(
        default=0.02,
        ge=0.0,
        le=1.0,
        description="Maximum fraction of missing values before hard failure.",
    )
    freshness_max_lag_days: int = Field(
        default=5,
        gt=0,
        description="Maximum trading days since last bar before data is stale.",
    )


class StorageSettings(BaseSettings):
    """Configuration for local file storage."""

    model_config = SettingsConfigDict(extra="forbid")

    base_path: Path = Path("./data")
    datasets_path: Path = Path("./data/datasets")
    features_path: Path = Path("./data/features")
    sealed_path: Path = Path("./data/sealed")

    @model_validator(mode="after")
    def resolve_paths(self) -> StorageSettings:
        """Ensure all paths are absolute if relative."""
        return self


class DataSettings(BaseSettings):
    """Top-level data configuration."""

    model_config = SettingsConfigDict(extra="forbid")

    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    validation: ValidationSettings = Field(default_factory=ValidationSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)


class WalkForwardSettings(BaseSettings):
    """Walk-forward validation configuration."""

    model_config = SettingsConfigDict(extra="forbid")

    train_window_years: int = Field(default=3, gt=0)
    test_window_months: int = Field(default=6, gt=0)
    step_months: int = Field(default=6, gt=0)
    min_train_bars: int = Field(
        default=500,
        gt=0,
        description="Minimum bars required in a training fold. Folds with fewer bars are skipped.",
    )


class BootstrapSettings(BaseSettings):
    """Block bootstrap configuration for statistical significance testing."""

    model_config = SettingsConfigDict(extra="forbid")

    iterations: int = Field(default=10_000, gt=0)
    block_length_method: Literal["auto", "fixed"] = "auto"
    fixed_block_length: int | None = None
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)


class TransactionCostSettings(BaseSettings):
    """Transaction cost model for backtesting."""

    model_config = SettingsConfigDict(extra="forbid")

    commission_bps: float = Field(default=5.0, ge=0.0)
    market_impact_bps: float = Field(default=5.0, ge=0.0)
    spread_bps: float = Field(default=5.0, ge=0.0)

    @property
    def round_trip_bps(self) -> float:
        """Total round-trip cost in basis points."""
        return (self.commission_bps + self.market_impact_bps + self.spread_bps) * 2


class EvaluationSettings(BaseSettings):
    """Evaluation and backtesting configuration."""

    model_config = SettingsConfigDict(extra="forbid")

    walk_forward: WalkForwardSettings = Field(default_factory=WalkForwardSettings)
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)
    transaction_costs: TransactionCostSettings = Field(default_factory=TransactionCostSettings)


class ResearchSettings(BaseSettings):
    """Research framework configuration."""

    model_config = SettingsConfigDict(extra="forbid")

    protocol_version: str = "1.0"
    pre_registrations_path: Path = Path("./docs/research/pre-registrations")
    research_log_path: Path = Path("./docs/research/research-log")

    expected_acceptance_rate_min: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Acceptance rates below this trigger a methodology warning.",
    )
    expected_acceptance_rate_max: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Acceptance rates above this trigger a mandatory review.",
    )


class DatabaseSettings(BaseSettings):
    """Database configuration. SQLite for V1; PostgreSQL-ready via URL pattern."""

    model_config = SettingsConfigDict(extra="forbid")

    url: str = "sqlite:///./data/marketmind.db"
    echo_sql: bool = False

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("sqlite") or v.startswith("postgresql")):
            raise ValueError(
                f"Database URL must be sqlite or postgresql, got {v!r}. "
                "Other databases are not supported."
            )
        return v


class ExperimentTrackingSettings(BaseSettings):
    """Experiment tracking configuration. MLflow-ready via backend_uri."""

    model_config = SettingsConfigDict(extra="forbid")

    backend: Literal["file", "mlflow"] = "file"
    tracking_uri: str = "./data/experiments"
    experiment_name: str = "marketmind"


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(extra="forbid")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["console", "json"] = "console"
    log_file: Path | None = None


class RecommendationThresholds(BaseSettings):
    """Rule thresholds for the recommendation engine. Versioned separately."""

    model_config = SettingsConfigDict(extra="forbid")

    min_direction_probability: float = Field(default=0.60, ge=0.5, le=1.0)
    min_data_quality: float = Field(default=0.75, ge=0.0, le=1.0)
    max_volatility_percentile: float = Field(default=80.0, ge=0.0, le=100.0)
    rule_set_version: str = "1.0"


# ---------------------------------------------------------------------------
# Root Settings Model
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """
    Root configuration model for MarketMind.

    Loaded once at startup via get_settings() and cached.
    All configuration access goes through this object.

    Environment is determined by MM_ENVIRONMENT env var.
    YAML file for that environment is loaded and merged.
    """

    model_config = SettingsConfigDict(
        env_prefix="MM_",
        env_nested_delimiter="__",
        extra="forbid",
        case_sensitive=False,
    )

    environment: Literal["local", "research", "test", "production"] = "local"

    data: DataSettings = Field(default_factory=DataSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    experiment_tracking: ExperimentTrackingSettings = Field(
        default_factory=ExperimentTrackingSettings
    )
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    recommendation: RecommendationThresholds = Field(default_factory=RecommendationThresholds)

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: Any) -> str:
        allowed = {"local", "research", "test", "production"}
        normalised: str = str(v).lower()
        if normalised not in allowed:
            raise ValueError(f"MM_ENVIRONMENT must be one of {allowed}, got {normalised!r}")
        return normalised


# ---------------------------------------------------------------------------
# YAML Loader
# ---------------------------------------------------------------------------


def _load_yaml_config(environment: str, config_dir: Path) -> dict[str, Any]:
    """
    Load the YAML configuration file for the given environment.

    Returns an empty dict if the file does not exist — all values
    will fall back to defaults.
    """
    yaml_path = config_dir / "environments" / f"{environment}.yaml"
    if not yaml_path.exists():
        return {}
    with yaml_path.open() as f:
        return yaml.safe_load(f) or {}


def _find_config_dir() -> Path:
    """
    Locate the config directory relative to the package root.

    Searches upward from the current file until it finds a directory
    containing pyproject.toml (project root), then looks for config/.
    """
    current = Path(__file__).parent
    while current != current.parent:
        if (current / "pyproject.toml").exists():
            config_dir = current / "marketmind" / "config"
            if config_dir.exists():
                return config_dir
        current = current.parent
    # Fallback: directory next to this file
    return Path(__file__).parent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the application settings singleton.

    Loads configuration from:
      1. Default values
      2. YAML file for MM_ENVIRONMENT
      3. Environment variables (MM_ prefix)

    Cached after first call — call clear_settings_cache() in tests
    that need to vary the configuration.
    """
    environment = os.environ.get("MM_ENVIRONMENT", "local").lower()
    config_dir = _find_config_dir()
    yaml_data = _load_yaml_config(environment, config_dir)

    # Remove 'environment' from YAML data if present — we pass it explicitly
    # to avoid a "multiple values for keyword argument" TypeError when the
    # YAML file itself contains an `environment:` key (which it does, for
    # human readability).
    yaml_data.pop("environment", None)

    # Pydantic Settings merges env vars automatically via model_config.
    # We pass YAML data as explicit kwargs which are then overridable by env vars.
    return Settings(environment=environment, **yaml_data)  # type: ignore[arg-type]


def clear_settings_cache() -> None:
    """
    Clear the settings cache.

    Call this in test setUp/tearDown when tests need to vary the configuration.
    Never call this in production code.
    """
    get_settings.cache_clear()
