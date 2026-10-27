#!/usr/bin/env bash
set -euo pipefail
mkdir -p wireguard-evidence
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb push "$RUNNER_TEMP/pl-wg-credentials.json" /data/local/tmp/pl-wg-credentials.json >/dev/null
trap 'adb shell rm -f /data/local/tmp/pl-wg-credentials.json >/dev/null 2>&1 || true' EXIT
adb shell am instrument -w -r -e liveWireGuard true \
  -e class com.prettylisavpn.android.LiveWireGuardTest \
  com.prettylisavpn.android.dev.test/com.prettylisavpn.android.AcceptanceRunner \
  > wireguard-evidence/instrumentation.txt
adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/wireguard-proof.json wireguard-evidence/ >/dev/null
adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/wireguard-proof.png wireguard-evidence/ >/dev/null
python3 - <<'PY'
import json
from pathlib import Path
proof = json.loads(Path('wireguard-evidence/wireguard-proof.json').read_text())
assert proof['phase'] == 'CONNECTED' and proof['method'] == 'wireguard', proof
assert proof['sustained_seconds'] >= 120 and proof['wireguard']['heartbeats'] >= 3, proof
assert proof['public_api_reachable'] and proof['tunnel_https_rechecked'] and not proof['notice_visible'], proof
assert 'OK (1 test)' in Path('wireguard-evidence/instrumentation.txt').read_text()
print('Real WireGuard: two minutes, repeated heartbeats, HTTPS, UI reachability and confirmed cleanup passed')
PY
