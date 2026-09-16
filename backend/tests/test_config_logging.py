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
        {"email_smtp_port": 0},
        {"email_provider": "unknown"},
        {"email_smtp_tls_mode": "none"},
        {"email_connection_timeout_seconds": 0},
        {"email_send_timeout_seconds": 0},
        {"vpn_node_stale_timeout_seconds": 9},
        {"vpn_node_health_poll_interval_seconds": 90},
        {"vpn_client_allowed_ips": ["10.0.0.0/8"]},
        {"vpn_client_allowed_ips": ["0.0.0.0/0", "10.0.0.0/8"]},
        {"vpn_node_agent_auth_token": "a" * 32},
        {
            "email_smtp_username": "auth@prettylisavpn.com",
            "email_from_address": "other@prettylisavpn.com",
        },
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


def test_smtp_credential_is_redacted_from_settings_repr():
    settings = Settings(_env_file=None, email_smtp_password="private-mailbox-password")

    assert "private-mailbox-password" not in repr(settings)


def test_node_agent_credential_is_redacted_and_requires_complete_mtls_configuration():
    settings = Settings(
        _env_file=None,
        vpn_node_agent_auth_token="private-node-machine-token-value",
        vpn_node_agent_tls_ca="/run/secrets/server-ca.crt",
        vpn_node_agent_tls_client_certificate="/run/secrets/backend-client.crt",
        vpn_node_agent_tls_client_key="/run/secrets/backend-client.key",
    )

    assert settings.vpn_node_agent_is_configured()
    assert "private-node-machine-token-value" not in repr(settings)


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
