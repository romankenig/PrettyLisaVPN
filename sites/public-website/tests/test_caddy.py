"""Serve the built website with an isolated production proxy and dummy binaries."""

import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
IMAGE = (
    "caddy:2.10.2-alpine@sha256:"
    "4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d"
)


def docker(*args, check=True):
    return subprocess.run(
        ["docker", *args], check=check, capture_output=True, text=True, timeout=90
    )


class PublicWebsiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dist = ROOT / "sites/public-website/dist"
        if not (cls.dist / "index.html").is_file():
            raise RuntimeError("Build the website before testing Caddy")
        cls.temp = tempfile.TemporaryDirectory(prefix="pl-public-test-")
        cls.addClassCleanup(cls.temp.cleanup)
        downloads = Path(cls.temp.name) / "downloads/current"
        downloads.mkdir(parents=True)
        for name in (
            "android.apk",
            "windows.exe",
            "android-sources.tar.gz",
            "windows-sources.tar.gz",
            "windows-licenses.txt",
            "index.json",
        ):
            (downloads / name).write_text("verified-client-fixture")
        (Path(cls.temp.name) / "private.txt").write_text("private-marker")
        config = (ROOT / "infra/deployment/Caddyfile").read_text()
        public = config.split("prettylisavpn.com {", 1)[1].split("{$API_DOMAIN}", 1)[0]
        public = public.replace("backend:8000", "127.0.0.1:8000")
        (Path(cls.temp.name) / "Caddyfile").write_text(
            ":8080 {" + public + '\n:8000 {\nrespond "payment-return-stub" 200\n}\n'
        )
        cls.name = "pl-public-website-test-" + uuid4().hex[:12]
        cls.addClassCleanup(docker, "rm", "-f", cls.name, check=False)
        docker(
            "run",
            "-d",
            "--name",
            cls.name,
            "--network=none",
            "-v",
            f"{cls.temp.name}:/etc/caddy/test:ro",
            "-v",
            f"{cls.dist}:/srv/public-website/current:ro",
            "-v",
            f"{Path(cls.temp.name) / 'downloads'}:/srv/client-downloads:ro",
            IMAGE,
            "caddy",
            "run",
            "--config",
            "/etc/caddy/test/Caddyfile",
            "--adapter",
            "caddyfile",
        )
        for _ in range(30):
            if "200 OK" in cls.request("/").stderr:
                return
            time.sleep(0.2)
        raise AssertionError("Isolated Caddy did not serve the website")

    @classmethod
    def request(cls, path, *options):
        return docker(
            "exec",
            cls.name,
            "wget",
            "-S",
            "-O",
            "-",
            *options,
            "http://127.0.0.1:8080" + path,
            check=False,
        )

    def test_all_pages_assets_and_headers(self):
        for page in self.dist.rglob("index.html"):
            route = "/" + page.parent.relative_to(self.dist).as_posix().strip(".")
            route = route.rstrip("/") + "/"
            with self.subTest(route=route):
                result = self.request(route)
                self.assertIn("200 OK", result.stderr)
                self.assertIn("PrettyLisaVPN", result.stdout)
                self.assertIn("platega test", result.stdout)
                self.assertEqual(result.stdout.count('class="document-button"'), 4)
                self.assertIn("noindex, nofollow", result.stderr)
                self.assertIn("no-store", result.stderr)
                self.assertIn("form-action 'none'", result.stderr)
        for asset in (
            "app.js",
            "downloads.mjs",
            "style.css",
            "lock.svg",
            "Rubik.ttf",
            "screenshots/android-home.png",
        ):
            # --spider checks headers without decoding binary fonts as text.
            result = self.request("/assets/" + asset, "--spider")
            self.assertIn("200 OK", result.stderr)
        self.assertIn("text/javascript", self.request("/assets/downloads.mjs").stderr)
        self.assertIn(
            "404 Not Found",
            self.request("/assets/screenshots/android-services.png", "--spider").stderr,
        )

    def test_client_files_are_public_but_dashboard_is_not(self):
        for name in (
            "android.apk",
            "windows.exe",
            "android-sources.tar.gz",
            "windows-sources.tar.gz",
            "windows-licenses.txt",
            "index.json",
        ):
            result = self.request("/downloads/" + name)
            self.assertIn("200 OK", result.stderr)
            self.assertEqual(result.stdout, "verified-client-fixture")
            self.assertIn("no-store", result.stderr)
            if name.endswith((".apk", ".exe", ".tar.gz")):
                self.assertIn("Content-Disposition: attachment", result.stderr)
            self.assertIn(
                "404 Not Found",
                self.request("/downloads/" + name, "--post-data=private-marker").stderr,
            )

    def test_cardlink_merchant_verification(self):
        result = self.request("/shop-verification-xO2ZZeK02A.txt")
        self.assertIn("200 OK", result.stderr)
        self.assertIn("Content-Type: text/plain", result.stderr)
        self.assertEqual(result.stdout.strip(), "shop-verification-xO2ZZeK02A")
        for route in ("/shop-verification-wrong.txt", "/public/shop-verification-xO2ZZeK02A.txt"):
            self.assertIn("404 Not Found", self.request(route).stderr)

    def test_private_paths_and_removed_provider_stay_closed(self):
        for route in (
            "/api/me",
            "/openapi.json",
            "/dashboard/",
            "/dashboard/downloads/android.apk",
            "/1plat.txt",
            "/api/payments/1plat/callback",
            "/Caddyfile",
            "/_headers",
            "/deployment.env",
            "/private.txt",
            "/unknown/",
            "/downloads/",
            "/downloads/private.txt",
            "/downloads/../private.txt",
            "/en/deployment.env",
            "/plans/",
            "/readiness/",
            "/account/",
        ):
            for options in ((), ("--post-data=private-marker",)):
                with self.subTest(route=route, options=options):
                    result = self.request(route, *options)
                    self.assertIn("404 Not Found", result.stderr)
                    self.assertNotIn("private-marker", result.stdout)

    def test_payment_is_disabled_and_returns_remain_routed(self):
        for route in ("/checkout", "/checkout/?approved=true"):
            result = self.request(route, "--post-data=approved=true")
            self.assertIn("503 Service Unavailable", result.stderr)
        for route in (
            "/payment/success",
            "/payment/failure",
            "/payment/assets/style.css",
            "/api/payments/cardlink/callback",
        ):
            result = self.request(route)
            self.assertIn("200 OK", result.stderr)
            self.assertEqual("payment-return-stub", result.stdout)
        for route in ("/payment/success", "/payment/failure", "/api/payments/cardlink/callback"):
            result = self.request(route, "--post-data=InvId=private-marker")
            self.assertIn("200 OK", result.stderr)
            self.assertEqual("payment-return-stub", result.stdout)
        # BusyBox wget does not resolve fragment-only targets like a browser.
        for route, target in (
            ("/support", "/#help"),
            ("/support/", "/#help"),
            ("/setup/", "/#download"),
        ):
            result = self.request(route)
            self.assertIn("308 Permanent Redirect", result.stderr)
            self.assertIn("Location: " + target, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
