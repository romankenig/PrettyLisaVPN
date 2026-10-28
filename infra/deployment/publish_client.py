"""Publish verified development clients atomically behind dashboard authentication."""

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FILES = {"android": "app-debug.apk", "windows": "PrettyLisaVPN.exe"}
DOWNLOADS = {"android": "android.apk", "windows": "windows.exe"}
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def order(entry: dict[str, Any]) -> tuple[int, ...]:
    return (
        *map(int, entry["version"].split(".")),
        entry["run_id"],
        entry["run_attempt"],
    )


def validate(
    directory: Path, platform: str, sha: str, run: int, attempt: int
) -> tuple[dict[str, Any], bytes]:
    if platform not in FILES or not re.fullmatch(r"[0-9a-f]{40}", sha) or run < 1 or attempt < 1:
        raise ValueError("Invalid build coordinates")
    identity = json.loads((directory / "build-identity.json").read_text(encoding="utf-8-sig"))
    if (
        identity["source_sha"] != sha
        or str(identity["run_id"]) != str(run)
        or str(identity["run_attempt"]) != str(attempt)
        or identity.get("pr_head_sha")
    ):
        raise ValueError("Build identity does not match the trusted develop push")
    android = platform == "android"
    version = identity["version_name" if android else "version"]
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Invalid client version")
    if android and (
        identity.get("application_id") != "com.prettylisavpn.android.dev"
        or identity.get("apk") != FILES[platform]
        or identity.get("event") != "push"
    ):
        raise ValueError("Unexpected Android build")
    binary = directory / FILES[platform]
    if binary.is_symlink() or not 0 < binary.stat().st_size <= 512 * 1024 * 1024:
        raise ValueError("Invalid binary file")
    payload = binary.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != identity["apk_sha256" if android else "sha256"]:
        raise ValueError("Binary checksum mismatch")
    if not payload.startswith(b"PK\x03\x04" if android else b"MZ"):
        raise ValueError("Unexpected binary format")
    if not android and identity.get("bytes") != len(payload):
        raise ValueError("Binary size mismatch")
    return {
        "version": version,
        "source_sha": sha,
        "run_id": run,
        "run_attempt": attempt,
        "sha256": digest,
        "bytes": len(payload),
        "url": "/dashboard/downloads/" + DOWNLOADS[platform],
        "published_at": datetime.now(UTC).isoformat(),
    }, payload


def publish(root: Path, directory: Path, platform: str, sha: str, run: int, attempt: int) -> str:
    # Only used on the Linux main server. A shared lock serializes both platforms.
    import fcntl

    entry, payload = validate(directory, platform, sha, run, attempt)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = root / "current" / "index.json"
        catalog = json.loads(current.read_text()) if current.exists() else {"clients": {}}
        clients = catalog["clients"]
        previous = clients.get(platform)
        if previous:
            if order(entry) < order(previous):
                return "superseded"
            if order(entry) == order(previous):
                if any(entry[key] != previous[key] for key in ("sha256", "source_sha")):
                    raise ValueError("Conflicting immutable build")
                return "unchanged"

        release = root / "releases" / platform / f"{run}-{attempt}"
        release.parent.mkdir(parents=True, exist_ok=True)
        if release.exists():
            if (
                json.loads((release / "identity.json").read_text())["source_sha"] != sha
                or hashlib.sha256((release / DOWNLOADS[platform]).read_bytes()).hexdigest()
                != entry["sha256"]
            ):
                raise ValueError("Conflicting stored build")
        else:
            stage = Path(tempfile.mkdtemp(prefix="pending-", dir=release.parent))
            (stage / DOWNLOADS[platform]).write_bytes(payload)
            (stage / "identity.json").write_text(json.dumps(entry))
            stage.rename(release)

        clients[platform] = entry
        snapshots = root / "snapshots"
        snapshots.mkdir(exist_ok=True)
        snapshot = Path(tempfile.mkdtemp(prefix="catalog-", dir=snapshots))
        for client, item in clients.items():
            target = (
                f"../../releases/{client}/{item['run_id']}-{item['run_attempt']}/"
                + DOWNLOADS[client]
            )
            (snapshot / DOWNLOADS[client]).symlink_to(target)
        (snapshot / "index.json").write_text(
            json.dumps({"schema": 1, "clients": clients}, indent=2) + "\n"
        )
        # One pointer switches catalog and both binaries together. Readers never
        # see a partially copied APK/EXE; the other platform remains available.
        link = root / "current.next"
        link.unlink(missing_ok=True)
        link.symlink_to("snapshots/" + snapshot.name)
        link.replace(root / "current")
        return "published"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=FILES, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run as root on the main server")
    os.umask(0o077)
    result = publish(
        Path("/opt/prettylisavpn/secrets/dashboard/downloads"),
        args.directory,
        args.platform,
        args.sha,
        args.run,
        args.attempt,
    )
    print(json.dumps({"platform": args.platform, "result": result, "run": args.run}))


if __name__ == "__main__":
    main()
