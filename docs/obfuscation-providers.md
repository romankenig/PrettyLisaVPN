# Independent obfuscation providers

```text
VPN protocol (encryption/authentication)
    -> optional obfuscation provider
    -> UDP socket or supported external TLS transport
```

`VpnProtocol` retains its lifecycle methods. The independent `ObfuscationProvider`
interface and registry own mode/version compatibility and transport planning.
Native Rust and node-side Python packet providers implement `encode` and `decode`
on opaque VPN packets; they do not inspect inner IP traffic or manage VPN keys.
Adding a provider extends its registry and transport implementation, not the
`VpnProtocol` interface. Existing `PRETTYLISA_V1` and upstream obfuscator integration
remain legacy modes; neither is renamed to the new simple wrapper.

## Configuration

Common connection configuration now accepts:

```json
{
  "protocol": "WIREGUARD",
  "transport": "UDP",
  "port": 443,
  "encryption_mode": "WIREGUARD",
  "obfuscation_mode": "SIMPLE_PACKET_WRAPPER_V1",
  "obfuscation_version": 1,
  "transport_parameters": { "max_datagram_size": 1400 },
  "country": "DE",
  "mtu": 1280,
  "dns_mode": "VPN",
  "routing_mode": "FULL_TUNNEL"
}
```

The `port` is the public provider listener port. The WireGuard bootstrap endpoint
must match it. The server forwards decoded ciphertext to its local WireGuard port.
`NONE` uses version 0 (omission remains accepted for existing clients) and empty
parameters. `SIMPLE_PACKET_WRAPPER_V1` requires explicit version 1; its only allowed
parameter is `max_datagram_size`, default 1400. `TLS_TRANSPORT` requires version 1
and empty parameters; endpoint identity and native trust/credential references stay
in the owning external protocol adapter's existing bootstrap contract.

Unknown versions, incompatible transports, unknown parameters and secret-like
fields are rejected with fixed error codes. New API fields are optional so existing
candidate responses retain their shape. Backend validation supports them, but the
current Autopilot provisioner still emits its existing legacy configuration; this
change does not turn on a wrapper fleet-wide or add automatic provider selection.
No new UI settings, schema migration, or automatic fallback is introduced.

## SIMPLE_PACKET_WRAPPER_V1 wire format

| Offset | Size | Meaning |
| --- | --- | --- |
| 0 | 4 | ASCII `PLPW` |
| 4 | 1 | Version `1` |
| 5 | 1 | Reserved flags, must be `0` |
| 6 | 2 | Unsigned big-endian payload length |
| 8 | N | Input bytes XOR `0xA5` |

This is public, keyless, reversible framing. It is **not cryptographic protection**
and provides no confidentiality, authentication, integrity, replay defense, or
claim of resistance to traffic classification. Corrupted payloads with valid framing
can decode; the underlying VPN must authenticate and reject them. Encryption and
VPN security remain WireGuard's responsibility. There is no nonce, shared secret,
stream state, or retransmission mechanism. Loss, duplication, reordering, and a new
connection cannot desynchronize the codec.

Zero-length payloads, invalid magic/version/flags, inconsistent lengths, trailing
bytes, truncated frames and oversized packets are rejected. The codec supports
outer UDP payload budgets up to 65507 bytes; oversized local packets are dropped
without terminating the forwarding worker. Datagram sizes are bounded before
transformation and no packet contents or new secret values are logged.

## MTU and latency

`max_datagram_size` is the outer **UDP payload** budget, excluding IP/UDP headers.
The maximum wrapped payload is that budget minus 8. With an IPv4 WireGuard IP MTU
of 1280, an encrypted data packet is 1312 bytes (including WireGuard overhead),
and its wrapped payload is 1320 bytes. Configuration therefore requires at least
1320 bytes. IPv4/UDP adds another 28 bytes on the path. The default budget is 1400;
the provider does not discover path MTU, fragment, or reassemble packets. Larger
budgets require an appropriate network path and may cause IP fragmentation.

Local Python 3.13.15/Windows benchmark, median of five runs of 100,000 encode/decode
pairs, measured with `vpn-obfuscator/tools/benchmark_providers.py`:

| Input bytes | Extra bytes | Byte overhead | NONE CPU μs/pair | Wrapper CPU μs/pair |
| --- | --- | --- | --- | --- |
| 148 | 8 | 5.405% | 0.157 | 0.830 |
| 1312 | 8 | 0.610% | 0.169 | 1.931 |
| 4096 | 8 | 0.195% | 0.164 | 4.088 |

The representative 1312-byte case adds about 1.76 μs of codec CPU time. This is not
network latency, native Rust performance, or a throughput guarantee. The reused
native forwarding worker polls at 1 ms; OS scheduling and the extra loopback hop can
dominate actual latency. No WAN latency or TLS handshake benchmark was performed.

## Compatibility matrix

| Protocol | Network transport | NONE | SIMPLE_PACKET_WRAPPER_V1 | TLS_TRANSPORT |
| --- | --- | --- | --- | --- |
| WireGuard | UDP, configurable port | Native direct | Native relay + matching node forwarder | Rejected |
| OpenVPN | TCP 443 | External OpenVPN runtime | Rejected | Conditional: explicit runtime capability |
| MASQUE | QUIC over UDP 443 | External MASQUE runtime | Rejected | Rejected; QUIC is not a TLS record stream |

`TLS_TRANSPORT` is delegated only if the injected external runtime advertises
`TLS_TRANSPORT:1`. The request requires TLS 1.3 minimum and certificate validation.
OpenVPN's TLS control channel alone does not imply support for an independent TLS
carrier. No home-grown TLS record encoding, certificate bypass, or claim of ordinary
browser TLS resemblance is added. The external runtime owns the TLS carrier and its
framing, buffering, reconnect, certificate policy and teardown.

The repository still does not bundle that TLS carrier or the OpenVPN/MASQUE services
from the profile stage. Tests prove delegation and rejection with mock runtimes;
they do not claim live OpenVPN-over-TLS interoperability. Missing services remain
unavailable. Production certificate provisioning, service packaging and live TLS
carrier tests remain required before enabling this mode.

## Node setup and verification

The existing Python UDP forwarder now accepts `NONE` and
`SIMPLE_PACKET_WRAPPER_V1` through `PRETTYLISA_OBFUSCATION_MODE`. See
[`vpn-obfuscator/.env.example`](../vpn-obfuscator/.env.example). It requires no shared
secret for these modes. Load the environment explicitly; the example is not an
automatically loaded dotenv file. Restart the service after changing mode/version.
Both ends must agree on the framing version and packet budget. Keep the local
WireGuard upstream loopback-only, open the selected public UDP listener, and retain
the existing bounded per-client sockets and idle expiry. No Ansible role or running
deployment was switched by this change.

Tests cover direct VPN calls, wrapped VPN calls, conditional TLS delegation,
reconnect, unknown provider rejection, exact MTU bounds, large packets, malformed
frames, deterministic loss, duplicates and reordering. Rust and Python share a fixed
wire-format test vector. Native and Python UDP loopback tests exercise actual relay
sockets; native loss/oversize/malformed tests confirm a later valid packet still
passes. Full tunnel-to-public-Internet tests were not run. The existing executable-
dependent legacy obfuscator test remains ignored unless its binary is supplied.
