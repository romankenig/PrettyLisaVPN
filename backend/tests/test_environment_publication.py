"""Environment boundaries and atomic website publication contracts."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from prettylisavpn.billing.web_sessions import BillingWebSessions


def load(name):
    path = Path(__file__).resolve().parents[2] / "infra/deployment" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_native_handoff_uses_the_configured_website():
    service = BillingWebSessions(Mock(), Mock(), Mock(), "https://test.prettylisavpn.com")
    service._active = AsyncMock()
    service.tokens.issue = AsyncMock(return_value="a" * 43)
    assert (
        await service.handoff(uuid4())
        == "https://test.prettylisavpn.com/account/#handoff=" + "a" * 43
    )


def test_release_readiness_requires_the_correct_runtime_environment():
    gate = load("wait_backend")
    version = {
        "application_name": "PrettyLisaVPN",
        "application_version": "0.54.2+g" + "a" * 40,
        "environment": "production",
    }
    ready = {"status": "ready", "dependencies": {"postgresql": True, "valkey": True}}
    assert gate.matches(version, ready, "0.54.2", "production")
    assert not gate.matches(version, ready, "0.54.2", "development")
    assert not gate.matches(version, ready, "0.54.1", "production")


def test_private_downloads_use_local_store_behind_owner_auth():
    source = Path(__file__).resolve().parents[2] / "sites/fleet-dashboard"
    functions = runpy.run_path(str(source / "install.py"))
    template = (source / "dashboard.caddy.template").read_text()
    config = functions["render"](template, "admin", "$2b$12$" + "a" * 53, "t" * 32)
    assert config.index("basic_auth") < config.index("handle_path /dashboard/downloads/*")
    assert "api.test.prettylisavpn.com" not in config
    assert "reverse_proxy backend:8000" in config
    assert "root * /etc/caddy/dashboard/downloads/current" in config
    assert "root * /etc/caddy/dashboard/site" in config


@pytest.mark.skipif(sys.platform == "win32", reason="Atomic publisher runs on Linux")
def test_website_bad_identity_preserves_current_release(tmp_path):
    publisher = load("publish_website")
    source = tmp_path / "source"
    source.mkdir()
    root = tmp_path / "served"
    sha = "a" * 40
    identity = {"source_sha": sha, "run_id": "100", "run_attempt": "1"}
    (source / "index.html").write_text("test-only website")
    (source / "build-identity.json").write_text(json.dumps(identity))
    assert publisher.publish(root, source, sha, 100, 1) == "published"
    previous = (root / "current").resolve()
    with pytest.raises(ValueError, match="identity mismatch"):
        publisher.publish(root, source, "b" * 40, 101, 1)
    assert (root / "current").resolve() == previous
    assert (root / "current/index.html").read_text() == "test-only website"
