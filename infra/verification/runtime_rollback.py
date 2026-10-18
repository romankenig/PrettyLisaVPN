"""One-time development rollback/restore check with an unconditional restore attempt."""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/prettylisavpn")
OLD_VERSION = "dev-1938d4d32eb58fd097e7c8840f695b735ec86b8f"
OLD_IMAGE_ID = "sha256:51b825d271f21e3555045d9dc5a9c4146ded8795e7ce505fead89ca14c7a4d11"


class VerificationError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def run(args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, "command_failed:" + args[0])
    return result.stdout.strip()


def public_environment(path):
    require(path.is_file(), "missing_env_file")
    require(stat.S_IMODE(path.stat().st_mode) == 0o600, "env_mode_must_be_0600")
    allowed = {"BACKEND_IMAGE", "APPLICATION_VERSION", "ENVIRONMENT", "API_DOMAIN", "COMPOSE_PROJECT_NAME"}
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key in allowed:
            values[key] = value.strip().strip("'\"")
    require(values.get("ENVIRONMENT") == "development", "environment_is_not_development")
    require(values.get("API_DOMAIN") == "api.prettylisavpn.com", "wrong_api_domain")
    require(values.get("COMPOSE_PROJECT_NAME") == "prettylisavpn-development", "wrong_compose_project")
    return values


def image_id(image):
    return run(["docker", "image", "inspect", "--format", "{{.Id}}", image])


def observe(expected_version, expected_image_id):
    containers = run([
        "docker", "ps", "--filter", "label=com.docker.compose.project=prettylisavpn-development",
        "--filter", "label=com.docker.compose.service=backend", "--format", "{{.ID}}",
    ]).splitlines()
    require(len(containers) == 1, "expected_one_development_backend")
    container = containers[0]
    actual_image = run(["docker", "inspect", "--format", "{{.Image}}", container])
    require(actual_image == expected_image_id, "running_image_id_mismatch")
    health = run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container])
    require(health == "healthy", "container_not_healthy")
    revision_output = run(["docker", "exec", container, "alembic", "current"])
    revisions = re.findall(r"(?m)^([0-9]{4}_[a-z0-9_]+)", revision_output)
    require(revisions == ["0017_profile_evidence"], "database_revision_changed")
    endpoints = {}
    for endpoint in ("health", "ready", "version"):
        last_error = None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(
                    "https://api.prettylisavpn.com/" + endpoint, timeout=10
                ) as response:
                    require(response.status == 200, "public_http_not_200:" + endpoint)
                    endpoints[endpoint] = json.loads(response.read(16385))
                last_error = None
                break
            except (OSError, ValueError, urllib.error.URLError) as exc:
                last_error = exc
                if attempt < 5:
                    time.sleep(2)
        require(last_error is None, "public_probe_failed:" + endpoint)
    require(endpoints["health"].get("status") == "ok", "health_not_ok")
    require(endpoints["ready"].get("status") == "ready", "api_not_ready")
    require(
        endpoints["ready"].get("dependencies") == {"postgresql": True, "valkey": True},
        "dependencies_not_ready",
    )
    require(endpoints["version"].get("environment") == "development", "wrong_public_environment")
    require(endpoints["version"].get("application_name") == "PrettyLisaVPN", "wrong_application")
    require(endpoints["version"].get("application_version") == expected_version, "public_version_mismatch")
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "container_id": container, "image_id": actual_image, "container_health": health,
        "alembic_revision": revisions[0], "http_status": {key: 200 for key in endpoints},
        "ready": endpoints["ready"], "version": endpoints["version"],
    }


def driver(release, env_file):
    print("Running retained-artifact driver in rollback mode", file=sys.stderr, flush=True)
    # Both rollback and restore skip migrations, pull and rebuild.
    run(["bash", str(release / "deploy.sh"), str(env_file), "rollback"], timeout=300)


def publish_current(release, env_file):
    canonical = ROOT / "secrets/deployment.env"
    staged_env = canonical.with_name("deployment.env.rollback-verification-next")
    shutil.copyfile(env_file, staged_env)
    staged_env.chmod(0o600)
    os.replace(staged_env, canonical)
    link = ROOT / "current.rollback-verification-next"
    if link.is_symlink():
        link.unlink()
    link.symlink_to(release)
    os.replace(link, ROOT / "current")


def recovery_cycle(rollback, restore):
    """Always attempt restore, including after a partial or failed rollback."""
    error = None
    try:
        rollback()
    except Exception as exc:
        error = exc
    finally:
        restore()
    if error is not None:
        raise error


def verify(expected_sha, run_id, attempt, report):
    require(re.fullmatch(r"[0-9a-f]{40}", expected_sha), "invalid_expected_sha")
    require(re.fullmatch(r"[1-9][0-9]*", run_id), "invalid_run_id")
    require(re.fullmatch(r"[1-9][0-9]*", attempt), "invalid_attempt")
    current = (ROOT / "current").resolve(strict=True)
    require(current.parent == ROOT / "releases", "current_outside_releases")
    identity = json.loads((current / "runtime-identity.json").read_text())
    require(identity.get("source_sha") == expected_sha, "another_revision_is_deployed")
    require(identity.get("channel") == "development", "wrong_deployment_channel")
    expected_version = "0.1.0-dev." + identity["run_id"] + "+g" + expected_sha
    require(identity.get("application_version") == expected_version, "unexpected_new_runtime_version")
    new_env = current / "deployment.env"
    old_env = current / "previous.env"
    new_values = public_environment(new_env)
    old_values = public_environment(old_env)
    require(new_values.get("APPLICATION_VERSION") == expected_version, "new_env_version_mismatch")
    require(old_values.get("APPLICATION_VERSION") == OLD_VERSION, "unexpected_rollback_version")
    require(new_env.read_bytes() == (ROOT / "secrets/deployment.env").read_bytes(), "canonical_env_changed")
    new_image_id = (current / "image-id").read_text().strip()
    require(image_id(new_values["BACKEND_IMAGE"]) == new_image_id, "new_retained_image_mismatch")
    old_image_id = (current / "previous-image-id").read_text().strip()
    require(old_image_id == OLD_IMAGE_ID, "previous_image_does_not_match_preflight")
    require(image_id(old_values["BACKEND_IMAGE"]) == old_image_id, "old_retained_image_mismatch")
    previous = Path((current / "previous-release").read_text().strip()).resolve(strict=True)
    require(previous.parent == ROOT / "releases", "previous_release_outside_releases")
    names = ("compose.yaml", "compose.node-agent.yaml", "Caddyfile")
    for name in names:
        require((previous / name).read_bytes() == (current / name).read_bytes(), "compose_changed:" + name)
    require("keeping the database schema unchanged" in (current / "deploy.sh").read_text(), "driver_has_no_rollback_mode")
    report.update({
        "expected_source_sha": expected_sha, "deployment_identity": identity,
        "new_release": str(current), "original_previous_release": str(previous),
        "before": observe(expected_version, new_image_id),
    })
    baseline = ROOT / "rollback-baselines" / (run_id + "-attempt-" + attempt)
    baseline.parent.mkdir(mode=0o700, exist_ok=True)
    baseline.mkdir(mode=0o700)
    for name in names:
        shutil.copyfile(previous / name, baseline / name)
    # Preserve the exact legacy Compose/env; use the new driver so it can skip migrations.
    shutil.copyfile(current / "deploy.sh", baseline / "deploy.sh")
    shutil.copyfile(old_env, baseline / "deployment.env")
    (baseline / "deployment.env").chmod(0o600)
    (baseline / "image-id").write_text(old_image_id + "\n")
    (baseline / "source-release").write_text(str(previous) + "\n")
    report["rollback_baseline"] = str(baseline)

    def rollback():
        print("phase=rollback_started", file=sys.stderr, flush=True)
        driver(baseline, baseline / "deployment.env")
        report["rollback"] = observe(OLD_VERSION, old_image_id)
        publish_current(baseline, baseline / "deployment.env")
        print("phase=rollback_verified", file=sys.stderr, flush=True)

    def restore():
        print("phase=restore_started", file=sys.stderr, flush=True)
        last_error = None
        for number in range(1, 3):
            try:
                driver(current, new_env)
                report["restore"] = observe(expected_version, new_image_id)
                publish_current(current, new_env)
                report["restore_attempt"] = number
                last_error = None
                break
            except Exception as exc:
                last_error = exc
        require(last_error is None, "restore_failed_after_two_attempts")
        require((ROOT / "current").resolve() == current, "restored_current_mismatch")
        require((ROOT / "secrets/deployment.env").read_bytes() == new_env.read_bytes(), "restored_env_mismatch")
        print("phase=restore_verified", file=sys.stderr, flush=True)

    recovery_cycle(rollback, restore)
    report["passed"] = True
    report["database_schema_changed"] = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args()
    report = {"passed": False, "run_id": args.run, "run_attempt": args.attempt}
    try:
        verify(args.expected_sha, args.run, args.attempt, report)
    except Exception as exc:
        report["error"] = str(exc) if isinstance(exc, VerificationError) else type(exc).__name__
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
