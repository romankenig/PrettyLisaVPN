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


def test_private_download_proxy_retains_owner_auth_and_monitoring():
    source = Path(__file__).resolve().parents[2] / "sites/fleet-dashboard"
    functions = runpy.run_path(str(source / "install.py"))
    template = (source / "dashboard.caddy.template").read_text()
    proxy = functions["test_download_proxy"](template, "admin", "test-only-password-at-least-20")
    assert proxy.index("basic_auth") < proxy.index("handle /dashboard/downloads/*")
    assert "reverse_proxy https://api.test.prettylisavpn.com" in proxy
    assert 'header_up Authorization "Basic ' in proxy
    assert "reverse_proxy backend:8000" in proxy
    assert "method GET HEAD" in proxy
    assert "test-only-password-at-least-20" not in proxy
    assert "root * /etc/caddy/dashboard/site" in proxy
    with pytest.raises(ValueError):
        functions["test_download_proxy"](template, "admin", "injected\nvalue")


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
