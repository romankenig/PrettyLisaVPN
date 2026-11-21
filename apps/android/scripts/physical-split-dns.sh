#!/usr/bin/env bash
set -euo pipefail

package=com.prettylisavpn.android.dev
fixture=$(mktemp -d)
mkdir -p split-dns-evidence
cleanup() {
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
  --pid-file="$fixture/dnsmasq.pid" --log-facility="$fixture/dnsmasq.log" --log-queries
python3 -m http.server 18080 --bind 127.0.0.1 --directory "$fixture" > "$fixture/http.log" 2>&1 &
http_pid=$!

adb shell settings put global private_dns_mode off
adb install -r apk/app-debug.apk
adb install -r test-apk/app-debug-androidTest.apk
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
  > split-dns-evidence/result.txt
