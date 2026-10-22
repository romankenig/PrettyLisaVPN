#!/usr/bin/env bash
# Isolated ephemeral CI WireGuard node. No application backend or credentials are used.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true ]] || { echo 'CI-only test peer' >&2; exit 1; }
sudo ip link add wgplci type wireguard
vpn_peer_private=$(mktemp)
chmod 600 "$vpn_peer_private"
wg genkey > "$vpn_peer_private"
sudo wg set wgplci listen-port 51820 private-key "$vpn_peer_private"
wg pubkey < "$vpn_peer_private" > /tmp/prettylisa-test-peer-public
rm -f "$vpn_peer_private"
sudo ip address add 10.77.0.1/24 dev wgplci
sudo ip link set wgplci up
sudo sysctl -q -w net.ipv4.ip_forward=1
sudo iptables -t nat -A POSTROUTING -s 10.77.0.0/24 -j MASQUERADE
sudo iptables -I FORWARD -i wgplci -j ACCEPT
sudo iptables -I FORWARD -o wgplci -j ACCEPT
cleanup() {
  sudo ip link delete wgplci || true
  sudo iptables -t nat -D POSTROUTING -s 10.77.0.0/24 -j MASQUERADE || true
  sudo iptables -D FORWARD -i wgplci -j ACCEPT || true
  sudo iptables -D FORWARD -o wgplci -j ACCEPT || true
  rm -f /tmp/prettylisa-test-peer-public
}
trap cleanup EXIT
trap 'exit 0' TERM INT
package=com.prettylisavpn.android.dev
peer_dir=/sdcard/Android/data/$package/files/acceptance/vpn
# The emulator exchanges public keys/ack markers only. No private key leaves either peer.
while true; do
  if adb shell test -f "$peer_dir/client-public-key" 2>/dev/null; then
    client_public=$(adb shell cat "$peer_dir/client-public-key" | tr -d '\r\n')
    [[ "$client_public" =~ ^[A-Za-z0-9+/]{43}=$ ]] || exit 1
    sudo wg set wgplci peer "$client_public" allowed-ips 10.77.0.2/32
    adb shell rm "$peer_dir/client-public-key"
    adb shell touch "$peer_dir/peer-ready"
  fi
  if adb shell test -f "$peer_dir/remove-peer" 2>/dev/null; then
    if [[ -n "${client_public:-}" ]]; then sudo wg set wgplci peer "$client_public" remove; fi
    adb shell rm "$peer_dir/remove-peer"
    adb shell touch "$peer_dir/peer-removed"
  fi
  sleep 0.3
done
