"""Publication contracts use fake binaries; never distribute test fixtures."""

import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
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
