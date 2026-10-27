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
    assert not any(
        key.startswith(("POSTGRES_URL=", "VALKEY_URL=", "EMAIL_SMTP_PASSWORD="))
        for key in config["Env"]
    )
    code = (
        "import importlib.util, os, pathlib, sys; "
        "assert sys.version_info[:2] == (3, 13); assert os.getuid() == 10001; "
        "assert importlib.util.find_spec('alembic') is not None; "
        "assert importlib.util.find_spec('httpx') is not None; "
        "assert all(importlib.util.find_spec(m) is None for m in ('pytest', 'uv', 'mypy')); "
        "assert pathlib.Path('/app/alembic.ini').is_file(); "
        "assert pathlib.Path('/app/migrations/env.py').is_file(); "
        "assert not any(p.name.startswith('.env') or p.suffix in ('.pem', '.key') "
        "for p in pathlib.Path('/app').rglob('*') if not p.is_relative_to('/app/.venv'))"
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
        "OTP_HMAC_SECRET": "docker-test-otp-hmac-secret-at-least-32-characters",
    }


def deployment_env():
    return {
        **production_env(),
        "API_DOMAIN": "api.example.invalid",
        "ACME_EMAIL": "ops@example.invalid",
        "HTTP_PORT": "18080",
        "HTTPS_PORT": "18443",
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
    assert backend["environment"]["OTP_HMAC_SECRET"] == production_env()["OTP_HMAC_SECRET"]
    assert len(backend["ports"]) == 1
    assert backend["ports"][0]["target"] == 8000


@pytest.mark.parametrize("missing", ["POSTGRES_URL", "VALKEY_URL", "OTP_HMAC_SECRET"])
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


def test_vps_compose_exposes_only_caddy_and_uses_external_dependencies():
    result = docker(
        "compose",
        "--project-name",
        "prettylisavpn-test",
        "--env-file",
        str(ROOT / "infra/deployment/.env.example"),
        "-f",
        str(ROOT / "infra/deployment/compose.yaml"),
        "config",
        "--format",
        "json",
        env=deployment_env(),
    )
    config = json.loads(result.stdout)
    assert set(config["services"]) == {"backend", "caddy"}

    backend = config["services"]["backend"]
    assert "ports" not in backend
    assert backend["expose"] == ["8000"]
    assert backend["restart"] == "unless-stopped"
    assert backend["read_only"]
    assert backend["environment"]["POSTGRES_URL"] == deployment_env()["POSTGRES_URL"]
    assert backend["environment"]["VALKEY_URL"] == deployment_env()["VALKEY_URL"]
    assert backend["environment"]["OTP_HMAC_SECRET"] == deployment_env()["OTP_HMAC_SECRET"]
    assert "volumes" not in backend

    caddy = config["services"]["caddy"]
    assert caddy["restart"] == "unless-stopped"
    assert {port["target"] for port in caddy["ports"]} == {80, 443}
    volume_targets = {volume["target"] for volume in caddy["volumes"]}
    assert {"/config", "/data", "/etc/caddy/Caddyfile"} <= volume_targets


def test_caddyfile_is_valid():
    docker(
        "run",
        "--rm",
        "--env",
        "API_DOMAIN=api.example.invalid",
        "--env",
        "ACME_EMAIL=ops@example.invalid",
        "--volume",
        f"{ROOT / 'infra/deployment/Caddyfile'}:/etc/caddy/Caddyfile:ro",
        "caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d",
        "caddy",
        "validate",
        "--config",
        "/etc/caddy/Caddyfile",
    )


def test_fleet_profile_mounts_credentials_only_in_worker(tmp_path):
    fleet_env = tmp_path / "fleet.env"
    fleet_env.write_text(
        "FLEET_ENABLED=true\n"
        "FLEET_ADMIN_TOKEN=administrator-test-token-32-characters\n"
        "FLEET_MONITOR_TOKEN=monitoring-test-token-distinct-32-characters\n"
    )
    result = docker(
        "compose",
        "--profile",
        "fleet",
        "-f",
        str(ROOT / "infra/deployment/compose.yaml"),
        "config",
        "--format",
        "json",
        env={**deployment_env(), "FLEET_ENV_FILE": str(fleet_env)},
    )
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"backend", "caddy", "fleet-worker"}
    assert "volumes" not in services["backend"]
    worker = services["fleet-worker"]
    assert worker["command"] == ["python", "-m", "prettylisavpn.fleet.worker"]
    assert worker["read_only"] and worker["cap_drop"] == ["ALL"]
    assert worker["volumes"][0]["target"] == "/run/fleet"
    assert worker["volumes"][0]["read_only"]
    assert "ports" not in worker
