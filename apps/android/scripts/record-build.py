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
element, = output["elements"]
apk = apk_dir / element["outputFile"]
assert output["applicationId"] == "com.prettylisavpn.android.dev"
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
    "apk": apk.name,
    "apk_sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
}
(apk_dir / "build-identity.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
