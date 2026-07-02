"""
Configuration package.

Public API:
    get_settings()      — return the Settings singleton
    clear_settings_cache() — for test isolation
"""

from marketmind.config.settings import Settings, clear_settings_cache, get_settings

__all__ = ["Settings", "clear_settings_cache", "get_settings"]
