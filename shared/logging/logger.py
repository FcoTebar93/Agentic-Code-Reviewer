"""
Structured JSON logging for all ADMADC services.

Each log entry includes the service name, enabling correlation across
containers in a distributed system. Outputs to stdout for Docker log
aggregation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service = service_name

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)

        extra = getattr(record, "_extra", None)
        if extra:
            entry["extra"] = extra

        return json.dumps(entry, default=str)


def setup_logging(service_name: str) -> logging.Logger:
    """
    Configure the root logger for a service with JSON output to stdout.

    Call once at service startup (in main.py or lifespan).
    Returns the service-specific logger.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter(service_name))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "aio_pika", "aiormq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logger = logging.getLogger(service_name)
    logger.info("Logging initialized", extra={"_extra": {"level": level_name}})
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger. Use for module-level logging."""
    return logging.getLogger(name)
