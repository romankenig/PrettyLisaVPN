"""Publish verified development clients atomically behind dashboard authentication."""

import argparse
import hashlib
import io
import json
import os
import plistlib
import re
import tarfile
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FILES = {
    "android": "app-debug.apk",
    "windows": "PrettyLisaVPN.exe",
    "chrome": "PrettyLisaVPN-Chrome.zip",
    "ios": "PrettyLisaVPN-iOS-device-unsigned.zip",
    "macos": "PrettyLisaVPN-macOS-release-unsigned.zip",
}
DOWNLOADS = {
    "android": "android.apk",
    "windows": "windows.exe",
    "chrome": "chrome-extension.zip",
    "ios": "ios-unsigned.zip",
    "macos": "macos-unsigned.zip",
}
PACKAGE_KINDS = {
    "chrome": "unpacked-extension",
    "ios": "unsigned-app",
    "macos": "unsigned-app",
}
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
SOURCES = "managed-source.tar.gz"
SIMULATOR_FILE = "PrettyLisaVPN-iOS-Simulator.zip"
SIMULATOR_DOWNLOAD = "ios-simulator.zip"


def sources(directory: Path, platform: str, version: str, sha: str) -> dict[str, bytes]:
    if platform == "chrome":
        return {}
    minimum = (0, 15, 0) if platform == "android" else (0, 18, 0)
    if platform in ("android", "windows") and tuple(map(int, version.split("."))) < minimum:
        return {}
    path = directory / SOURCES
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 512 * 1024 * 1024:
        raise ValueError("Corresponding managed sources are required")
    with tarfile.open(path, "r:gz") as archive:
        names = {member.name.removeprefix("./"): member for member in archive}
        marker = names.get("identity.json" if platform == "windows" else "source-sha.txt")
        if marker is None or not marker.isfile() or marker.size > 4096:
            raise ValueError("Source identity missing")
        stream = archive.extractfile(marker)
        assert stream is not None
        identity = stream.read().decode("utf-8-sig")
        source_sha = (
            json.loads(identity)["source_sha"] if platform == "windows" else identity.strip()
        )
        if (
            source_sha != sha
            or "source/engines/managed/go.mod" not in names
            or not any(name.startswith("licenses/") for name in names)
        ):
            raise ValueError("Corresponding source or license mismatch")
        if platform == "windows":
            notice = names.get("Wintun-Prebuilt-License.txt")
            if notice is None or not notice.isfile() or not 0 < notice.size <= 131072:
                raise ValueError("Archived Wintun license missing")
            notice_stream = archive.extractfile(notice)
            assert notice_stream is not None
            archived_notice = notice_stream.read()
    result = {f"{platform}-sources.tar.gz": path.read_bytes()}
    if platform == "windows":
        license_path = directory / "Wintun-Prebuilt-License.txt"
        if (
            license_path.is_symlink()
            or not license_path.is_file()
            or not 0 < license_path.stat().st_size <= 131072
        ):
            raise ValueError("Wintun binary redistribution license missing")
        result["windows-licenses.txt"] = license_path.read_bytes()
        if result["windows-licenses.txt"] != archived_notice:
            raise ValueError("Wintun license differs from corresponding archive")
    return result


def order(entry: dict[str, Any]) -> tuple[int, ...]:
    return (
        *map(int, entry["version"].split(".")),
        entry["run_id"],
        entry["run_attempt"],
    )


def archive_version(payload: bytes, platform: str, *, simulator: bool = False) -> str:
    """Check the actual extension/app, never infer installability from a ZIP suffix."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(
            name.startswith(("/", "\\")) or "\\" in name or ".." in name.split("/")
            for name in names
        ):
            raise ValueError("Unsafe or duplicate archive paths")

        def read_metadata(name: str) -> bytes:
            if archive.getinfo(name).file_size > 65536:
                raise ValueError("Archive metadata too large")
            return archive.read(name)

        if platform == "chrome":
            manifest = json.loads(read_metadata("manifest.json"))
            if (
                manifest.get("manifest_version") != 3
                or manifest.get("name") != "PrettyLisaVPN"
                or manifest.get("background", {}).get("service_worker") != "background.js"
                or not {"background.js", "popup.html", "icon.png"}.issubset(names)
            ):
                raise ValueError("Expected the complete PrettyLisaVPN MV3 extension")
            version = manifest.get("version")
        else:
            prefix = "PrettyLisaVPN.app/" + ("Contents/" if platform == "macos" else "")
            info = plistlib.loads(read_metadata(prefix + "Info.plist"))
            executable = prefix + ("MacOS/" if platform == "macos" else "") + "PrettyLisaVPN"
            sdk = (
                "iphonesimulator" if simulator else "macosx" if platform == "macos" else "iphoneos"
            )
            if (
                info.get("CFBundleExecutable") != "PrettyLisaVPN"
                or info.get("CFBundlePackageType") != "APPL"
                or info.get("DTPlatformName") != sdk
                or executable not in names
                or not any(
                    name.startswith(prefix + "PlugIns/") and name.endswith("Info.plist")
                    for name in names
                )
            ):
                kind = "Simulator" if simulator else "device release"
                raise ValueError(f"Expected a {kind} app with its tunnel extension")
            version = info.get("CFBundleShortVersionString")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError("Invalid archive version")
        return version


def validate(
    directory: Path, platform: str, sha: str, run: int, attempt: int
) -> tuple[dict[str, Any], bytes, dict[str, bytes]]:
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
    installed_windows = platform == "windows" and tuple(map(int, version.split("."))) >= (
        0,
        23,
        0,
    )
    if installed_windows and (
        identity.get("package_kind") != "nsis"
        or identity.get("installer") != "PrettyLisaVPN-Setup.exe"
    ):
        raise ValueError("Windows must be distributed as an installer")
    binary = directory / ("PrettyLisaVPN-Setup.exe" if installed_windows else FILES[platform])
    if binary.is_symlink() or not 0 < binary.stat().st_size <= 512 * 1024 * 1024:
        raise ValueError("Invalid binary file")
    payload = binary.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != identity["apk_sha256" if android else "sha256"]:
        raise ValueError("Binary checksum mismatch")
    if not payload.startswith(b"MZ" if platform == "windows" else b"PK\x03\x04"):
        raise ValueError("Unexpected binary format")
    if platform in PACKAGE_KINDS:
        if (
            identity.get("event") != "push"
            or identity.get("package_kind") != PACKAGE_KINDS[platform]
            or archive_version(payload, platform) != version
        ):
            raise ValueError("Unexpected development archive identity")
        if platform == "chrome":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                build = json.loads(archive.read("build-identity.json"))
            if (
                build.get("source_sha"),
                str(build.get("run")),
                str(build.get("attempt")),
            ) != (sha, str(run), str(attempt)):
                raise ValueError("Extension source identity mismatch")
    compact_android = android and tuple(map(int, version.split("."))) >= (0, 15, 1)
    if compact_android:
        if len(payload) > 40_000_000:
            raise ValueError("Android APK exceeds 40 MB")
        if identity.get("abi") != "arm64-v8a" or identity.get("apk_bytes") != len(payload):
            raise ValueError("Expected the standalone ARM64 phone APK")
        with zipfile.ZipFile(io.BytesIO(payload)) as apk:
            natives = {name for name in apk.namelist() if name.startswith("lib/")}
            if {name.split("/")[1] for name in natives} != {"arm64-v8a"} or not {
                "lib/arm64-v8a/libgojni.so",
                "lib/arm64-v8a/libwg-go.so",
            }.issubset(natives):
                raise ValueError("Android native architecture mismatch")
    if not android and identity.get("bytes") != len(payload):
        raise ValueError("Binary size mismatch")
    companions = sources(directory, platform, version, sha)
    entry = {
        "version": version,
        "source_sha": sha,
        "run_id": run,
        "run_attempt": attempt,
        "sha256": digest,
        "bytes": len(payload),
        "url": "/dashboard/downloads/" + DOWNLOADS[platform],
        "published_at": datetime.now(UTC).isoformat(),
    }
    if installed_windows:
        entry["package_kind"] = "nsis"
    if platform in PACKAGE_KINDS:
        entry["package_kind"] = PACKAGE_KINDS[platform]
    if compact_android:
        entry["abi"] = "arm64-v8a"
    if companions:
        entry["sources_url"] = f"/dashboard/downloads/{platform}-sources.tar.gz"
        entry["sources_sha256"] = hashlib.sha256(
            companions[f"{platform}-sources.tar.gz"]
        ).hexdigest()
        if platform == "windows":
            entry["licenses_url"] = "/dashboard/downloads/windows-licenses.txt"
            entry["licenses_sha256"] = hashlib.sha256(
                companions["windows-licenses.txt"]
            ).hexdigest()
    # Optional for legacy catalogs; new Apple CI packages always include it.
    # Both variants share the parent build coordinates and corresponding sources.
    if platform == "ios" and "simulator" in identity:
        metadata = identity["simulator"]
        path = directory / SIMULATOR_FILE
        if (
            not isinstance(metadata, dict)
            or path.is_symlink()
            or not path.is_file()
            or not 0 < path.stat().st_size <= 512 * 1024 * 1024
        ):
            raise ValueError("Invalid Simulator package")
        simulator_payload = path.read_bytes()
        simulator_digest = hashlib.sha256(simulator_payload).hexdigest()
        if (
            metadata.get("sha256") != simulator_digest
            or metadata.get("bytes") != len(simulator_payload)
            or archive_version(simulator_payload, "ios", simulator=True) != version
        ):
            raise ValueError("Simulator identity mismatch")
        companions[SIMULATOR_DOWNLOAD] = simulator_payload
        entry["simulator_url"] = "/dashboard/downloads/" + SIMULATOR_DOWNLOAD
        entry["simulator_sha256"] = simulator_digest
        entry["simulator_bytes"] = len(simulator_payload)
    return entry, payload, companions


def publish(root: Path, directory: Path, platform: str, sha: str, run: int, attempt: int) -> str:
    # Only used on the Linux main server. A shared lock serializes both platforms.
    import fcntl

    entry, payload, companions = validate(directory, platform, sha, run, attempt)
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
                if any(
                    entry.get(key) != previous.get(key)
                    for key in (
                        "sha256",
                        "source_sha",
                        "sources_sha256",
                        "licenses_sha256",
                        "simulator_sha256",
                    )
                ):
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
            for name, content in companions.items():
                if not (release / name).is_file() or (release / name).read_bytes() != content:
                    raise ValueError("Conflicting stored sources or licenses")
        else:
            stage = Path(tempfile.mkdtemp(prefix="pending-", dir=release.parent))
            (stage / DOWNLOADS[platform]).write_bytes(payload)
            for name, content in companions.items():
                (stage / name).write_bytes(content)
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
            for key, name in (
                ("sources_sha256", f"{client}-sources.tar.gz"),
                ("licenses_sha256", "windows-licenses.txt"),
                ("simulator_sha256", SIMULATOR_DOWNLOAD),
            ):
                if key in item:
                    (snapshot / name).symlink_to(
                        f"../../releases/{client}/{item['run_id']}-{item['run_attempt']}/{name}"
                    )
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
