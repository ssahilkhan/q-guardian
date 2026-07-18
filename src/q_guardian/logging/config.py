"""Logging configuration for Q-Guardian.

Sets up structlog with both console and file handlers.
Supports daily rotation, structured JSON output, and log levels.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_format: str = "json",
) -> None:
    """Configure application-wide logging.

    Sets up both console and file logging with structlog integration.
    File logs are rotated daily with configurable retention.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory to write log files.
        log_format: Output format - 'json' for structured, 'console' for human-readable.
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    log_level_int = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level_int),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _setup_file_handler(log_path, log_level_int)
    _setup_stdlib_logging(log_level_int)


def _setup_file_handler(log_path: Path, log_level: int) -> None:
    """Set up rotating file handler for standard logging.

    Args:
        log_path: Directory to store log files.
        log_level: Minimum log level for the handler.
    """
    file_handler = TimedRotatingFileHandler(
        filename=log_path / "q_guardian.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.root.addHandler(file_handler)


def _setup_stdlib_logging(log_level: int) -> None:
    """Configure stdlib logging with a console handler.

    Args:
        log_level: Minimum log level.
    """
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.root.addHandler(console_handler)
    logging.root.setLevel(log_level)

    noisy_loggers = [
        "uvicorn.access",
        "motor",
        "pymongo",
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a named structlog logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        A bound logger instance.
    """
    return structlog.get_logger(name)
