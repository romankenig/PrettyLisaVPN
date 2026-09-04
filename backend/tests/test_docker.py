"""Opt-in checks of the built runtime and standalone deployment configuration."""

import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(os.getenv("RUN_DOCKER_TESTS") != "1", reason="Set RUN_DOCKER_TESTS=1"),
]
ROOT = Path(__file__).resolve().parents[2]
IMAGE = os.getenv("DOCKER_TEST_IMAGE", "prettylisavpn-backend:test")


def docker(*args, env=None, check=True):
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=check, env=env, timeout=60
    )


def test_runtime_image_configuration():
    config = json.loads(docker("image", "inspect", IMAGE).stdout)[0]["Config"]
    assert config["User"] == "10001:10001"
    assert set(config["ExposedPorts"]) == {"8000/tcp"}
    assert config["StopSignal"] == "SIGTERM"
    assert config["Healthcheck"]["Test"][0] == "CMD"
    assert "/health" in config["Healthcheck"]["Test"][-1]
    assert not any(key.startswith(("POSTGRES_URL=", "VALKEY_URL=")) for key in config["Env"])
    code = (
        "import importlib.util, os, pathlib, sys; "
        "assert sys.version_info[:2] == (3, 13); assert os.getuid() == 10001; "
        "assert all(importlib.util.find_spec(m) is None for m in ('pytest', 'uv', 'mypy')); "
        "assert not any(p.name.startswith('.env') or p.suffix in ('.pem', '.key') "
        "for p in pathlib.Path('/app').rglob('*'))"
    )
    docker("run", "--rm", IMAGE, "python", "-c", code)


def test_liveness_without_dependencies_and_graceful_shutdown():
    name = f"prettylisa-smoke-{uuid4().hex[:12]}"
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=16m",
        "--health-interval=1s",
        "--health-start-period=1s",
        "--network=none",
        IMAGE,
    )
    try:
        for _ in range(30):
            state = json.loads(docker("inspect", name).stdout)[0]["State"]
            if state["Health"]["Status"] == "healthy":
                break
            time.sleep(0.25)
        else:
            pytest.fail("Container liveness did not become healthy without dependencies")
        # The image's healthcheck must stay healthy when readiness returns 503.
        code = (
            "import urllib.error, urllib.request; "
            "\ntry: urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5)"
            "\nexcept urllib.error.HTTPError as exc: assert exc.code == 503"
            "\nelse: raise AssertionError('Expected 503 without dependencies')"
        )
        docker("exec", name, "python", "-c", code)
        docker("stop", "--time", "30", name)
        state = json.loads(docker("inspect", name).stdout)[0]["State"]
        assert state["ExitCode"] == 0
        logs = docker("logs", name)
        assert "application_stopped" in logs.stdout + logs.stderr
    finally:
        docker("rm", "-f", name, check=False)


def production_env():
    return {
        **os.environ,
        "BACKEND_IMAGE": IMAGE,
        "APPLICATION_VERSION": "0.1.0",
        "POSTGRES_URL": "postgresql+asyncpg://example:example@external-postgres/example",
        "VALKEY_URL": "redis://external-valkey/0",
    }


def test_production_compose_has_only_backend():
    result = docker(
        "compose",
        "-f",
        str(ROOT / "infra/docker/compose.production.yaml"),
        "config",
        "--format",
        "json",
        env=production_env(),
    )
    config = json.loads(result.stdout)
    assert set(config["services"]) == {"backend"}
    backend = config["services"]["backend"]
    assert "build" not in backend
    assert "depends_on" not in backend
    assert backend["read_only"]
    assert backend["environment"]["ENVIRONMENT"] == "production"
    assert backend["environment"]["POSTGRES_URL"] == production_env()["POSTGRES_URL"]
    assert backend["environment"]["VALKEY_URL"] == production_env()["VALKEY_URL"]
    assert len(backend["ports"]) == 1
    assert backend["ports"][0]["target"] == 8000


@pytest.mark.parametrize("missing", ["POSTGRES_URL", "VALKEY_URL"])
def test_production_compose_rejects_missing_dependency_urls(missing):
    env = production_env()
    env[missing] = ""
    result = docker(
        "compose",
        "-f",
        str(ROOT / "infra/docker/compose.production.yaml"),
        "config",
        "--quiet",
        env=env,
        check=False,
    )
    assert result.returncode != 0
    assert missing in result.stderr
