#!/usr/bin/env bash
set -euo pipefail
mkdir -p managed-evidence
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb push "$RUNNER_TEMP/pl-managed-credentials.json" /data/local/tmp/pl-managed-credentials.json >/dev/null
trap 'adb shell rm -f /data/local/tmp/pl-managed-credentials.json >/dev/null 2>&1 || true' EXIT
adb shell am instrument -w -r -e liveManaged true \
  -e class com.prettylisavpn.android.LiveManagedTest \
  com.prettylisavpn.android.dev.test/com.prettylisavpn.android.AcceptanceRunner \
  > managed-evidence/instrumentation.txt
adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/managed-proof.json managed-evidence/ >/dev/null
adb shell 'ls /sdcard/Android/data/com.prettylisavpn.android.dev/files/managed-*.png' | tr -d '\r' | while read -r image; do
  adb pull "$image" managed-evidence/ >/dev/null
done
python3 - <<'PY'
import json
from pathlib import Path
proof = json.loads(Path('managed-evidence/managed-proof.json').read_text())
assert proof['results'], 'No real attempts'
for row in proof['results']:
    assert row['connected'] and row['tunnel_https'] and row['cleanup'], row
    assert row['sustained_seconds'] >= 40, row
assert 'OK (1 test)' in Path('managed-evidence/instrumentation.txt').read_text()
print('Real packaged managed tunnels: verification, HTTPS, renewal and cleanup passed')
PY
