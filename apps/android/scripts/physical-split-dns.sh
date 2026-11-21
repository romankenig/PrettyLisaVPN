#!/usr/bin/env bash
set -euo pipefail

package=com.prettylisavpn.android.dev
fixture=$(mktemp -d)
mkdir -p split-dns-evidence
cleanup() {
  if sudo test -f "$fixture/dnsmasq.log"; then
    sudo grep -E '(direct|selected|uplink[^.]*)\.prettylisa\.test' "$fixture/dnsmasq.log" > split-dns-evidence/fixture-dns.txt || true
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
sudo dnsmasq --bind-interfaces --listen-address="${SPLIT_DNS_HOST:?Expected the runner DNS fixture address}" --no-resolv --no-hosts \
  --address=/prettylisa.test/10.0.2.2 \
  --pid-file="$fixture/dnsmasq.pid" --log-facility="$fixture/dnsmasq.log" --log-queries
python3 -m http.server 18080 --bind 127.0.0.1 --directory "$fixture" > "$fixture/http.log" 2>&1 &
http_pid=$!

adb shell settings put global private_dns_mode off
adb shell settings put global captive_portal_mode 0
# Use separate names so the direct lookup can only come from the test.
probe_uplink() {
  local uplink
  uplink=$(timeout 8 adb shell ping -c 1 -W 2 "$1.prettylisa.test" 2>&1 || true)
  printf '%s\n' "$uplink" | tee -a split-dns-evidence/uplink.txt
  [[ "$uplink" == *'(10.0.2.2)'* ]]
}
if ! probe_uplink uplink; then
  # Some emulator images use an independent Wi-Fi DNS proxy. Exercise the same
  # Android physical Network path over the emulated cellular connection.
  adb shell svc wifi disable
  adb shell svc data enable
  for ((attempt = 0; attempt < 4; attempt++)); do
    if probe_uplink "uplink-cell-$attempt"; then break; fi
    sleep 2
  done
  grep -Fq '(10.0.2.2)' split-dns-evidence/uplink.txt
fi
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
