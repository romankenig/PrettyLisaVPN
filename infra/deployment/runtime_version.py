"""Render runtime identity without changing the Python package version."""

import argparse
import json
import re
import tomllib
from pathlib import Path


def runtime_identity(base: str, sha: str, run: str, attempt: str, channel: str) -> dict[str, str]:
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", base):
        raise ValueError("Package version must be MAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("A full lowercase commit SHA is required")
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (run, attempt)):
        raise ValueError("Run and attempt must be positive integers")
    if channel not in {"development", "preview", "release"}:
        raise ValueError("Unsupported channel")
    suffix = "" if channel == "release" else f"-dev.{run}"
    return {
        "application_version": f"{base}{suffix}+g{sha}",
        "image": f"prettylisavpn-backend:{sha}-run-{run}-attempt-{attempt}",
        "release_id": f"{sha}-run-{run}-attempt-{attempt}",
        "source_sha": sha,
        "run_id": run,
        "run_attempt": attempt,
        "channel": channel,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--channel", choices=("development", "preview", "release"), required=True)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "backend/pyproject.toml"
    base = tomllib.loads(manifest.read_text())["project"]["version"]
    print(json.dumps(runtime_identity(base, args.sha, args.run, args.attempt, args.channel)))


if __name__ == "__main__":
    main()
