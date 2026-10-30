#!/usr/bin/env bash
set -euo pipefail
mkdir -p managed-evidence
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb push "$RUNNER_TEMP/pl-managed-credentials.json" /data/local/tmp/pl-managed-credentials.json >/dev/null
collect() {
  adb shell rm -f /data/local/tmp/pl-managed-credentials.json >/dev/null 2>&1 || true
  adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/managed-proof.json managed-evidence/ >/dev/null 2>&1 || true
  adb shell 'ls /sdcard/Android/data/com.prettylisavpn.android.dev/files/managed-*.png' | tr -d '\r' | while read -r image; do
    adb pull "$image" managed-evidence/ >/dev/null 2>&1 || true
  done
}
trap collect EXIT
adb shell am instrument -w -r -e liveManaged true \
  -e class com.prettylisavpn.android.LiveManagedTest \
  com.prettylisavpn.android.dev.test/com.prettylisavpn.android.AcceptanceRunner \
  > managed-evidence/instrumentation.txt &
instrumentation=$!
previous=''
unchanged=0
while kill -0 "$instrumentation" 2>/dev/null; do
  sleep 10
  adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/managed-proof.json managed-evidence/ >/dev/null 2>&1 || true
  current=$(sha256sum managed-evidence/managed-proof.json 2>/dev/null || true)
  if [ "$current" = "$previous" ]; then unchanged=$((unchanged + 1)); else unchanged=0; fi
  previous="$current"
  if [ "$unchanged" -ge 30 ]; then
    adb exec-out screencap -p > managed-evidence/stalled.png
    adb shell am force-stop com.prettylisavpn.android.dev
    wait "$instrumentation" || true
    echo 'Acceptance stopped: no phase progress for five minutes'
    exit 1
  fi
done
wait "$instrumentation"
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
    assert row['connected'] and row['tunnel_https'] and row['cleanup'] and row.get('split_verified', True), row
    assert row['sustained_seconds'] >= 40, row
assert 'OK (1 test)' in Path('managed-evidence/instrumentation.txt').read_text()
print('Real packaged managed tunnels: verification, HTTPS, renewal and cleanup passed')
PY
