"""Record the exact checkout, APK digest and Android-owned version after assembly."""

import hashlib
import json
import os
import pathlib
import subprocess

root = pathlib.Path(__file__).resolve().parents[1]
source_sha = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=root, text=True
).strip()
assert source_sha == os.environ["GITHUB_SHA"], "APK must be built from this checkout"
apk_dir = root / "app/build/outputs/apk/debug"
output = json.loads((apk_dir / "output-metadata.json").read_text())
assert output["applicationId"] == "com.prettylisavpn.android.dev"
expected = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}
seen = set()
for element in output["elements"]:
    abi_filter, = element["filters"]
    assert abi_filter["filterType"] == "ABI"
    abi = abi_filter["value"]
    assert abi in expected and abi not in seen
    seen.add(abi)
    apk = apk_dir / element["outputFile"]
    destination = root / "app/build/distributions/debug" / abi
    destination.mkdir(parents=True, exist_ok=True)
    payload = apk.read_bytes()
    assert len(payload) <= 40_000_000, f"{abi} APK exceeds the 40 MB download limit"
    (destination / "app-debug.apk").write_bytes(payload)
    record = {
        "product": "PrettyLisaVPN",
        "platform": "ANDROID",
        "source_sha": source_sha,
        "pr_head_sha": os.environ.get("PR_HEAD_SHA") or None,
        "event": os.environ["GITHUB_EVENT_NAME"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "build_type": "debug",
        "application_id": output["applicationId"],
        "version_name": element["versionName"],
        "version_code": element["versionCode"],
        "abi": abi,
        "apk": "app-debug.apk",
        "apk_bytes": len(payload),
        "apk_sha256": hashlib.sha256(payload).hexdigest(),
    }
    (destination / "build-identity.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))
assert seen == expected
