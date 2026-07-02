"""
Logging Framework
=================

MarketMind uses structlog for structured logging throughout.

Structured logging emits log records as key-value pairs rather than
formatted strings. This has two concrete benefits for a research platform:

  1. Log records are machine-parseable — you can filter, aggregate, and
     analyse them programmatically rather than grepping plain text.

  2. Context (experiment_id, symbol, fold, dataset_hash) is attached to
     every log record automatically, making it trivial to trace all activity
     for a specific experiment or asset.

Usage
-----
    from marketmind.logging import get_logger

    log = get_logger(__name__)
    log.info("validation_complete", symbol="AAPL", score=0.94, bars=1250)
    log.warning("quality_gate_near_threshold", symbol="TSLA", score=0.76)
    log.error("provider_failed", provider="yahoo", error=str(e))

Context Binding
---------------
    # Bind context that should appear on all subsequent log calls
    log = log.bind(experiment_id="EXP-007", fold=2)
    log.info("fold_started", train_bars=750)   # experiment_id and fold included
    log.info("fold_complete", sharpe=1.23)     # experiment_id and fold included

Initialisation
--------------
Call configure_logging() once at application startup.
It reads from Settings and must not be called in library code.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from structlog.types import EventDict, WrappedLogger


def _add_log_level(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add the log level name to the event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def _drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Remove the 'color_message' key that uvicorn adds.

    When running behind uvicorn, it injects a 'color_message' key that
    duplicates 'event' with ANSI codes. We drop it to keep records clean.
    """
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(
    level: str = "INFO",
    fmt: str = "console",
    log_file: str | None = None,
) -> None:
    """
    Configure the logging framework. Call once at application startup.

    Parameters
    ----------
    level:
        Log level string: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    fmt:
        "console" for human-readable coloured output (development).
        "json" for machine-parseable JSON (production, CI).
    log_file:
        Optional path to write logs to in addition to stdout.
        Only used in production environment.

    Notes
    -----
    This function configures both structlog and the standard library logging
    module so that third-party libraries (which use stdlib logging) are also
    captured and formatted consistently.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # --- Standard library logging setup --------------------------------
    # Route all stdlib log records through structlog's formatting.
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,
    )

    # Silence noisy third-party loggers
    for noisy in ["urllib3", "httpx", "httpcore", "hpack"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # --- Shared processors (applied regardless of output format) --------
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_log_level,
        _drop_color_message_key,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    # --- Output-format-specific renderer --------------------------------
    if fmt == "json":
        # Production / CI: each record is a JSON object on a single line.
        # Easily ingested by log aggregators (Datadog, Loki, CloudWatch).
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        # Development: coloured, aligned key=value output.
        renderer = structlog.dev.ConsoleRenderer(
            colors=sys.stdout.isatty(),  # disable colours when piped
            exception_formatter=structlog.dev.plain_traceback,
        )

    # --- Structlog configuration ----------------------------------------
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Wire structlog into the stdlib formatter so third-party logs also
    # go through our shared processors.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a structlog BoundLogger for the given module name.

    Convention: always pass __name__ so log records carry the module path.

    Example
    -------
        log = get_logger(__name__)
        log.info("dataset_loaded", symbol="AAPL", rows=1250)
    """
    logger: structlog.BoundLogger = structlog.get_logger(name)
    return logger


def configure_from_settings() -> None:
    """
    Initialise logging from the application Settings singleton.

    Call this once at the entry point (CLI, API startup, research runner).
    Do not call from library code — logging configuration is the
    responsibility of the application, not individual modules.
    """
    from marketmind.config.settings import get_settings

    settings = get_settings()
    configure_logging(
        level=settings.logging.level,
        fmt=settings.logging.format,
        log_file=str(settings.logging.log_file) if settings.logging.log_file else None,
    )
