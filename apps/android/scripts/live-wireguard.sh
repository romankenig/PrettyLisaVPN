#!/usr/bin/env bash
set -euo pipefail
mkdir -p wireguard-evidence
expected_method=wireguard
if [ "${FORCE_RELAY:-false}" = true ]; then
  # Runner is disposable; block both possible direct exits, leaving RU and HTTPS intact.
  sudo iptables -I OUTPUT 1 -p udp --dport 51820 -j DROP
  sudo iptables -I FORWARD 1 -p udp --dport 51820 -j DROP
  expected_method=wireguard_relay
fi
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
adb push "$RUNNER_TEMP/pl-wg-credentials.json" /data/local/tmp/pl-wg-credentials.json >/dev/null
trap 'adb shell rm -f /data/local/tmp/pl-wg-credentials.json >/dev/null 2>&1 || true' EXIT
adb shell am instrument -w -r -e liveWireGuard true \
  -e expectedMethod "$expected_method" \
  -e class com.prettylisavpn.android.LiveWireGuardTest \
  com.prettylisavpn.android.dev.test/com.prettylisavpn.android.AcceptanceRunner \
  > wireguard-evidence/instrumentation.txt
adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/wireguard-proof.json wireguard-evidence/ >/dev/null
adb pull /sdcard/Android/data/com.prettylisavpn.android.dev/files/wireguard-proof.png wireguard-evidence/ >/dev/null
EXPECTED_METHOD="$expected_method" python3 - <<'PY'
import json
import os
from pathlib import Path
proof = json.loads(Path('wireguard-evidence/wireguard-proof.json').read_text())
assert proof['phase'] == 'CONNECTED' and proof['method'] == os.environ['EXPECTED_METHOD'], proof
if os.environ['EXPECTED_METHOD'] == 'wireguard_relay':
    assert proof['attempts'][:2] == ['wireguard', 'wireguard_relay'], proof
assert proof['sustained_seconds'] >= 120 and proof['wireguard']['heartbeats'] >= 3, proof
assert proof['deep_idle_confirmed'] and proof['idle_seconds'] >= 300 and proof['same_vpn_network'], proof
assert proof['public_api_reachable'] and proof['tunnel_https_rechecked'] and not proof['notice_visible'], proof
assert 'OK (1 test)' in Path('wireguard-evidence/instrumentation.txt').read_text()
print('Real WireGuard: initial verification, five minutes deep Doze, same tunnel after wake, HTTPS and confirmed cleanup passed')
PY
