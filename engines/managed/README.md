# PrettyLisaVPN managed engine (in development)

Separate executable, version 0.1.0. Xray-core 26.10.21 is pinned to source commit
`1b1647cd9ddf0abc34b981d4611fc03bcac1ca74` in go.mod/go.sum. The adapter is MIT;
Xray is MPL-2.0. The unpublished sing-box implementation was removed following
the owner's decision. No sing-box, sing-openvpn or sing-openconnect is linked.
REALITY's transitive LGPL rate limiter is replaced by the small, independently
implemented MIT adapter in `compat/ratelimit` (only the two required methods).
NAT-PMP is pinned to Apache-2.0 commit `2c56765bf4dfd2c849263d5f1b4eeef8fea74214`
with its complete license text.

This is **not yet an enabled client connection method**. Main-client wiring,
server authorization/revocation, packaging, tunnel-bound verification and DE/US
device acceptance remain pending. Linux builds check portability; automatic
desktop routing in this component targets Windows, not a Linux product release.

The private protocol is newline-delimited JSON on inherited stdin/stdout:
`version`, `start` with a typed `profile`, `status`, `stop`. No listening API,
arbitrary paths, scripts or raw Xray JSON. Profiles must come from authenticated
server session authorization. A country field is not proof of endpoint ownership.
Credentials stay in memory and never enter command lines or logs. EOF exits and
closes the tunnel. The Windows host must use a kill-on-close Job Object and kill
the helper if bounded cleanup fails. RUNNING is not proof of connectivity.

The generated profile supports WireGuard, VLESS/TLS, VLESS/REALITY/Vision,
VMess/TLS, Trojan/TLS, Shadowsocks AEAD/2022, Hysteria2 and Salamander. The TLS
proxies additionally support WebSocket, gRPC, HTTPUpgrade and XHTTP. Old HTTP/2
and QUIC transport names are rejected, not silently mapped to a different wire
format. Hysteria1, SSH, UoT and other article families need separate adapters.
OpenVPN/OpenConnect GPL libraries are not part of this component.

All application packets, including DNS to 1.1.1.1, use the selected encrypted
outbound. Uplinks are IP addresses; SNI does not require direct DNS. Both IP
families enter TUN; IPv6 is rejected until the nodes provision it. No sniffing,
access/DNS/error logging, direct fallback or insecure TLS setting is exposed.
Windows uses Xray's TUN routing and DNS/WFP protections. The parent must provide
the vetted Wintun distribution and required privileges before enabling it.

```text
go test ./...
go vet ./...
go build -trimpath ./cmd/pl-engine
```

Go 1.27.3. CI checks dependency licenses against MIT/MPL-2.0 and permissive
BSD/Apache/ISC licenses, failing on GPL/AGPL or unknown licenses. It does not
replace redistribution obligations: ship the exact dependency notices and
corresponding MPL source with a binary release, including any modified files.
The current workflow builds and tests; it does not publish a release.

The companion source is in `apps/android/engine-app`. Its separate Go runtime
shares one VpnService consent, protects every outgoing socket and duplicates the
application-owned TUN descriptor. It never loads a native Go library into the
main PrettyLisaVPN Android process.
