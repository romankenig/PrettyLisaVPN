"""Archive/CI provenance contracts; fixtures must never be distributed."""

import hashlib
import importlib.util
import io
import json
import os
import plistlib
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import test_client_downloads as legacy_downloads
from test_client_downloads import PUBLISHER, ROOT, SHA

SPEC = importlib.util.spec_from_file_location(
    "prepare_client_download", ROOT / "infra/deployment/prepare_client_download.py"
)
assert SPEC is not None and SPEC.loader is not None
PREPARE = importlib.util.module_from_spec(SPEC)
with patch.dict(sys.modules, {"publish_client": PUBLISHER}):
    SPEC.loader.exec_module(PREPARE)


class DownloadArchiveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)

    def original(self, platform):
        directory = self.base / platform
        directory.mkdir(exist_ok=True)
        identity = {"source_sha": SHA, "run": "100", "attempt": "1"}
        (directory / "build-identity.json").write_text(json.dumps(identity))
        if platform == "chrome":
            manifest = {
                "manifest_version": 3,
                "name": "PrettyLisaVPN",
                "version": "0.1.0",
                "background": {"service_worker": "background.js"},
            }
            (directory / "manifest.json").write_text(json.dumps(manifest))
            for name in ("background.js", "popup.html", "icon.png"):
                (directory / name).write_bytes(b"test-only")
        else:
            prefix = "PrettyLisaVPN.app/" + ("Contents/" if platform == "macos" else "")
            with zipfile.ZipFile(directory / PUBLISHER.FILES[platform], "w") as archive:
                archive.writestr(
                    prefix + "Info.plist",
                    plistlib.dumps(
                        {
                            "CFBundleExecutable": "PrettyLisaVPN",
                            "CFBundlePackageType": "APPL",
                            "CFBundleShortVersionString": "0.1.0",
                            "DTPlatformName": "macosx" if platform == "macos" else "iphoneos",
                        }
                    ),
                )
                archive.writestr(
                    prefix + ("MacOS/" if platform == "macos" else "") + "PrettyLisaVPN",
                    b"test-only",
                )
                archive.writestr(prefix + "PlugIns/Tunnel.appex/Info.plist", b"test-only")
            if platform == "ios":
                with (
                    zipfile.ZipFile(directory / PUBLISHER.FILES[platform]) as source,
                    zipfile.ZipFile(directory / PUBLISHER.SIMULATOR_FILE, "w") as simulator,
                ):
                    for name in source.namelist():
                        data = source.read(name)
                        if name == prefix + "Info.plist":
                            info = plistlib.loads(data)
                            info["DTPlatformName"] = "iphonesimulator"
                            data = plistlib.dumps(info)
                        simulator.writestr(name, data)
            with tarfile.open(
                directory / "corresponding-source-and-licenses.tar.gz", "w:gz"
            ) as archive:
                for name in ("source/engines/managed/go.mod", "licenses/test/LICENSE"):
                    member = tarfile.TarInfo(name)
                    member.size = 9
                    archive.addfile(member, io.BytesIO(b"test-only"))
        return directory

    def package(self, platform, suffix="", event="push"):
        output = self.base / (platform + "-download" + suffix)
        PREPARE.prepare(self.original(platform), output, platform, SHA, 100, 1, event)
        return output

    def test_all_archives_preserve_identity_version_kind_and_sources(self):
        for platform in PUBLISHER.PACKAGE_KINDS:
            directory = self.package(platform)
            entry, payload, companions = PUBLISHER.validate(directory, platform, SHA, 100, 1)
            self.assertEqual(entry["package_kind"], PUBLISHER.PACKAGE_KINDS[platform])
            self.assertEqual(entry["version"], "0.1.0")
            self.assertEqual(entry["url"], "/dashboard/downloads/" + PUBLISHER.DOWNLOADS[platform])
            self.assertEqual(entry["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(bool(companions), platform != "chrome")
            repeated = self.package(platform, "-repeat")
            self.assertEqual(payload, (repeated / PUBLISHER.FILES[platform]).read_bytes())
            if companions:
                self.assertEqual(
                    (directory / PUBLISHER.SOURCES).read_bytes(),
                    (repeated / PUBLISHER.SOURCES).read_bytes(),
                )
                (directory / PUBLISHER.SOURCES).unlink()
                with self.assertRaisesRegex(ValueError, "sources"):
                    PUBLISHER.validate(directory, platform, SHA, 100, 1)

    def test_reject_wrong_provenance_version_kind_hash_size_and_manual_builds(self):
        for platform in PUBLISHER.PACKAGE_KINDS:
            directory = self.package(platform)
            path = directory / "build-identity.json"
            original = json.loads(path.read_text())
            for key, value in (
                ("source_sha", "b" * 40),
                ("run_id", 99),
                ("run_attempt", 2),
                ("version", "0.2.0"),
                ("package_kind", "signed"),
                ("bytes", 1),
                ("sha256", "0" * 64),
                ("event", "workflow_dispatch"),
                ("event", "pull_request"),
            ):
                path.write_text(json.dumps({**original, key: value}))
                with self.subTest(platform=platform, field=key), self.assertRaises(ValueError):
                    PUBLISHER.validate(directory, platform, SHA, 100, 1)
            with self.assertRaisesRegex(ValueError, "Original CI identity"):
                PREPARE.prepare(
                    self.original(platform), self.base / "wrong", platform, "b" * 40, 100, 1, "push"
                )

    def test_reject_simulator_and_unsafe_archive_paths(self):
        directory = self.package("ios")
        binary = directory / PUBLISHER.FILES["ios"]
        with zipfile.ZipFile(binary) as source:
            files = {name: source.read(name) for name in source.namelist()}
        name = "PrettyLisaVPN.app/Info.plist"
        info = plistlib.loads(files[name])
        info["DTPlatformName"] = "iphonesimulator"
        files[name] = plistlib.dumps(info)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for path, data in files.items():
                archive.writestr(path, data)
        with self.assertRaisesRegex(ValueError, "device release"):
            PUBLISHER.archive_version(stream.getvalue(), "ios")
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("../bad", b"test-only")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            PUBLISHER.archive_version(stream.getvalue(), "ios")

    def test_simulator_is_a_distinct_verified_companion_and_legacy_is_supported(self):
        directory = self.package("ios")
        entry, _, companions = PUBLISHER.validate(directory, "ios", SHA, 100, 1)
        self.assertEqual(entry["simulator_url"], "/dashboard/downloads/ios-simulator.zip")
        self.assertEqual(
            entry["simulator_sha256"],
            hashlib.sha256(companions[PUBLISHER.SIMULATOR_DOWNLOAD]).hexdigest(),
        )
        identity_path = directory / "build-identity.json"
        identity = json.loads(identity_path.read_text())
        for metadata in (None, {}, {"sha256": "0" * 64, "bytes": entry["simulator_bytes"]}):
            identity_path.write_text(json.dumps({**identity, "simulator": metadata}))
            with self.assertRaises(ValueError):
                PUBLISHER.validate(directory, "ios", SHA, 100, 1)
        identity_path.write_text(json.dumps(identity))
        simulator = directory / PUBLISHER.SIMULATOR_FILE
        simulator.unlink()
        with self.assertRaisesRegex(ValueError, "Invalid Simulator"):
            PUBLISHER.validate(directory, "ios", SHA, 100, 1)
        del identity["simulator"]
        identity_path.write_text(json.dumps(identity))
        legacy, _, _ = PUBLISHER.validate(directory, "ios", SHA, 100, 1)
        self.assertNotIn("simulator_url", legacy)

    def test_device_archive_cannot_be_substituted_for_simulator(self):
        original = self.original("ios")
        (original / PUBLISHER.SIMULATOR_FILE).write_bytes(
            (original / PUBLISHER.FILES["ios"]).read_bytes()
        )
        with self.assertRaisesRegex(ValueError, "Simulator app"):
            PREPARE.prepare(original, self.base / "bad", "ios", SHA, 100, 1, "push")

    @unittest.skipIf(os.name == "nt", "Publisher uses Linux flock and symlinks")
    def test_new_platforms_preserve_existing_downloads_and_replay_atomically(self):
        root = self.base / "served"
        legacy = legacy_downloads.ClientDownloadsTests()
        legacy.base = self.base
        for platform in ("android", "windows"):
            PUBLISHER.publish(root, legacy.artifact(platform), platform, SHA, 100, 1)
        for platform in PUBLISHER.PACKAGE_KINDS:
            directory = self.package(platform)
            self.assertEqual(PUBLISHER.publish(root, directory, platform, SHA, 100, 1), "published")
            before = (root / "current").readlink()
            self.assertEqual(PUBLISHER.publish(root, directory, platform, SHA, 100, 1), "unchanged")
            self.assertEqual(before, (root / "current").readlink())
        clients = json.loads((root / "current/index.json").read_text())["clients"]
        self.assertEqual(set(clients), set(PUBLISHER.FILES))
        for platform, entry in clients.items():
            self.assertEqual(
                hashlib.sha256(
                    (root / "current" / PUBLISHER.DOWNLOADS[platform]).read_bytes()
                ).hexdigest(),
                entry["sha256"],
            )
        self.assertEqual(
            hashlib.sha256((root / "current/ios-simulator.zip").read_bytes()).hexdigest(),
            clients["ios"]["simulator_sha256"],
        )
        directory = self.base / "ios-download"
        path = directory / PUBLISHER.SIMULATOR_FILE
        with zipfile.ZipFile(path, "a") as archive:
            archive.writestr("test-only.txt", "changed simulator, same device")
        identity_path = directory / "build-identity.json"
        identity = json.loads(identity_path.read_text())
        identity["simulator"] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
        identity_path.write_text(json.dumps(identity))
        with self.assertRaisesRegex(ValueError, "Conflicting immutable"):
            PUBLISHER.publish(root, directory, "ios", SHA, 100, 1)
