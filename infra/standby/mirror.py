#!/usr/bin/env python3
"""Mirror verified, inactive control-plane snapshots. Never start the application."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

PRIMARY_ROOT = Path("/opt/prettylisavpn/standby-export")
STANDBY_ROOT = Path("/opt/prettylisavpn-standby")
SERVICES = ("backend", "caddy", "fleet-worker", "product-analytics")
PROJECT = "prettylisavpn-development"
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def run(args: list[str]) -> str:
    # Command stderr can include configuration: never copy it to the journal.
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed ({result.returncode})")
    return result.stdout


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    path.chmod(0o600)


def safe_relative(value: str) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("Unsafe snapshot path")
    return path


def inventory(root: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Snapshot must not contain symlinks")
        if path.is_file() and path != root / "manifest.json":
            stat = path.stat()
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(path),
                "bytes": stat.st_size,
                "mode": stat.st_mode & 0o777,
                "uid": stat.st_uid,
                "gid": stat.st_gid,
            }
    return result


def snapshot_id(files: dict[str, dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def verify(root: Path, expected: str) -> dict[str, Any]:
    if not HEX64.fullmatch(expected):
        raise ValueError("Invalid snapshot identity")
    manifest: dict[str, Any] = json.loads((root / "manifest.json").read_text())
    if manifest.get("format") != 1 or manifest.get("snapshot_id") != expected:
        raise ValueError("Unexpected manifest")
    for name in manifest["files"]:
        safe_relative(name)
    files = inventory(root)
    if files != manifest["files"] or snapshot_id(files) != expected:
        raise ValueError("Snapshot contents or permissions changed")
    containers = json.loads((root / "containers.json").read_text())
    expected_images = sorted({c["Image"] for c in containers})
    if manifest["images"] != expected_images:
        raise ValueError("Image list differs from captured runtime")
    for image_id in expected_images:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Invalid image identity")
        if f"images/{image_id[7:]}.tar.gz" not in files:
            raise ValueError("Missing image archive")
    return manifest


def prune_snapshots(root: Path, current: str) -> None:
    candidates = [
        p
        for p in (root / "snapshots").iterdir()
        if HEX64.fullmatch(p.name) and p.is_dir() and not p.is_symlink()
    ]
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    keep = {current, *[p.name for p in candidates if p.name != current][:2]}
    for candidate in candidates:
        if candidate.name not in keep:
            shutil.rmtree(candidate)
    if root == PRIMARY_ROOT:
        referenced = {
            p.name
            for d in (root / "snapshots").iterdir()
            if d.is_dir() and not d.is_symlink()
            for p in (d / "images").glob("*.tar.gz")
        }
        for archive in (root / "images").glob("*.tar.gz"):
            if archive.name not in referenced:
                archive.unlink()


def prune_imported_images(root: Path, owned: set[str]) -> None:
    retained = {
        image_id
        for snapshot in (root / "snapshots").iterdir()
        if HEX64.fullmatch(snapshot.name) and not snapshot.is_symlink()
        for image_id in json.loads((snapshot / "manifest.json").read_text())["images"]
    }
    for image_id in sorted(owned - retained):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
            raise ValueError("Invalid imported image identity")
        try:
            # Never force removal or prune unrelated/pre-existing Docker images.
            run(["docker", "image", "rm", image_id])
        except RuntimeError:
            continue
        owned.remove(image_id)
    write_json(root / "imported-images.next", sorted(owned))
    (root / "imported-images.next").replace(root / "imported-images.json")


def discard_abandoned_staging(root: Path, *, keep: str | None = None) -> None:
    # Caller holds the process-wide lock. Only task-owned scratch names qualify.
    for candidate in root.iterdir():
        managed = (
            candidate.name.startswith("preparing-")
            if keep is None
            else bool(HEX64.fullmatch(candidate.name))
        )
        if managed and candidate.name != keep and candidate.is_dir() and not candidate.is_symlink():
            shutil.rmtree(candidate)


def copy_file(source: Path, target: Path, *, immutable: bool = False) -> None:
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if immutable:
        try:
            os.link(source, target)
            return
        except OSError:
            pass
    shutil.copy2(source, target)
    stat = source.stat()
    os.chown(target, stat.st_uid, stat.st_gid)


def copy_tree(
    source: Path, target: Path, *, immutable: bool = False, boundary: Path | None = None
) -> None:
    # Only explicit production mount roots are traversed; materialize current
    # symlinks so the mirror never relies on older publisher directories.
    real = source.resolve(strict=True)
    if boundary is None:
        boundary = source.parent.resolve() if source.name in {"current", "site"} else real
    if not real.is_relative_to(boundary):
        raise ValueError("Unexpected link outside a selected source tree")
    if real.is_file():
        copy_file(real, target, immutable=immutable)
        return
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copystat(real, target)
    stat = real.stat()
    os.chown(target, stat.st_uid, stat.st_gid)
    for child in real.iterdir():
        resolved = child.resolve(strict=True)
        if not resolved.is_relative_to(boundary):
            raise ValueError("Unexpected link outside a selected source tree")
        copy_tree(child, target / child.name, immutable=immutable, boundary=boundary)


def inspect_live() -> list[dict[str, Any]]:
    containers: list[dict[str, Any]] = json.loads(
        run(["docker", "inspect", *[f"{PROJECT}-{s}-1" for s in SERVICES]])
    )
    for container in containers:
        if container["State"]["Status"] != "running":
            raise RuntimeError("Primary service is not running")
    if containers[0]["State"].get("Health", {}).get("Status") != "healthy":
        raise RuntimeError("Primary API is unhealthy")
    return containers


def stable_containers(containers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Omit mutable healthcheck history/statistics, retain the actual effective
    # environment (including owner-managed settings) and runtime image IDs.
    return [
        {k: c[k] for k in ("Id", "Name", "Image", "Config", "HostConfig", "Mounts")}
        for c in containers
    ]


def image_archive(image_id: str, cache: Path) -> Path:
    identity = image_id.removeprefix("sha256:")
    if not HEX64.fullmatch(identity):
        raise ValueError("Invalid image identity")
    target = cache / f"{identity}.tar.gz"
    if target.is_file():
        return target
    temporary = target.with_suffix(".partial")
    process = subprocess.Popen(
        ["docker", "save", image_id], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    try:
        assert process.stdout is not None
        with gzip.open(temporary, "wb", compresslevel=1) as output:
            shutil.copyfileobj(process.stdout, output, 1024 * 1024)
        if process.wait() != 0:
            raise RuntimeError("Image export failed")
        temporary.replace(target)
        return target
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        temporary.unlink(missing_ok=True)


def select_sources(containers: list[dict[str, Any]]) -> list[tuple[Path, bool]]:
    release = Path("/opt/prettylisavpn/current").resolve(strict=True)
    if not release.is_relative_to("/opt/prettylisavpn/releases"):
        raise ValueError("Unexpected primary release directory")
    paths: list[tuple[Path, bool]] = []
    for name in (
        "compose.yaml",
        "Caddyfile",
        "deployment.env",
        "runtime-identity.json",
        "image-id",
    ):
        source = release / name
        if source.is_file():
            paths.append((source, False))
    for source in Path("/etc/prettylisavpn").glob("*.env"):
        paths.append((source, False))
    secrets = Path("/opt/prettylisavpn/secrets")
    for name in ("deployment.env", "fleet.env", "node-agent.env", "vpn.env"):
        if (secrets / name).is_file():
            paths.append((secrets / name, False))
    dashboard = secrets / "dashboard"
    for source in dashboard.glob("*.caddy"):
        paths.append((source, False))
    for name in ("login.json", "test-download-login.json"):
        if (dashboard / name).is_file():
            paths.append((dashboard / name, False))
    paths.extend(
        [
            (dashboard / "site", True),
            (dashboard / "downloads/current", True),
            (Path("/opt/prettylisavpn/public-website/current"), True),
        ]
    )
    covered = {
        str(dashboard),
        str(dashboard / "downloads"),
        "/opt/prettylisavpn/public-website",
    }
    for container in containers:
        for mount in container["Mounts"]:
            source = Path(mount["Source"])
            if str(source) in covered or any(source == p for p, _ in paths):
                continue
            if not any(
                source.is_relative_to(p)
                for p in (
                    "/opt/prettylisavpn",
                    "/etc/prettylisavpn",
                    "/var/lib/docker/volumes",
                )
            ):
                raise ValueError("Unexpected runtime mount; extend the reviewed mirror allowlist")
            paths.append((source, False))
            covered.add(str(source))
    return paths


def prepare() -> None:
    if "95.140.152.42" not in run(["hostname", "-I"]).split():
        raise RuntimeError("Snapshot export is restricted to the production primary")
    root = PRIMARY_ROOT
    for child in ("snapshots", "images"):
        (root / child).mkdir(parents=True, exist_ok=True, mode=0o700)
    discard_abandoned_staging(root)
    before = stable_containers(inspect_live())
    sources = select_sources(before)
    pointers = {str(p): str(p.resolve()) for p, _ in sources}
    stage = Path(tempfile.mkdtemp(prefix="preparing-", dir=root))
    try:
        write_json(stage / "containers.json", before)
        write_json(
            stage / "source.json",
            {
                "primary": "95.140.152.42",
                "release": str(Path("/opt/prettylisavpn/current").resolve()),
                "pointers": pointers,
            },
        )
        for source, immutable in sources:
            copy_tree(source, stage / "rootfs" / str(source).lstrip("/"), immutable=immutable)
        image_ids = sorted({c["Image"] for c in before})
        for identity in image_ids:
            archive = image_archive(identity, root / "images")
            copy_file(archive, stage / "images" / archive.name, immutable=True)
        if before != stable_containers(inspect_live()) or pointers != {
            str(p): str(p.resolve()) for p, _ in select_sources(before)
        }:
            raise RuntimeError("Primary changed during snapshot; retry after deployment")
        files = inventory(stage)
        identity = snapshot_id(files)
        write_json(
            stage / "manifest.json",
            {
                "format": 1,
                "snapshot_id": identity,
                "created_at_unix": int(time.time()),
                "images": image_ids,
                "files": files,
            },
        )
        destination = root / "snapshots" / identity
        if not destination.exists():
            stage.rename(destination)
        else:
            verify(destination, identity)
        write_json(
            root / "latest.next",
            {"snapshot_id": identity, "checked_at_unix": int(time.time())},
        )
        (root / "latest.next").replace(root / "latest.json")
        prune_snapshots(root, identity)
        print(json.dumps({"event": "standby_snapshot_prepared", "snapshot_id": identity}))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def pull() -> None:
    root = STANDBY_ROOT
    if (root / "ACTIVE").exists():
        raise RuntimeError("Standby is active; automatic mirroring is fenced")
    if "130.0.234.51" not in run(["hostname", "-I"]).split():
        raise RuntimeError("Snapshot import is restricted to the designated standby")
    config = Path("/etc/prettylisavpn-standby")
    ssh = (
        f"ssh -i {config}/mirror_key -o BatchMode=yes -o StrictHostKeyChecking=yes "
        f"-o UserKnownHostsFile={config}/known_hosts -o ConnectTimeout=10"
    )
    common = ["rsync", "-a", "--numeric-ids", "--timeout=90", "-e", ssh]
    incoming = root / "incoming"
    incoming.mkdir(parents=True, exist_ok=True, mode=0o700)
    run([*common, "root@95.140.152.42:latest.json", str(incoming / "latest.json")])
    latest = json.loads((incoming / "latest.json").read_text())
    identity = latest["snapshot_id"]
    if not isinstance(identity, str) or not HEX64.fullmatch(identity):
        raise ValueError("Invalid remote snapshot identity")
    discard_abandoned_staging(incoming, keep=identity)
    destination = root / "snapshots" / identity
    stage = destination if destination.exists() else incoming / identity
    if not destination.exists():
        stage.mkdir(exist_ok=True, mode=0o700)
        reuse = (
            [f"--link-dest={(root / 'current').resolve()}"] if (root / "current").exists() else []
        )
        run(
            [
                *common,
                *reuse,
                "--delete",
                f"root@95.140.152.42:snapshots/{identity}/",
                str(stage) + "/",
            ]
        )
    manifest = verify(stage, identity)
    if (root / "ACTIVE").exists():
        raise RuntimeError("Activation occurred during mirroring; refusing promotion")
    ledger = root / "imported-images.json"
    owned = set(json.loads(ledger.read_text())) if ledger.exists() else set()
    for image_id in manifest["images"]:
        try:
            run(["docker", "image", "inspect", image_id])
        except RuntimeError:
            run(
                [
                    "docker",
                    "load",
                    "--input",
                    str(stage / "images" / (image_id.removeprefix("sha256:") + ".tar.gz")),
                ]
            )
            owned.add(image_id)
            write_json(root / "imported-images.next", sorted(owned))
            (root / "imported-images.next").replace(ledger)
        run(["docker", "image", "inspect", image_id])
    if stage != destination:
        stage.rename(destination)
    next_pointer = root / "current.next"
    next_pointer.unlink(missing_ok=True)
    next_pointer.symlink_to(Path("snapshots") / identity)
    next_pointer.replace(root / "current")
    write_json(
        root / "status.json",
        {
            "state": "STAGED_NOT_ACTIVE",
            "snapshot_id": identity,
            "synced_at_unix": int(time.time()),
            "primary_checked_at_unix": latest["checked_at_unix"],
        },
    )
    prune_snapshots(root, identity)
    prune_imported_images(root, owned)
    print(
        json.dumps(
            {
                "event": "standby_snapshot_verified",
                "snapshot_id": identity,
                "application_started": False,
            }
        )
    )


def main() -> None:
    import fcntl

    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "pull"])
    args = parser.parse_args()
    with Path("/run/prettylisavpn-standby-mirror.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            (prepare if args.operation == "prepare" else pull)()
        except Exception as error:  # noqa: BLE001 - redact all configuration-bearing failures
            print(
                json.dumps(
                    {
                        "event": "standby_mirror_failed",
                        "error_type": type(error).__name__,
                    }
                )
            )
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
