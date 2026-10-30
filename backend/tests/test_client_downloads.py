"""Publication contracts use fake binaries; never distribute test fixtures."""

import hashlib
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "publish_client", ROOT / "infra/deployment/publish_client.py"
)
assert SPEC is not None and SPEC.loader is not None
PUBLISHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISHER)
SHA = "a" * 40


class ClientDownloadsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "served"

    def artifact(self, platform="android", run=100, version="0.14.0", attempt=1):
        directory = self.base / f"{platform}-{run}-{attempt}"
        directory.mkdir(exist_ok=True)
        android = platform == "android"
        payload = (b"PK\x03\x04" if android else b"MZ") + b"test-only"
        (directory / PUBLISHER.FILES[platform]).write_bytes(payload)
        identity = {
            "source_sha": SHA,
            "run_id": str(run),
            "run_attempt": str(attempt),
            "version_name" if android else "version": version,
            "apk_sha256" if android else "sha256": hashlib.sha256(payload).hexdigest(),
            "bytes": len(payload),
            "application_id": "com.prettylisavpn.android.dev",
            "apk": "app-debug.apk",
            "event": "push",
        }
        (directory / "build-identity.json").write_text(json.dumps(identity))
        return directory

    def publish(self, platform="android", run=100, version="0.14.0", attempt=1):
        return PUBLISHER.publish(
            self.root,
            self.artifact(platform, run, version, attempt),
            platform,
            SHA,
            run,
            attempt,
        )

    def source_archive(self, directory, platform, sha=SHA):
        marker = (
            {"source-sha.txt": sha}
            if platform == "android"
            else {
                "identity.json": json.dumps({"source_sha": sha}),
                "Wintun-Prebuilt-License.txt": "Test-only license fixture",
            }
        )
        with tarfile.open(directory / PUBLISHER.SOURCES, "w:gz") as archive:
            for name, value in {
                **marker,
                "source/engines/managed/go.mod": "module test-only",
                "licenses/test-only/LICENSE": "Test-only license fixture",
            }.items():
                data = value.encode()
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        if platform == "windows":
            (directory / "Wintun-Prebuilt-License.txt").write_text("Test-only license fixture")

    def test_managed_clients_require_matching_sources_and_licenses(self):
        for platform, version in (("android", "0.15.0"), ("windows", "0.18.0")):
            directory = self.artifact(platform, version=version)
            with self.assertRaises(ValueError):
                PUBLISHER.validate(directory, platform, SHA, 100, 1)
            self.source_archive(directory, platform, "b" * 40)
            with self.assertRaises(ValueError):
                PUBLISHER.validate(directory, platform, SHA, 100, 1)
            self.source_archive(directory, platform)
            entry, _, companions = PUBLISHER.validate(directory, platform, SHA, 100, 1)
            self.assertEqual(
                entry["sources_sha256"],
                hashlib.sha256(companions[f"{platform}-sources.tar.gz"]).hexdigest(),
            )
            self.assertEqual(
                entry["sources_url"], f"/dashboard/downloads/{platform}-sources.tar.gz"
            )
            if platform == "windows":
                (directory / "Wintun-Prebuilt-License.txt").write_text("different")
                with self.assertRaises(ValueError):
                    PUBLISHER.validate(directory, platform, SHA, 100, 1)

    def test_compact_android_requires_matching_phone_abi_and_size(self):
        directory = self.artifact(version="0.15.1")
        self.source_archive(directory, "android")
        apk = directory / "app-debug.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            for name in ("libgojni.so", "libwg-go.so"):
                archive.writestr("lib/arm64-v8a/" + name, b"test-only")
        identity_path = directory / "build-identity.json"
        identity = json.loads(identity_path.read_text())
        identity.update(
            abi="arm64-v8a",
            apk_bytes=apk.stat().st_size,
            apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
        )
        identity_path.write_text(json.dumps(identity))
        entry, _, _ = PUBLISHER.validate(directory, "android", SHA, 100, 1)
        self.assertEqual(entry["abi"], "arm64-v8a")
        for field, value in (("abi", "x86_64"), ("abi", None), ("apk_bytes", 1)):
            identity_path.write_text(json.dumps({**identity, field: value}))
            with self.assertRaises(ValueError):
                PUBLISHER.validate(directory, "android", SHA, 100, 1)
        with apk.open("ab") as stream:
            stream.truncate(40_000_001)
        identity.update(
            apk_bytes=apk.stat().st_size, apk_sha256=hashlib.sha256(apk.read_bytes()).hexdigest()
        )
        identity_path.write_text(json.dumps(identity))
        with self.assertRaisesRegex(ValueError, "exceeds 40 MB"):
            PUBLISHER.validate(directory, "android", SHA, 100, 1)

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_sources_switch_atomically_and_changed_source_replay_is_rejected(self):
        directory = self.artifact("windows", version="0.18.0")
        self.source_archive(directory, "windows")
        self.assertEqual(
            PUBLISHER.publish(self.root, directory, "windows", SHA, 100, 1), "published"
        )
        initial = (self.root / "current").readlink()
        catalog = json.loads((self.root / "current/index.json").read_text())["clients"]["windows"]
        for name, key in (
            ("windows-sources.tar.gz", "sources_sha256"),
            ("windows-licenses.txt", "licenses_sha256"),
        ):
            self.assertEqual(
                hashlib.sha256((self.root / "current" / name).read_bytes()).hexdigest(),
                catalog[key],
            )
        # A new valid archive with the same source marker but changed payload is
        # still a different immutable build and cannot replace these coordinates.
        with tarfile.open(directory / PUBLISHER.SOURCES, "r:gz") as archive:
            data = [
                (member, archive.extractfile(member).read())
                for member in archive
                if member.isfile()
            ]
        with tarfile.open(directory / PUBLISHER.SOURCES, "w:gz") as archive:
            for member, content in data:
                if member.name.endswith("go.mod"):
                    content += b"\n// changed"
                    member.size = len(content)
                archive.addfile(member, io.BytesIO(content))
        with self.assertRaises(ValueError):
            PUBLISHER.publish(self.root, directory, "windows", SHA, 100, 1)
        self.assertEqual((self.root / "current").readlink(), initial)

    def test_identity_hash_size_and_format_are_verified(self):
        for platform in PUBLISHER.FILES:
            directory = self.artifact(platform)
            PUBLISHER.validate(directory, platform, SHA, 100, 1)
            for sha, run, attempt in (("b" * 40, 100, 1), (SHA, 99, 1), (SHA, 100, 2)):
                with self.assertRaises(ValueError):
                    PUBLISHER.validate(directory, platform, sha, run, attempt)
            identity_path = directory / "build-identity.json"
            original = json.loads(identity_path.read_text())
            for key, value in (
                ("pr_head_sha", SHA),
                ("version_name" if platform == "android" else "version", "../../bad"),
                ("apk_sha256" if platform == "android" else "sha256", "0" * 64),
                ("application_id" if platform == "android" else "bytes", 0),
            ):
                identity_path.write_text(json.dumps({**original, key: value}))
                with self.assertRaises(ValueError):
                    PUBLISHER.validate(directory, platform, SHA, 100, 1)
            identity_path.write_text(json.dumps(original))
            (directory / PUBLISHER.FILES[platform]).write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                PUBLISHER.validate(directory, platform, SHA, 100, 1)

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_both_platforms_publish_concurrently_without_lost_updates(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.publish, ["android", "windows"]))
        self.assertEqual(results, ["published", "published"])
        catalog = json.loads((self.root / "current/index.json").read_text())
        self.assertEqual(set(catalog["clients"]), {"android", "windows"})
        for platform, entry in catalog["clients"].items():
            payload = (self.root / "current" / PUBLISHER.DOWNLOADS[platform]).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), entry["sha256"])
            self.assertEqual(entry["url"], "/dashboard/downloads/" + PUBLISHER.DOWNLOADS[platform])

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_late_older_build_is_ignored_and_reruns_are_idempotent(self):
        self.assertEqual(self.publish(), "published")
        initial = (self.root / "current").readlink()
        self.assertEqual(self.publish(), "unchanged")
        self.assertEqual(self.publish(run=99), "superseded")
        self.assertEqual(self.publish(run=101, version="0.13.0"), "superseded")
        self.assertEqual((self.root / "current").readlink(), initial)
        self.assertEqual(self.publish(attempt=2), "published")
        self.assertEqual(self.publish(run=101), "published")

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_invalid_or_interrupted_publication_keeps_previous_snapshot(self):
        self.publish()
        initial = (self.root / "current").readlink()
        directory = self.artifact(run=101)
        (directory / "app-debug.apk").write_bytes(b"invalid")
        with self.assertRaises(ValueError):
            PUBLISHER.publish(self.root, directory, "android", SHA, 101, 1)
        with patch.object(Path, "replace", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.publish(run=101)
        self.assertEqual((self.root / "current").readlink(), initial)
        self.assertEqual(self.publish(run=101), "published")

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_same_coordinates_with_other_source_or_bytes_are_rejected(self):
        self.publish()
        initial = (self.root / "current").readlink()
        directory = self.artifact()
        path = directory / "build-identity.json"
        identity = json.loads(path.read_text())
        identity["source_sha"] = "b" * 40
        path.write_text(json.dumps(identity))
        with self.assertRaises(ValueError):
            PUBLISHER.publish(self.root, directory, "android", "b" * 40, 100, 1)
        self.assertEqual((self.root / "current").readlink(), initial)


if __name__ == "__main__":
    unittest.main()
