"""Snapshot integrity and inactive-standby safeguards, without production IO."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mirror


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def snapshot(self):
        identity = "sha256:" + "a" * 64
        mirror.write_json(self.root / "containers.json", [{"Image": identity}])
        (self.root / "images").mkdir()
        (self.root / "images" / ("a" * 64 + ".tar.gz")).write_bytes(b"fixture-image")
        (self.root / "rootfs").mkdir()
        (self.root / "rootfs/config.env").write_text("FIXTURE_SECRET=never-log-this\n")
        # A nested manifest is application data and must also be protected.
        (self.root / "rootfs/manifest.json").write_text('{"version":"fixture"}')
        files = mirror.inventory(self.root)
        snapshot_id = mirror.snapshot_id(files)
        mirror.write_json(
            self.root / "manifest.json",
            {
                "format": 1,
                "snapshot_id": snapshot_id,
                "files": files,
                "images": [identity],
            },
        )
        return snapshot_id

    def test_complete_snapshot_is_accepted(self):
        identity = self.snapshot()
        self.assertEqual(mirror.verify(self.root, identity)["snapshot_id"], identity)

    def test_changed_settings_are_rejected(self):
        identity = self.snapshot()
        (self.root / "rootfs/config.env").write_text("different")
        with self.assertRaises(ValueError):
            mirror.verify(self.root, identity)

    def test_nested_manifest_is_not_excluded(self):
        identity = self.snapshot()
        (self.root / "rootfs/manifest.json").write_text("different")
        with self.assertRaises(ValueError):
            mirror.verify(self.root, identity)

    def test_added_file_is_rejected(self):
        identity = self.snapshot()
        (self.root / "unreviewed").write_text("unexpected")
        with self.assertRaises(ValueError):
            mirror.verify(self.root, identity)

    def test_image_substitution_is_rejected(self):
        identity = self.snapshot()
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["images"] = ["sha256:" + "b" * 64]
        mirror.write_json(path, manifest)
        with self.assertRaises(ValueError):
            mirror.verify(self.root, identity)

    def test_escaping_paths_are_rejected(self):
        for value in (
            "../secret",
            "/etc/passwd",
            "images/../../secret",
            "x\\..\\secret",
            "",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mirror.safe_relative(value)

    def test_symlink_is_rejected(self):
        identity = self.snapshot()
        (self.root / "link").symlink_to(self.root / "containers.json")
        with self.assertRaises(ValueError):
            mirror.verify(self.root, identity)

    def test_active_standby_refuses_any_remote_or_docker_command(self):
        (self.root / "ACTIVE").touch()
        with (
            patch.object(mirror, "STANDBY_ROOT", self.root),
            patch.object(mirror, "run") as run,
        ):
            with self.assertRaises(RuntimeError):
                mirror.pull()
            run.assert_not_called()

    def test_command_errors_do_not_expose_secret_stderr(self):
        result = type("Result", (), {"returncode": 1, "stderr": "secret-value"})()
        with patch.object(mirror.subprocess, "run", return_value=result):
            with self.assertRaises(RuntimeError) as caught:
                mirror.run(["rsync", "fixture"])
            self.assertNotIn("secret-value", str(caught.exception))

    def test_publisher_links_within_download_store_are_materialized(self):
        store = self.root / "downloads"
        (store / "snapshot").mkdir(parents=True)
        (store / "artifacts").mkdir()
        (store / "artifacts/client.exe").write_bytes(b"verified-client")
        (store / "snapshot/client.exe").symlink_to("../artifacts/client.exe")
        (store / "current").symlink_to("snapshot")
        mirror.copy_tree(store / "current", self.root / "copied", immutable=True)
        copied = self.root / "copied/client.exe"
        self.assertFalse(copied.is_symlink())
        self.assertEqual(copied.read_bytes(), b"verified-client")

    def test_publisher_link_cannot_escape_download_store(self):
        store = self.root / "downloads"
        (store / "snapshot").mkdir(parents=True)
        (self.root / "secret").write_text("secret")
        (store / "snapshot/client.exe").symlink_to("../../secret")
        (store / "current").symlink_to("snapshot")
        with self.assertRaises(ValueError):
            mirror.copy_tree(store / "current", self.root / "copied")

    def test_unchanged_snapshot_does_not_retransfer_payload_or_start_services(self):
        identity = self.snapshot()
        fixture = self.root
        with tempfile.TemporaryDirectory() as directory:
            standby = Path(directory)
            destination = standby / "snapshots" / identity
            shutil.copytree(fixture, destination)
            (standby / "incoming").mkdir()
            mirror.write_json(
                standby / "incoming/latest.json",
                {"snapshot_id": identity, "checked_at_unix": 123},
            )
            with (
                patch.object(mirror, "STANDBY_ROOT", standby),
                patch.object(mirror, "run", return_value="130.0.234.51") as run,
            ):
                mirror.pull()
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len([c for c in commands if c[0] == "rsync"]), 1)
            self.assertTrue(
                all(c[:3] == ["docker", "image", "inspect"] for c in commands if c[0] == "docker")
            )
            self.assertEqual((standby / "current").resolve(), destination)
            self.assertEqual(
                json.loads((standby / "status.json").read_text())["state"], "STAGED_NOT_ACTIVE"
            )

    def test_only_owned_unreferenced_images_are_removed_without_force(self):
        identity = self.snapshot()
        current = "sha256:" + "a" * 64
        old = "sha256:" + "b" * 64
        retained = self.root / "snapshots" / identity
        retained.mkdir(parents=True)
        mirror.write_json(retained / "manifest.json", {"images": [current]})
        with patch.object(mirror, "run") as run:
            mirror.prune_imported_images(self.root, {current, old})
            run.assert_called_once_with(["docker", "image", "rm", old])
        self.assertEqual(json.loads((self.root / "imported-images.json").read_text()), [current])

    def test_image_in_use_remains_tracked_for_later_cleanup(self):
        (self.root / "snapshots").mkdir()
        old = "sha256:" + "b" * 64
        with patch.object(mirror, "run", side_effect=RuntimeError("in use")):
            mirror.prune_imported_images(self.root, {old})
        self.assertEqual(json.loads((self.root / "imported-images.json").read_text()), [old])

    def test_abandoned_transfers_are_removed_but_current_and_unrelated_are_kept(self):
        old, current = "a" * 64, "b" * 64
        for name in (old, current, "unrelated"):
            (self.root / name).mkdir()
        (self.root / ("c" * 64)).symlink_to(self.root / "unrelated")
        mirror.discard_abandoned_staging(self.root, keep=current)
        self.assertFalse((self.root / old).exists())
        self.assertTrue((self.root / current).exists())
        self.assertTrue((self.root / "unrelated").exists())
        self.assertTrue((self.root / ("c" * 64)).is_symlink())


if __name__ == "__main__":
    unittest.main()
