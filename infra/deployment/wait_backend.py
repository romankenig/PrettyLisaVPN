"""Gate client publication on the source manifest's live development backend."""

import argparse
import json
import re
import time
import tomllib
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def matches(version: object, ready: object, base: str) -> bool:
    if not isinstance(version, dict) or not isinstance(ready, dict):
        return False
    runtime = version.get("application_version")
    return (
        version.get("application_name") == "PrettyLisaVPN"
        and version.get("environment") == "development"
        and isinstance(runtime, str)
        and re.fullmatch(re.escape(base) + r"-dev\.[1-9][0-9]*\+g[0-9a-f]{40}", runtime) is not None
        and ready.get("status") == "ready"
        and ready.get("dependencies") == {"postgresql": True, "valkey": True}
    )


def wait_backend(url: str, base: str, timeout: float) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or timeout <= 0
        or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", base)
    ):
        raise ValueError("Expected an HTTPS origin, package version and positive timeout")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url.rstrip("/") + "/version", timeout=10) as response:
                version = json.load(response)
            with urlopen(url.rstrip("/") + "/ready", timeout=10) as response:
                ready = json.load(response)
            if matches(version, ready, base):
                print(json.dumps({"event": "backend_ready_for_clients", "version": version}))
                return
        except (URLError, OSError, ValueError):
            pass
        print(
            json.dumps({"event": "waiting_for_backend", "required_version": base}),
            flush=True,
        )
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    raise TimeoutError("Required backend is not ready; client publication remains blocked")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=float, default=1800)
    args = parser.parse_args()
    manifest = Path(__file__).resolve().parents[2] / "backend/pyproject.toml"
    base = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["version"]
    wait_backend(args.url, base, args.timeout)


if __name__ == "__main__":
    main()
