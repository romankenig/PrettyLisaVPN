"""Recreation must retain owner configuration without inherited shell exports."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "deployment_config", ROOT / "infra/deployment/deployment_config.py"
)
assert SPEC is not None and SPEC.loader is not None
CONFIG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONFIG)


class DeploymentConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = self.root / "deployment.env"
        self.secret_line = "OTP_HMAC_SECRET='test-only-secret-with=embedded-value'\n"
        self.environment.write_text(self.secret_line)
        self.environment.chmod(0o600)
        # Keep tests independent of host enrollments and environment overrides.
        self.defaults = {
            f"{prefix}_ENV_FILE": str(self.root / f"{prefix.lower()}.env")
            for prefix in CONFIG.ENV_FILES
        }
        self.overrides = patch.dict(os.environ, self.defaults)
        self.overrides.start()
        self.addCleanup(self.overrides.stop)

    def fleet_file(self):
        path = self.root / "fleet.env"
        path.write_text("FLEET_ENABLED=true\nCLIENT_VPN_ENABLED=true\nMANAGED_VPN_ENABLED=true\n")
        path.chmod(0o600)
        return path

    def prepare(self, previous=None):
        CONFIG.prepare(self.environment, previous, self.root)

    def test_persist_and_reuse_after_shell_environment_is_gone(self):
        self.fleet_file()
        with patch.dict(os.environ, {"FLEET_CREDENTIALS_DIR": str(self.root / "custom-keys")}):
            self.prepare()
        original = self.environment.read_text()
        with patch.dict(os.environ, {}, clear=True):
            self.prepare()
        self.assertEqual(self.environment.read_text(), original)
        self.assertIn(self.secret_line, original)
        values = CONFIG.read_values(self.environment)
        self.assertEqual(values["FLEET_ENV_REQUIRED"], "true")
        self.assertEqual(values["FLEET_CREDENTIALS_DIR"], str(self.root / "custom-keys"))
        self.assertEqual(self.environment.stat().st_mode & 0o777, 0o600)

    def test_next_release_inherits_paths_without_copying_old_credentials(self):
        self.fleet_file()
        self.prepare()
        previous = self.root / "previous.env"
        self.environment.rename(previous)
        self.environment.write_text(
            "APPLICATION_VERSION='next-build'\nOTP_HMAC_SECRET='new-secret'\n"
        )
        self.environment.chmod(0o600)
        with patch.dict(os.environ, {}, clear=True):
            self.prepare(previous)
        new = self.environment.read_text()
        self.assertNotIn(self.secret_line, new)
        self.assertIn("OTP_HMAC_SECRET='new-secret'", new)
        self.assertEqual(CONFIG.read_values(self.environment)["FLEET_ENV_REQUIRED"], "true")

    def test_missing_previously_present_file_aborts_before_rewriting(self):
        fleet = self.fleet_file()
        self.prepare()
        original = self.environment.read_text()
        fleet.unlink()
        with self.assertRaisesRegex(ValueError, "Required FLEET"):
            self.prepare()
        self.assertEqual(self.environment.read_text(), original)

    def test_next_release_cannot_forget_required_file(self):
        fleet = self.fleet_file()
        self.prepare()
        previous = self.root / "previous.env"
        self.environment.rename(previous)
        fleet.unlink()
        self.environment.write_text(self.secret_line)
        self.environment.chmod(0o600)
        with self.assertRaisesRegex(ValueError, "Required FLEET"):
            self.prepare(previous)
        self.assertEqual(self.environment.read_text(), self.secret_line)

    def test_fresh_install_keeps_unconfigured_features_optional(self):
        self.prepare()
        values = CONFIG.read_values(self.environment)
        for prefix in CONFIG.ENV_FILES:
            self.assertEqual(values[f"{prefix}_ENV_REQUIRED"], "false")

    def test_insecure_file_and_interpolated_path_are_rejected(self):
        fleet = self.fleet_file()
        fleet.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "mode 600"):
            self.prepare()
        fleet.chmod(0o600)
        with patch.dict(os.environ, {"FLEET_ENV_FILE": "/tmp/$SECRET.env"}):
            with self.assertRaisesRegex(ValueError, "literal path"):
                self.prepare()

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is required")
    def test_plain_compose_recreation_keeps_vpn_flags_and_fails_if_file_disappears(self):
        fleet = self.fleet_file()
        with self.environment.open("a") as output:
            output.write(
                "BACKEND_IMAGE=test-only:immutable\nAPPLICATION_VERSION=0.0.0\n"
                "POSTGRES_URL=postgresql://test-only\nVALKEY_URL=redis://test-only\n"
                "API_DOMAIN=api.example.invalid\nACME_EMAIL=ops@example.invalid\n"
            )
        self.prepare()
        command = [
            "docker",
            "compose",
            "--env-file",
            str(self.environment),
            "--file",
            str(ROOT / "infra/deployment/compose.yaml"),
            "--profile",
            "fleet",
            "config",
            "--format",
            "json",
        ]
        # This renders only; it never starts a container or accesses a real secret.
        clean = {key: value for key, value in os.environ.items() if key not in self.defaults}
        result = subprocess.run(command, env=clean, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, "Compose render failed")
        services = json.loads(result.stdout)["services"]
        for name in ("backend", "fleet-worker"):
            for flag in ("FLEET_ENABLED", "CLIENT_VPN_ENABLED", "MANAGED_VPN_ENABLED"):
                self.assertEqual(services[name]["environment"][flag], "true")
        fleet.unlink()
        missing = subprocess.run(command, env=clean, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(missing.returncode, 0)


class RuntimeConfigurationTests(unittest.TestCase):
    def verify(self, *, missing_flag=False, missing_worker=False):
        expected = {"FLEET_ENABLED": "true", "MANAGED_VPN_SECRET": "test-only-secret"}
        responses = [
            {
                "services": {
                    name: {"image": "test:fixed", "environment": expected}
                    for name in ("backend", "fleet-worker")
                }
            }
        ]
        for name in ("backend", "fleet-worker"):
            responses.append([] if missing_worker and name == "fleet-worker" else {"ID": name})
            actual = expected if not missing_flag else {"MANAGED_VPN_SECRET": "test-only-secret"}
            responses.append(
                [
                    {
                        "State": {"Running": True},
                        "Config": {
                            "Image": "test:fixed",
                            "Env": [f"{k}={v}" for k, v in actual.items()],
                        },
                    }
                ]
            )
        with patch.object(CONFIG, "read_values", return_value={"FLEET_ENV_REQUIRED": "true"}):
            with patch.object(CONFIG, "docker_json", side_effect=responses):
                CONFIG.verify(Path("release.env"), Path("compose.yaml"), "test-project")

    def test_runtime_must_match_for_backend_and_worker(self):
        self.verify()

    def test_missing_runtime_flag_is_a_failed_deployment(self):
        with self.assertRaisesRegex(ValueError, "runtime environment differs"):
            self.verify(missing_flag=True)

    def test_missing_worker_is_a_failed_deployment(self):
        with self.assertRaisesRegex(ValueError, "one running fleet-worker"):
            self.verify(missing_worker=True)


if __name__ == "__main__":
    unittest.main()
