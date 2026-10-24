# Connection profiles

See [Obfuscation providers](obfuscation-providers.md) for independent framing and
conditional TLS-carrier capabilities.

Profiles describe implementation capabilities, not UI controls. Users still choose
Autopilot or country. Nodes and profile preferences are operational concerns. No
node selection is performed by clients. Windows 0.13.0 tries authorized candidates
in order, stopping each failed attempt before moving on. Missing engines cannot
produce a successful connection. See [the ongoing transport task](vpn-methods-from-article.md).

| Profile | Transport / ports | Security | Runtime in this repository |
| --- | --- | --- | --- |
| `WIREGUARD_UDP` | UDP, configurable 1–65535; default 51820 | Standard WireGuard encryption | Existing WireGuardNT adapter, explicit direct UDP |
| `OPENVPN_TLS_TCP` | TCP 443 | TLS 1.3 control channel; AES-256-GCM data channel | Validated external runtime adapter; service not bundled |
| `MASQUE_QUIC` | UDP 443 | QUIC security using TLS 1.3 | Validated external runtime adapter; service not bundled |

The client catalog is `apps/windows/src/vpn/profiles.ts`; the backend catalog is
`backend/src/prettylisavpn/vpn_nodes/profiles.py`. Each declares protocol, transport,
supported ports, encryption, obfuscation, IPv6, and full-tunnel capabilities.
`VpnProtocol.capabilities` exposes the corresponding descriptor. Capabilities are
the integration contract, not a claim that an external runtime is installed.
The initial implementations request IPv4 full-tunnel routing, VPN DNS, and MTU
1280. IPv6 and ordinary-TLS resemblance remain false. WireGuard and OpenVPN now
declare obfuscation capability subject to the independent provider compatibility
checks; MASQUE does not.

OpenVPN has its own framing and data channel: TCP 443 and TLS 1.3 do not make it
ordinary HTTPS. It must not be marketed as browser-identical TLS. A future adapter
with verified TLS resemblance can declare that capability. There is no custom
cryptography or new packet masking in these profiles. Existing optional native
WireGuard wrappers remain available only through the legacy `NATIVE` contract;
the explicit standard WireGuard profile sets `direct: true` and bypasses them.

## Node configuration and persistence

`VpnNodeRegistration.connection_profiles` accepts an ordered tuple of validated
`NodeConnectionProfile` values. A node may declare all three families, for example:

```python
connection_profiles=(
    NodeConnectionProfile(profile=ProfileId.WIREGUARD_UDP, ports=(51820,)),
    NodeConnectionProfile(profile=ProfileId.OPENVPN_TLS_TCP, ports=(443,)),
    NodeConnectionProfile(profile=ProfileId.MASQUE_QUIC, ports=(443,)),
)
```

Operator declarations serialize to PostgreSQL JSONB as:

```json
[
  {"profile": "WIREGUARD_UDP", "ports": [51820]},
  {"profile": "OPENVPN_TLS_TCP", "ports": [443]},
  {"profile": "MASQUE_QUIC", "ports": [443]}
]
```

No secrets belong in this metadata. Duplicate profiles/ports, invalid ports,
unsupported ports, and unknown fields are rejected. TLS and QUIC initially support
443 only; WireGuard supports configurable ports. TCP 443 and UDP 443 may coexist.
An operator must only declare ports actually served by that node.

Migration `0016_node_profiles` adds the column and backfills existing nodes with
WireGuard at their existing port. SQL NULL remains the compatibility sentinel for
legacy registration/import code; it resolves to the current WireGuard port.
An explicit empty array means no supported profiles. Re-registration that omits
profiles preserves existing explicit declarations. A change to the legacy
WireGuard port must also update any explicit WireGuard declaration.

The current backend provisioner still creates WireGuard peers only. Eligibility
therefore requires a declared WireGuard profile containing `wireguard_port`.
TLS/QUIC-only nodes, empty declarations, or a mismatched WireGuard port are excluded
from availability and placement. Merely declaring TLS/QUIC does not provision it,
advertise runnable candidates, or route a session through the backend API.
Existing candidate responses and legacy clients retain their current behavior.

## Client adapters and runtime boundary

`createProfileConfig(profile, country, port?)` creates a validated common config.
`createProfileAdapter(profile, dependencies)` returns a `VpnProtocol`. Each can be
passed to `connectFirstCandidate` or the connection manager. This is explicit
construction; the factory does not implement selection or fallback.

WireGuard uses the native controller. OpenVPN and MASQUE use the injected
`ExternalTunnelRuntime` port, which owns start, stop, status and health. An external
executable/service must be controlled by an implementation of this port, not by
React or the session manager. No arbitrary commands, executable paths, script
options, raw private keys, or certificate-verification bypasses are accepted by
the adapter's bootstrap payload. It contains only endpoint, server name,
credential reference, and trust-store reference. The adapter requests TLS 1.3
minimum and mandatory certificate validation. A service implementation must enforce
these requirements, verify the negotiated profile, resolve references in native
secure storage, manage TUN/routes/DNS, and verify Internet traffic through the tunnel.

Missing services produce `RUNTIME_UNAVAILABLE`. Validation failures never invoke
them. Startup exceptions and unverified connections trigger teardown without trying
another candidate. Runtime error text and arbitrary result fields are discarded;
diagnostics expose a closed set of status fields with no runtime output or secrets.

## Dependencies and deployment requirements

No new npm, Cargo or Python package is added by this architecture stage.

- WireGuard: existing WireGuardNT DLL, native key storage, administrator privileges,
  a node WireGuard listener on the declared UDP port, firewall ingress, forwarding,
  NAT, and the existing peer-provisioning agent. The legacy application default is
  preserved; an explicit profile config selects direct UDP.
- OpenVPN: deploy matching maintained OpenVPN client/server builds with TLS 1.3
  capable OpenSSL. Enforce TLS 1.3, authenticated server identity, AES-256-GCM data
  encryption and disable compression. Require client authentication, a TCP 443
  listener, TUN, forwarding/NAT, VPN DNS and controlled route teardown. Package a
  privileged native service implementation of the runtime port before enabling it.
- MASQUE: deploy an authenticated HTTP/3 CONNECT-IP implementation of RFC 9484 over
  UDP 443, with HTTP Datagrams, TLS 1.3 certificate validation, address allocation,
  TUN, DNS, forwarding/NAT and teardown. A maintained QUIC/HTTP3 library such as
  Cloudflare quiche can supply the transport/TLS stack; it is not itself a packaged
  CONNECT-IP VPN. Do not ship quiche's example CLI apps as a production VPN runtime.

Select, pin and review actual release builds, licensing and security advisories
before distribution. This stage does not assert a version-specific audit for an
unselected service or add an unaudited cryptographic implementation.

Primary references:

- [OpenVPN manual: transport, TLS minimum and data ciphers](https://openvpn.net/community-docs/community-articles/openvpn-2-6-manual.html)
- [RFC 9484: Proxying IP in HTTP](https://www.rfc-editor.org/rfc/rfc9484.html)
- [RFC 9001: Using TLS to Secure QUIC](https://www.rfc-editor.org/rfc/rfc9001.html)
- [quiche library and example application limitations](https://github.com/cloudflare/quiche)

## Unsupported pieces and validation

TLS/QUIC process/service bridges, bundled binaries, node deployment roles, credentials
and trust provisioning, per-profile readiness checks, generic session bootstrap
payloads, and end-to-end Internet verification with real TLS/QUIC servers remain
TODOs. Default desktop/session provisioning remains WireGuard. IPv6, split routing,
TLS camouflage, extra TLS/QUIC ports and automatic fallback are not implemented.
The Chrome extension still requires a separate browser-only proxy integration.

Tests cover all three profile constructors and the common connection interface,
capability/configuration validation, direct WireGuard configuration, runtime
unavailability, sanitization, failed-start cleanup, and no fallback. Backend tests
cover multi-profile declarations, legacy compatibility, eligibility gating,
registration, and PostgreSQL persistence. Mocked TLS/QUIC runtime tests validate the
adapter boundary; they do not prove network interoperability or a deployed service.
