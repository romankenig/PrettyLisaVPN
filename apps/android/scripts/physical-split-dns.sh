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
  --local=/prettylisa.test/ --address=/prettylisa.test/10.0.2.2 \
  --pid-file="$fixture/dnsmasq.pid" --log-facility="$fixture/dnsmasq.log" --log-queries
python3 -m http.server 18080 --bind 127.0.0.1 --directory "$fixture" > "$fixture/http.log" 2>&1 &
http_pid=$!

adb shell settings put global private_dns_mode off
adb shell settings put global captive_portal_mode 0
# Connect netd directly to the runner fixture on the disposable API 35 image.
# This keeps the real Android per-Network resolver and bypasses the emulator's DNS proxy.
adb root
adb wait-for-device
test "$(adb shell id -u | tr -d '\r')" = 0
adb shell svc data disable
adb shell svc wifi enable
adb shell cmd wifi set-ipreach-disconnect disabled
adb shell cmd wifi connect-network AndroidWifi open
wifi_ready=false
for ((attempt = 0; attempt < 30; attempt++)); do
  networks=$(adb shell dumpsys connectivity)
  uplink_id=$(sed -n 's/.*Active default network: \([0-9][0-9]*\).*/\1/p' <<< "$networks")
  if [[ "$uplink_id" =~ ^[0-9]+$ ]] &&
      grep -qE "NetworkAgentInfo\\{network\\{$uplink_id\\}.*WIFI CONNECTED.*10\\.0\\.2\\.[0-9]+/24" <<< "$networks" &&
      adb shell ping -c 1 -W 1 10.0.2.2 >/dev/null 2>&1; then
    wifi_ready=true
    break
  fi
  sleep 1
done
if [[ "$wifi_ready" != true ]]; then
  echo 'The isolated Wi-Fi network did not acquire a default route'
  exit 1
fi
# IDnsResolver.setResolverConfiguration is transaction 3. The 92-byte
# ResolverParamsParcel sets the network ID, resolver timings and DNS servers.
adb shell "service call dnsresolver 3 i32 1 i32 92 i32 $uplink_id i32 1800 i32 25 i32 8 i32 64 i32 1000 i32 2 i32 1 s16 10.0.2.2 i32 0 s16 '' i32 0 i32 0 s16 '' i32 0"
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
