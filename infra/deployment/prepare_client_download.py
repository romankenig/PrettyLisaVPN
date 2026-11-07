"""Package Chrome/Apple CI outputs, retaining their original build coordinates.

Input must come from the same successful CI run. For manual bootstrap, verify
the run's push/develop provenance and all jobs before invoking this helper.
"""

import argparse
import gzip
import hashlib
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

from publish_client import FILES, PACKAGE_KINDS, SIMULATOR_FILE, SOURCES, archive_version


def prepare(
    directory: Path,
    output: Path,
    platform: str,
    sha: str,
    run: int,
    attempt: int,
    event: str,
) -> None:
    original = json.loads((directory / "build-identity.json").read_text(encoding="utf-8"))
    if (
        original.get("source_sha"),
        str(original.get("run")),
        str(original.get("attempt")),
    ) != (sha, str(run), str(attempt)):
        raise ValueError("Original CI identity mismatch")
    output.mkdir(parents=True, exist_ok=False)
    binary = output / FILES[platform]
    if platform == "chrome":
        with zipfile.ZipFile(binary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(directory.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Unexpected symlink in extension")
                if path.is_file():
                    zip_member = zipfile.ZipInfo(path.relative_to(directory).as_posix())
                    zip_member.compress_type = zipfile.ZIP_DEFLATED
                    zip_member.external_attr = 0o100644 << 16
                    archive.writestr(zip_member, path.read_bytes())
    else:
        shutil.copyfile(directory / FILES[platform], binary)
        # Retain the original corresponding sources/licenses and add an explicit
        # provenance marker for the common atomic publisher. Never extract them.
        with (
            tarfile.open(directory / "corresponding-source-and-licenses.tar.gz", "r:gz") as source,
            (output / SOURCES).open("wb") as destination,
            gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=0) as compressed,
            tarfile.open(fileobj=compressed, mode="w") as target,
        ):
            for member in source:
                if member.name.removeprefix("./") == "source-sha.txt":
                    raise ValueError("Source identity marker already exists")
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
            marker = tarfile.TarInfo("source-sha.txt")
            data = (sha + "\n").encode()
            marker.size = len(data)
            target.addfile(marker, io.BytesIO(data))
    payload = binary.read_bytes()
    identity = {
        "source_sha": sha,
        "run_id": run,
        "run_attempt": attempt,
        "event": event,
        "version": archive_version(payload, platform),
        "package_kind": PACKAGE_KINDS[platform],
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    if platform == "ios":
        simulator = (directory / SIMULATOR_FILE).read_bytes()
        if archive_version(simulator, "ios", simulator=True) != identity["version"]:
            raise ValueError("Simulator and device versions differ")
        (output / SIMULATOR_FILE).write_bytes(simulator)
        identity["simulator"] = {
            "sha256": hashlib.sha256(simulator).hexdigest(),
            "bytes": len(simulator),
        }
    (output / "build-identity.json").write_text(
        json.dumps(identity, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=PACKAGE_KINDS, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument(
        "--event", choices=("push", "pull_request", "workflow_dispatch"), required=True
    )
    args = parser.parse_args()
    prepare(
        args.directory,
        args.output,
        args.platform,
        args.sha,
        args.run,
        args.attempt,
        args.event,
    )


if __name__ == "__main__":
    main()
