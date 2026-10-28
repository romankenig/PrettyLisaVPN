"""Exercise the Linux publication boundary without Docker or real credentials."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "infra/deployment/publish_client_container.sh"


@unittest.skipUnless(os.name == "posix", "Main-server Bash boundary")
class ClientPublisherContainerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.log = self.base / "docker.json"
        docker = self.base / "docker"
        docker.write_text(
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "if sys.argv[1] == 'inspect': print('sha256:' + 'b' * 64)\n"
            "else: Path(os.environ['DOCKER_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        )
        docker.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.base) + os.pathsep + os.environ["PATH"],
            "DOCKER_LOG": str(self.log),
        }
        self.args = [
            "windows",
            "/opt/prettylisavpn/incoming/client-windows-123-1",
            "a" * 40,
            "123",
            "1",
        ]

    def test_only_download_store_is_writable_and_no_network_or_secrets_are_mounted(self):
        subprocess.run(["bash", str(SCRIPT), *self.args], env=self.env, check=True)
        args = json.loads(self.log.read_text())
        self.assertIn("--read-only", args)
        self.assertIn("--no-healthcheck", args)
        for flag, value in {
            "--network": "none",
            "--cap-drop": "ALL",
            "--cap-add": "DAC_READ_SEARCH",
            "--security-opt": "no-new-privileges",
            "--user": "0:0",
            "--pull": "never",
            "--entrypoint": "python",
        }.items():
            self.assertEqual(args[args.index(flag) + 1], value)
        mounts = [args[i + 1] for i, item in enumerate(args) if item == "--mount"]
        incoming = self.args[1]
        downloads = "/opt/prettylisavpn/secrets/dashboard/downloads"
        self.assertEqual(
            mounts,
            [
                f"type=bind,src={incoming},dst={incoming},readonly",
                f"type=bind,src={downloads},dst={downloads}",
            ],
        )
        self.assertIn("sha256:" + "b" * 64, args)
        self.assertEqual(args[-4:], ["--run", "123", "--attempt", "1"])

    def test_rejects_unexpected_mount_paths_and_invalid_build_identity(self):
        for index, invalid in [(0, "unknown"), (1, "/etc"), (2, "HEAD"), (3, "0")]:
            args = self.args.copy()
            args[index] = invalid
            result = subprocess.run(["bash", str(SCRIPT), *args], env=self.env, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())
