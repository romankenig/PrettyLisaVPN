#!/usr/bin/env bash
set -euo pipefail

package=com.prettylisavpn.android.dev
fixture=$(mktemp -d)
mkdir -p split-dns-evidence
cleanup() {
  if sudo test -f "$fixture/dnsmasq.log"; then
    sudo grep -E '(direct|selected|uplink)\.prettylisa\.test' "$fixture/dnsmasq.log" > split-dns-evidence/fixture-dns.txt || true
  fi
  if [[ -f "$fixture/dnsmasq.pid" ]]; then
    sudo kill "$(cat "$fixture/dnsmasq.pid")" || true
  fi
  if [[ -n "${http_pid:-}" ]]; then
    kill "$http_pid" || true
  fi
  rm -r -- "$fixture"
}
trap cleanup EXIT

printf '%s\n' direct-split-dns-proof > "$fixture/proof.txt"
sudo dnsmasq --bind-interfaces --listen-address=127.0.0.1 --no-resolv --no-hosts \
  --address=/direct.prettylisa.test/10.0.2.2 --address=/selected.prettylisa.test/10.0.2.2 \
  --address=/uplink.prettylisa.test/10.0.2.2 \
  --pid-file="$fixture/dnsmasq.pid" --log-facility="$fixture/dnsmasq.log" --log-queries
python3 -m http.server 18080 --bind 127.0.0.1 --directory "$fixture" > "$fixture/http.log" 2>&1 &
http_pid=$!

adb shell settings put global private_dns_mode off
adb shell settings put global captive_portal_mode 0
# Check a separate hostname so the direct lookup below can only come from the test.
uplink=$(timeout 8 adb shell ping -c 1 -W 2 uplink.prettylisa.test 2>&1 || true)
printf '%s\n' "$uplink" | tee split-dns-evidence/uplink.txt
grep -Fq '(10.0.2.2)' split-dns-evidence/uplink.txt
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
# Authorize only this APK on the disposable emulator. The app still calls VpnService.prepare.
adb shell cmd appops set "$package" ACTIVATE_VPN allow
adb shell am instrument -w -r -e physicalSplitDns true \
  -e class com.prettylisavpn.android.PhysicalSplitDnsTest \
  "$package.test/com.prettylisavpn.android.AcceptanceRunner" | tee split-dns-evidence/instrumentation.txt
grep -Fq 'OK (1 test)' split-dns-evidence/instrumentation.txt
sudo grep -Fq 'query[A] direct.prettylisa.test' "$fixture/dnsmasq.log"
if sudo grep -Eq 'query\[[^]]+\] selected\.prettylisa\.test' "$fixture/dnsmasq.log"; then
  echo "A selected domain reached the physical DNS fixture"
  exit 1
fi
printf '%s\n' "Direct HTTP reached the host after Android DNS resolution. The selected domain remained in the VPN." \
  | tee split-dns-evidence/result.txt
