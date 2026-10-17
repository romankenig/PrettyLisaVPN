"""Offline contract checks; these do not claim a live VPS rollback."""

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "runtime_version", ROOT / "infra/deployment/runtime_version.py"
)
assert SPEC is not None and SPEC.loader is not None
RUNTIME = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNTIME)


class RuntimeIdentityTests(unittest.TestCase):
    def test_channels_and_attempt_identity(self):
        for channel in ("development", "preview", "release"):
            first = RUNTIME.runtime_identity("0.1.0", "a" * 40, "123", "1", channel)
            second = RUNTIME.runtime_identity("0.1.0", "a" * 40, "123", "2", channel)
            suffix = "" if channel == "release" else "-dev.123"
            self.assertEqual(first["application_version"], f"0.1.0{suffix}+g{'a' * 40}")
            self.assertEqual(first["application_version"], second["application_version"])
            self.assertNotEqual(first["image"], second["image"])
            self.assertNotIn("+", first["image"])

    def test_invalid_identity_rejected(self):
        for values in (
            ("dev-abc", "a" * 40, "1", "1", "development"),
            ("0.1.0", "abcdef", "1", "1", "development"),
            ("0.1.0", "a" * 40, "0", "1", "development"),
            ("0.1.0", "a" * 40, "1", "bad", "development"),
            ("0.1.0", "a" * 40, "1", "1", "unknown"),
        ):
            with self.assertRaises(ValueError):
                RUNTIME.runtime_identity(*values)


class DeploymentScriptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "commands"
        self.env_file = self.directory / "deployment.env"
        self.env_file.write_text(
            "API_DOMAIN='api.example.invalid'\n"
            "BACKEND_IMAGE='prettylisavpn-backend:retained-run-1-attempt-1'\n"
            "APPLICATION_VERSION='0.1.0-dev.1+g" + "a" * 40 + "'\n"
            "COMPOSE_PROJECT_NAME='prettylisavpn-development'\n"
        )
        self.env_file.chmod(0o600)
        for name, body in {
            "getent": "exit 0\n",
            "docker": 'printf "%s\\n" "$*" >> "$COMMAND_LOG"\n'
            'if [[ "$*" == "image inspect "* ]]; then exit "${IMAGE_EXIT:-0}"; fi\n'
            'if [[ "$*" == *"alembic upgrade"* ]]; then exit "${MIGRATION_EXIT:-0}"; fi\n',
            "curl": 'case "${!#}" in\n*/version) printf "%s" "$VERSION_JSON";;\nesac\n'
            'exit "${CURL_EXIT:-0}"\n',
        }.items():
            path = self.directory / name
            path.write_text("#!/bin/bash\n" + body)
            path.chmod(0o755)
        self.environment = {
            **os.environ,
            "PATH": f"{self.directory}:{os.environ['PATH']}",
            "COMMAND_LOG": str(self.log),
            "VERSION_JSON": json.dumps({"application_version": "0.1.0-dev.1+g" + "a" * 40}),
            "IMAGE_EXIT": "0",
            "MIGRATION_EXIT": "0",
            "CURL_EXIT": "0",
        }

    def run_deployment(self, mode="deploy"):
        return subprocess.run(
            ["bash", str(ROOT / "infra/deployment/deploy.sh"), str(self.env_file), mode],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_deploy_migrates_before_starting(self):
        result = self.run_deployment()
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertLess(commands.index("alembic upgrade head"), commands.index("up --detach"))

    def test_rollback_uses_retained_image_without_pull_or_migrations(self):
        result = self.run_deployment("rollback")
        self.assertEqual(result.returncode, 0, result.stderr)
        commands = self.log.read_text()
        self.assertIn("image inspect prettylisavpn-backend:retained-run-1-attempt-1", commands)
        self.assertNotIn("alembic", commands)
        self.assertNotIn(" pull", commands)
        self.assertIn("--pull never", commands)

    def test_wrong_malformed_and_substring_versions_fail(self):
        for response in (
            '{"application_version":"wrong"}',
            '{"application_version":"0.1.0-dev.1+g' + "a" * 40 + '-extra"}',
            "not json",
            "[]",
        ):
            self.environment["VERSION_JSON"] = response
            self.assertNotEqual(self.run_deployment("rollback").returncode, 0)

    def test_unavailable_endpoint_fails(self):
        self.environment["CURL_EXIT"] = "22"
        self.assertNotEqual(self.run_deployment("rollback").returncode, 0)

    def test_missing_rollback_image_stops_before_up(self):
        self.environment["IMAGE_EXIT"] = "1"
        self.assertNotEqual(self.run_deployment("rollback").returncode, 0)
        self.assertNotIn("up --detach", self.log.read_text())

    def test_failed_migration_stops_before_up(self):
        self.environment["MIGRATION_EXIT"] = "1"
        self.assertNotEqual(self.run_deployment().returncode, 0)
        self.assertNotIn("up --detach", self.log.read_text())

    def test_secret_file_permissions_checked_before_docker(self):
        self.env_file.chmod(0o644)
        self.assertNotEqual(self.run_deployment().returncode, 0)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
