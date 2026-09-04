import pytest


@pytest.fixture(autouse=True)
def preserve_test_logging(monkeypatch):
    monkeypatch.setattr("prettylisavpn.main.configure_logging", lambda level: None)
