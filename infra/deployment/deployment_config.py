"""Persist owner-managed configuration paths and verify running container settings.

Never print Compose output, environment values or provider credentials.
"""

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ENV_FILES = ("FLEET", "DEMO", "CARDLINK", "PLATEGA")


def read_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and not key.startswith("#"):
            values[key] = value.strip().strip("'\"")
    return values


def prepare(environment_file: Path, previous: Path | None, root: Path) -> None:
    if stat.S_IMODE(environment_file.stat().st_mode) != 0o600:
        raise ValueError("Deployment environment file must have mode 600")
    defaults = {
        "DASHBOARD_DIR": str(root / "dashboard"),
        "FLEET_ENV_FILE": str(root / "fleet.env"),
        "FLEET_CREDENTIALS_DIR": str(root / "fleet"),
        "CARDLINK_ENV_FILE": str(root / "cardlink.env"),
        "DEMO_ENV_FILE": "/etc/prettylisavpn/demo.env",
        "PLATEGA_ENV_FILE": "/etc/prettylisavpn/platega.env",
        "PUBLIC_WEBSITE_DIR": "/opt/prettylisavpn/public-website",
    }
    old = read_values(previous) if previous and previous.is_file() else {}
    current = read_values(environment_file)
    selected = {}
    for key, default in defaults.items():
        value = os.environ.get(key) or current.get(key) or old.get(key) or default
        if not Path(value).is_absolute() or any(char in value for char in "\r\n\0'\"$\\"):
            raise ValueError(f"{key} must be an absolute, literal path")
        selected[key] = value
    for prefix in ENV_FILES:
        key = f"{prefix}_ENV_REQUIRED"
        path = Path(selected[f"{prefix}_ENV_FILE"])
        # A previously present file must never silently become optional on update.
        required = path.exists() or current.get(key) == "true" or old.get(key) == "true"
        if required and not path.is_file():
            raise ValueError(f"Required {prefix} environment file is missing")
        if path.is_file() and stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError(f"{prefix} environment file must have mode 600")
        selected[key] = str(required).lower()
    lines = [
        line
        for line in environment_file.read_text().splitlines()
        if line.partition("=")[0] not in selected
    ]
    lines.extend(f"{key}='{value}'" for key, value in selected.items())
    # Keep secret content and permissions; failed validation leaves the original intact.
    descriptor, temporary = tempfile.mkstemp(dir=environment_file.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write("\n".join(lines) + "\n")
        os.replace(temporary, environment_file)
    finally:
        Path(temporary).unlink(missing_ok=True)


def docker_json(arguments: list[str]) -> object:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode:
        raise ValueError("Docker configuration inspection failed (details suppressed)")
    return json.loads(result.stdout)


def verify(environment_file: Path, compose_file: Path, project: str) -> None:
    values = read_values(environment_file)
    compose = [
        "compose",
        "--project-name",
        project,
        "--env-file",
        str(environment_file),
    ]
    compose += ["--file", str(compose_file)]
    fleet = values.get("FLEET_ENV_REQUIRED") == "true"
    if fleet:
        compose += ["--profile", "fleet"]
    config = docker_json([*compose, "config", "--format", "json"])
    assert isinstance(config, dict)
    for service in ("backend", "fleet-worker") if fleet else ("backend",):
        containers = docker_json([*compose, "ps", "--format", "json", service])
        # Compose emits one object for a single container, an array in older versions.
        if isinstance(containers, dict):
            containers = [containers]
        if not isinstance(containers, list) or len(containers) != 1:
            raise ValueError(f"Expected one running {service} container")
        running = docker_json(["inspect", containers[0]["ID"]])
        assert isinstance(running, list)
        container = running[0]
        expected = config["services"][service]
        actual = dict(item.split("=", 1) for item in container["Config"]["Env"])
        if not container["State"]["Running"] or container["Config"]["Image"] != expected["image"]:
            raise ValueError(f"{service} is not running the configured image")
        if any(actual.get(key) != str(value) for key, value in expected["environment"].items()):
            raise ValueError(f"{service} runtime environment differs from persisted configuration")
    print("Running backend/worker configuration matches the persisted release")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--environment-file", required=True, type=Path)
    parser.add_argument("--previous-environment-file", type=Path)
    parser.add_argument("--configuration-root", type=Path)
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument("--project")
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            prepare(
                args.environment_file,
                args.previous_environment_file,
                args.configuration_root or args.environment_file.resolve().parent,
            )
        else:
            if not args.compose_file or not args.project:
                parser.error("verify requires --compose-file and --project")
            verify(args.environment_file, args.compose_file, args.project)
    except (ValueError, OSError, subprocess.TimeoutExpired):
        # Exception messages from parsers/subprocesses can contain secret file content.
        raise SystemExit(
            "Deployment configuration validation failed; no secret values logged"
        ) from None


if __name__ == "__main__":
    main()
