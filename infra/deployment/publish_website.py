"""Atomically install a verified static website without changing business data."""

import argparse
import json
import os
import re
import shutil
from pathlib import Path


def publish(root: Path, source: Path, sha: str, run: int, attempt: int) -> str:
    import fcntl

    if not re.fullmatch(r"[0-9a-f]{40}", sha) or min(run, attempt) < 1:
        raise ValueError("Invalid build coordinates")
    identity = json.loads((source / "build-identity.json").read_text())
    if (
        identity.get("source_sha"),
        str(identity.get("run_id")),
        str(identity.get("run_attempt")),
    ) != (sha, str(run), str(attempt)):
        raise ValueError("Website build identity mismatch")
    if not (source / "index.html").is_file():
        raise ValueError("Website index missing")
    for path in source.rglob("*"):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("Unexpected website file type")
    root.mkdir(parents=True, exist_ok=True)
    with (root / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = root / "current" / "build-identity.json"
        if current.exists():
            old = json.loads(current.read_text())
            if (int(old.get("run_id") or 0), int(old.get("run_attempt") or 0)) > (run, attempt):
                return "superseded"
        release = root / "releases" / f"{sha}-{run}-{attempt}"
        release.parent.mkdir(exist_ok=True)
        # Reruns have their own attempt; never overwrite immutable stored files.
        shutil.copytree(source, release)
        temporary = root / "current.next"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to("releases/" + release.name)
        temporary.replace(root / "current")
    return "published"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    args = parser.parse_args()
    os.umask(0o022)
    print(
        publish(
            Path("/opt/prettylisavpn/public-website"), args.source, args.sha, args.run, args.attempt
        )
    )


if __name__ == "__main__":
    main()
