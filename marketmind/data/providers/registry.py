"""
Provider Registry
=================

Configuration-driven factory that resolves and instantiates market data
providers by name.

Design: Class-level registry (dict[str, type[BaseMarketDataProvider]]).
  - Providers register themselves at import time via ProviderRegistry.register().
  - The active provider is resolved from Settings at runtime via get_from_settings().
  - This decouples every pipeline component from specific provider imports —
    nothing outside this module needs to import MockProvider or YahooProvider.

Adding a new provider:
  1. Implement BaseMarketDataProvider in a new module.
  2. Call ProviderRegistry.register("name", NewProvider) at the bottom of that module.
  3. Set MM_DATA__PROVIDERS__PRIMARY=name in config.
  No other code changes required.
"""

from __future__ import annotations

from typing import ClassVar

from marketmind.core.exceptions import ConfigurationError
from marketmind.data.providers.base import BaseMarketDataProvider


class ProviderRegistry:
    """
    Registry and factory for MarketDataProvider implementations.

    Class-level state is intentional: the registry is global and populated
    at module import time. This mirrors how Python's logging handler registry
    and Django's app registry work — a single process-wide catalogue.

    Thread safety: register() is not thread-safe and must only be called at
    module import time (before any concurrent code runs). get() and
    get_from_settings() are read-only and safe to call concurrently.
    """

    _registry: ClassVar[dict[str, type[BaseMarketDataProvider]]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[BaseMarketDataProvider]) -> None:
        """
        Register a provider class under the given name.

        Call this at module level in the provider's own module,
        after the class definition.

        Parameters
        ----------
        name:
            The configuration key used to select this provider.
            Must be lowercase. Must match the value used in
            config/environments/*.yaml under data.providers.primary.
        provider_class:
            The concrete provider class (not an instance).

        Raises
        ------
        ConfigurationError
            If `name` is empty or contains uppercase characters.
        TypeError
            If provider_class does not extend BaseMarketDataProvider.
        """
        if not name:
            raise ConfigurationError("Provider name cannot be empty.")
        if name != name.lower():
            raise ConfigurationError(
                f"Provider name must be lowercase, got '{name}'. "
                "This must match the config file key exactly."
            )
        if not (
            isinstance(provider_class, type) and issubclass(provider_class, BaseMarketDataProvider)
        ):
            raise TypeError(f"{provider_class!r} must be a subclass of BaseMarketDataProvider.")
        if name in cls._registry:
            # Allow re-registration (e.g. test isolation that patches a provider)
            # but log it as a warning at the module level
            pass
        cls._registry[name] = provider_class

    @classmethod
    def get(cls, name: str, **kwargs: object) -> BaseMarketDataProvider:
        """
        Instantiate and return a provider by name.

        Parameters
        ----------
        name:
            The provider key (must have been registered).
        **kwargs:
            Passed to the provider's __init__. Useful for injecting test
            configuration (e.g. MockProvider(fail_symbols={"X"})).

        Returns
        -------
        BaseMarketDataProvider
            A freshly instantiated provider.

        Raises
        ------
        ConfigurationError
            If `name` is not registered.
        """
        provider_class = cls._registry.get(name)
        if provider_class is None:
            available = sorted(cls._registry.keys())
            raise ConfigurationError(
                f"No provider registered under name '{name}'. "
                f"Available providers: {available}. "
                "Ensure the provider module has been imported."
            )
        return provider_class(**kwargs)

    @classmethod
    def get_from_settings(cls) -> BaseMarketDataProvider:
        """
        Resolve and instantiate the provider configured in application Settings.

        Reads `settings.data.providers.primary` and falls back to
        `settings.data.providers.fallback` if the primary is not available.

        Returns
        -------
        BaseMarketDataProvider
            The configured provider instance.

        Raises
        ------
        ConfigurationError
            If neither primary nor fallback provider is registered.
        """
        from marketmind.config.settings import get_settings

        settings = get_settings()
        primary = settings.data.providers.primary
        fallback = settings.data.providers.fallback

        if primary in cls._registry:
            return cls.get(primary)

        if fallback in cls._registry:
            from marketmind.logging import get_logger

            log = get_logger(__name__)
            log.warning(
                "provider_registry.primary_unavailable",
                primary=primary,
                fallback=fallback,
                reason="Primary provider not registered; using fallback.",
            )
            return cls.get(fallback)

        raise ConfigurationError(
            f"Neither primary provider '{primary}' nor fallback provider '{fallback}' "
            "is registered. "
            "Ensure provider modules are imported before calling get_from_settings()."
        )

    @classmethod
    def available(cls) -> list[str]:
        """Return a sorted list of all registered provider names."""
        return sorted(cls._registry.keys())

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """Return True if `name` has been registered."""
        return name in cls._registry

    @classmethod
    def clear(cls) -> None:
        """
        Clear all registered providers.

        For use in tests only — resets the registry to an empty state.
        Call ProviderRegistry.clear() in teardown if tests manipulate the registry.
        """
        cls._registry.clear()


# ---------------------------------------------------------------------------
# Auto-register built-in providers
# ---------------------------------------------------------------------------
# Importing this module triggers auto-registration of the MockProvider.
# Real providers (Yahoo, Polygon) register themselves when their modules
# are imported, which happens lazily via get() or get_from_settings().
# This keeps optional dependencies (yfinance, etc.) out of the import chain.


def _register_builtins() -> None:
    """Register providers that ship with Phase 1/2 of MarketMind."""
    from marketmind.data.providers.mock import MockProvider

    ProviderRegistry.register("mock", MockProvider)


_register_builtins()
