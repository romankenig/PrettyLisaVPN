"""Install a built private dashboard on the main server; never prints credentials."""

import argparse
import json
import os
import re
import secrets
import subprocess
import tarfile
from pathlib import Path


def render(template: str, username: str, password_hash: str, monitor_token: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", username):
        raise ValueError("Invalid dashboard username")
    if not re.fullmatch(r"\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}", password_hash):
        raise ValueError("A bcrypt password hash is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", monitor_token):
        raise ValueError("Invalid monitoring token")
    return (
        template.replace("@@USERNAME@@", username)
        .replace("@@PASSWORD_HASH@@", password_hash)
        .replace("@@MONITOR_TOKEN@@", monitor_token)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("sha")
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise SystemExit("Run as root with the exact source SHA")
    os.umask(0o077)
    root = Path("/opt/prettylisavpn/secrets/dashboard")
    root.mkdir(mode=0o700, exist_ok=True)
    credentials = root / "login.json"
    if not credentials.exists():
        credentials.write_text(
            json.dumps({"username": "admin", "password": secrets.token_urlsafe(24)})
        )
    login = json.loads(credentials.read_text())
    password_hash = (
        subprocess.check_output(
            [
                "docker",
                "exec",
                "-i",
                "prettylisavpn-development-caddy-1",
                "caddy",
                "hash-password",
            ],
            input=(login["password"] + "\n").encode(),
            stderr=subprocess.DEVNULL,
        )
        .decode()
        .strip()
    )
    fleet = dict(
        line.split("=", 1)
        for line in (root.parent / "fleet.env").read_text().splitlines()
        if "=" in line
    )
    release = root / "releases" / args.sha
    release.mkdir(parents=True, exist_ok=False)
    with tarfile.open(args.archive) as archive:
        archive.extractall(release, filter="data")
    if not (release / "index.html").is_file():
        raise SystemExit("Archive has no dashboard index.html")
    config = render(
        Path(__file__).with_name("dashboard.caddy.template").read_text(),
        login["username"],
        password_hash,
        fleet["FLEET_MONITOR_TOKEN"],
    )
    pending = root / "monitoring.pending"
    pending.write_text(config)
    # Validate in the pinned runtime before making the route visible.
    image = (
        subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format={{.Config.Image}}",
                "prettylisavpn-development-caddy-1",
            ]
        )
        .decode()
        .strip()
    )
    validation = root / "validation"
    validation.write_text(
        ":8080 {\nimport /etc/caddy/dashboard/monitoring.pending\n}\n"
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            str(root) + ":/etc/caddy/dashboard:ro",
            image,
            "caddy",
            "validate",
            "--config",
            "/etc/caddy/dashboard/validation",
            "--adapter",
            "caddyfile",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    pending.replace(root / "monitoring.caddy")
    link = root / "site.next"
    link.symlink_to("releases/" + args.sha)
    link.replace(root / "site")
    validation.unlink()
    print(
        json.dumps(
            {
                "installed": True,
                "source_sha": args.sha,
                "url": "https://api.prettylisavpn.com/dashboard/",
            }
        )
    )


if __name__ == "__main__":
    main()
