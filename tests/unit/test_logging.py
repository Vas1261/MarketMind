"""
Unit tests for marketmind.logging

Tests that the logging framework configures correctly,
produces a usable logger, and that configure_from_settings()
works without error.
"""

from __future__ import annotations

import logging


def test_get_logger_returns_bound_logger() -> None:
    """get_logger() must return something we can call .info() on."""
    from marketmind.logging import get_logger

    log = get_logger(__name__)
    assert hasattr(log, "info")
    assert hasattr(log, "warning")
    assert hasattr(log, "error")
    assert hasattr(log, "debug")


def test_configure_logging_console_format() -> None:
    """configure_logging() with console format should not raise."""
    from marketmind.logging import configure_logging

    configure_logging(level="WARNING", fmt="console")


def test_configure_logging_json_format() -> None:
    """configure_logging() with json format should not raise."""
    from marketmind.logging import configure_logging

    configure_logging(level="WARNING", fmt="json")


def test_configure_from_settings_does_not_raise(settings) -> None:  # type: ignore[no-untyped-def]
    """configure_from_settings() wires up from Settings without error."""
    from marketmind.logging import configure_from_settings

    configure_from_settings()


def test_logger_can_emit_structured_fields(caplog) -> None:  # type: ignore[no-untyped-def]
    """Verify that log calls with keyword args don't raise."""
    from marketmind.logging import configure_logging, get_logger

    configure_logging(level="DEBUG", fmt="console")
    log = get_logger(__name__)

    with caplog.at_level(logging.DEBUG):
        # Should not raise — keyword args become structured fields
        log.info("test_event", symbol="AAPL", score=0.94)


def test_logger_bind_returns_new_logger() -> None:
    """Bound logger returns a new logger with context attached."""
    from marketmind.logging import get_logger

    log = get_logger(__name__)
    bound = log.bind(experiment_id="EXP-001")
    assert bound is not log
