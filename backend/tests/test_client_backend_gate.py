"""Publication waits for the matching ready backend, without changing product versions."""

import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wait_backend", Path(__file__).resolve().parents[2] / "infra/deployment/wait_backend.py"
)
assert SPEC is not None and SPEC.loader is not None
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
VERSION = {
    "application_name": "PrettyLisaVPN",
    "application_version": "0.54.0-dev.123+g" + "a" * 40,
    "environment": "development",
}
READY = {"status": "ready", "dependencies": {"postgresql": True, "valkey": True}}


def test_exact_ready_backend():
    assert GATE.matches(VERSION, READY, "0.54.0")
    assert not GATE.matches(VERSION, READY, "0.53.0")
    assert not GATE.matches(VERSION, READY, "0.55.0")


@pytest.mark.parametrize(
    "change",
    [
        {"application_name": "other"},
        {"environment": "production"},
        {"application_version": "0.54.0"},
        {"application_version": "0.54.0-dev.123+gshort"},
        {"application_version": None},
    ],
)
def test_rejects_wrong_identity(change):
    assert not GATE.matches(VERSION | change, READY, "0.54.0")


@pytest.mark.parametrize("ready", [None, [], {}, {"status": "ready"}, READY | {"status": "error"}])
def test_rejects_unready(ready):
    assert not GATE.matches(VERSION, ready, "0.54.0")


def test_waits_through_network_error_and_old_version():
    payloads = [
        URLError("unavailable"),
        io.BytesIO(json.dumps(VERSION | {"application_version": "0.53.0"}).encode()),
        io.BytesIO(json.dumps(READY).encode()),
        io.BytesIO(json.dumps(VERSION).encode()),
        io.BytesIO(json.dumps(READY).encode()),
    ]
    with (
        patch.object(GATE, "urlopen", side_effect=payloads) as request,
        patch.object(GATE.time, "sleep") as sleep,
    ):
        GATE.wait_backend("https://api.example.test", "0.54.0", 60)
    assert request.call_count == 5
    assert sleep.call_count == 2


def test_timeout_fails_closed():
    with (
        patch.object(GATE.time, "monotonic", side_effect=[0, 0, 2, 2]),
        patch.object(GATE.time, "sleep"),
        patch.object(GATE, "urlopen", side_effect=URLError("unavailable")),
        pytest.raises(TimeoutError, match="publication remains blocked"),
    ):
        GATE.wait_backend("https://api.example.test", "0.54.0", 1)


@pytest.mark.parametrize(
    "url", ["http://api.test", "https://a:b@api.test", "https://api.test/path"]
)
def test_invalid_origin(url):
    with pytest.raises(ValueError), patch.object(GATE, "urlopen") as request:
        GATE.wait_backend(url, "0.54.0", 60)
    request.assert_not_called()
