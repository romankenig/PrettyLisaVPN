"""Exercise clean/repeated preparation against a read-only module cache."""

import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare_core


class PreparationTest(unittest.TestCase):
    def test_prepares_private_copy_without_changing_cache_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            original = cache / prepare_core.FILE
            original.parent.mkdir(parents=True)
            original.write_bytes(b"original")
            for directory in [cache, *original.parents]:
                if directory == root:
                    break
                directory.chmod(stat.S_IRUSR | stat.S_IXUSR)
            script = root / "engine" / "prepare_core.py"
            script.parent.mkdir()
            metadata = json.dumps(
                {"Dir": str(cache), "Sum": prepare_core.SUM, "Version": prepare_core.VERSION}
            ).encode()
            try:
                with (
                    patch.object(prepare_core, "__file__", str(script)),
                    patch.object(prepare_core.subprocess, "check_output", return_value=metadata),
                    patch.object(prepare_core.subprocess, "run"),
                    patch.object(prepare_core, "patched", return_value=b"patched"),
                    patch.object(prepare_core, "GRPC_FILES", {}),
                ):
                    prepare_core.prepare("go")
                    prepare_core.prepare("go")
                target = script.parent / "patched" / "xray-core"
                self.assertEqual((target / prepare_core.FILE).read_bytes(), b"patched")
                self.assertEqual(original.read_bytes(), b"original")
                self.assertTrue((target / prepare_core.MARKER).is_file())
                # Windows does not implement Unix directory write permissions.
                import os

                if os.name != "nt":
                    self.assertFalse(cache.stat().st_mode & stat.S_IWUSR)
                    self.assertTrue(target.stat().st_mode & stat.S_IWUSR)
            finally:
                for directory in [cache, *cache.rglob("*")]:
                    if directory.is_dir():
                        directory.chmod(directory.stat().st_mode | stat.S_IRWXU)


if __name__ == "__main__":
    unittest.main()
