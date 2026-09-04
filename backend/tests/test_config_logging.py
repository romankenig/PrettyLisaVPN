import json
import logging

import pytest
from pydantic import ValidationError

from prettylisavpn.config import Settings
from prettylisavpn.logging import JsonFormatter, configure_logging


def test_environment_configuration(monkeypatch):
    monkeypatch.setenv("APPLICATION_VERSION", "2.0.0")
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://user:private-password@localhost/db")
    settings = Settings(_env_file=None)
    assert settings.application_version == "2.0.0"
    assert settings.environment == "staging"
    assert "private-password" not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"postgres_url": "sqlite://"},
        {"valkey_url": "http://localhost"},
        {"dependency_timeout_seconds": 0},
        {"postgres_pool_size": 0},
    ],
)
def test_invalid_configuration(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_json_logging_has_utc_timestamp_without_tracebacks():
    record = logging.LogRecord("test", logging.ERROR, "", 0, "request_failed", (), None)
    record.exc_text = "secret-password"
    result = JsonFormatter().format(record)
    payload = json.loads(result)
    assert payload["timestamp"].endswith("+00:00")
    assert payload["event"] == "request_failed"
    assert payload["level"] == "ERROR"
    assert "secret-password" not in result


def test_logging_discards_access_urls():
    # Restore all affected logger state to avoid changing pytest's capture configuration.
    names = ["", "uvicorn", "uvicorn.access", "sqlalchemy", "httpx"]
    saved = [
        (
            logging.getLogger(name),
            logging.getLogger(name).handlers[:],
            logging.getLogger(name).level,
            logging.getLogger(name).propagate,
        )
        for name in names
    ]
    try:
        configure_logging("INFO")
        access = logging.getLogger("uvicorn.access")
        assert not access.propagate
        assert all(isinstance(handler, logging.NullHandler) for handler in access.handlers)
        assert isinstance(logging.getLogger().handlers[0].formatter, JsonFormatter)
    finally:
        for logger, handlers, level, propagate in saved:
            logger.handlers = handlers
            logger.setLevel(level)
            logger.propagate = propagate
