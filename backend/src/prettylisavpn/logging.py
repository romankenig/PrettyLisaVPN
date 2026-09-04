"""JSON logging with UTC timestamps and no raw exceptions or request data."""

import json
import logging
import logging.config
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": record.getMessage(),
            }
        )


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "console": {"class": "logging.StreamHandler", "formatter": "json"},
                "discard": {"class": "logging.NullHandler"},
            },
            "root": {"handlers": ["console"], "level": level},
            "loggers": {
                "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
                # Access records include request URLs, so always discard them.
                "uvicorn.access": {"handlers": ["discard"], "propagate": False},
                "sqlalchemy": {"handlers": ["discard"], "propagate": False},
                "httpx": {"handlers": ["discard"], "propagate": False},
            },
        }
    )
