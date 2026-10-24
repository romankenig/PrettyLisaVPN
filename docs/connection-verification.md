# Strict connection verification

`UP` means only that the protocol tunnel exists. The connection manager emits
`CONNECTED` only after a fresh `ConnectionResult` has `tunnel_established: true`,
`internet_verified: true`, and `failure_code: null`. Restoration of an existing
UP tunnel also requires a fresh health check.

```text
DISCONNECTED -> CONNECTING -> TUNNEL_ESTABLISHED -> VERIFYING_INTERNET
                                                       | success -> CONNECTED
                                                       | failure -> FAILED
CONNECTED -> DEGRADED -> CONNECTED (recovered)
                     -> FAILED (3 consecutive failed checks)
CONNECTED/DEGRADED -> FAILED immediately on lost tunnel, route leak or egress mismatch
CONNECTED/DEGRADED -> DISCONNECTED on explicit disconnect or session expiry
```

Existing RECONCILING, DISCONNECTING and UNAVAILABLE states remain for session
restoration, teardown, and control-plane errors. They never render Connected.
Failure clears the success state before teardown; failed teardown stays visible
and permits another disconnect attempt. Windows 0.13.0 and Android 0.9.0 try
the next authorized supported candidate after confirmed local teardown. There
is no allocation of additional nodes; a missing runtime is never considered working.

## Native Windows implementation

`internet_verification.rs` performs a fresh DNS A query against the tunnel's
configured DNS servers, then a fresh HTTPS request to the resulting address.
Both sockets bind to the tunnel's source IPv4 and use Windows `IP_UNICAST_IF` to
pin transmission to its interface. `GetBestRoute2` checks the selected interface
against the tunnel LUID before and after each exchange. Failure to establish the
VPN route is fail-closed with `ROUTE_LEAK_DETECTED`. Probes never use the system
HTTP proxy, browser fetch, ICMP, DNS cache, or HTTP redirects.

Hickory parses DNS; rustls/ring and WebPKI roots validate the TLS certificate and
hostname; httparse parses HTTP headers and chunk lengths. No custom cryptography
is introduced. HTTP status AND configured body expectation must match. IP-body
endpoints must return a plain public IPv4 address. If an expected NAT egress IP
is configured, a mismatch produces `EGRESS_MISMATCH`. The observed egress address
is available in the native result but is not logged or promoted to UI diagnostics.
Raw DNS packets, HTTP responses, endpoint URLs, exception text and secrets are
never added to protocol diagnostics.

Checks have a shared 15-second native budget, socket operations capped at three
seconds, a 16 KiB response limit, and no connection reuse. The common layer bounds
health calls to 20 seconds. After success the manager checks every 30 seconds,
without overlapping monitor calls. Session expiration keeps running while DEGRADED.

## Configuration

Set `PRETTYLISA_HEALTH_CONFIG` in the **native process environment** before starting
the desktop application (`.env.example` documents it; Vite does not load native
settings). Supply 1-4 endpoints. Each requires an HTTPS hostname URL and a 2xx
`expected_status`, plus `expected_body` (exact UTF-8 bytes) or `public_ip_body`.

```json
{
  "endpoints": [
    {"url": "https://egress.example.com/ip", "expected_status": 200, "public_ip_body": true},
    {"url": "https://backup.example.com/ip", "expected_status": 200, "public_ip_body": true}
  ],
  "expected_egress_ip": "203.0.113.10"
}
```

The example egress address is a placeholder; use the actual public NAT address.
With `expected_egress_ip`, every endpoint must return an IP. Otherwise, fixed-body
endpoints can be used without public-IP discovery. Defaults are `api.ipify.org/`
and `checkip.amazonaws.com/` (HTTPS, 200, plain IP body). Deploy first-party health
endpoints for production control over availability and retention. Endpoint
redundancy never masks a route leak or egress mismatch.

Normalized failures: TRANSPORT_TIMEOUT, HANDSHAKE_FAILED,
TUNNEL_ESTABLISHED_NO_TRAFFIC, DNS_FAILED, HTTPS_CHECK_FAILED, EGRESS_MISMATCH,
ROUTE_LEAK_DETECTED, SERVER_UNREACHABLE, OBFUSCATION_FAILED, UNKNOWN. Older
configuration/runtime availability codes remain accepted for compatibility.

## Other protocol adapters

External TLS/QUIC runtimes still own their protocol and network setup. Successful
`start()` establishes a tunnel only. The adapter calls `health()` independently;
its response must supply explicit `verification.dns_verified`, `https_verified`
and `route_verified` booleans set to true. `egress_matches: false` fails immediately.
An old runtime that supplies only `internet_verified: true` cannot connect.
The runtime must implement real interface-pinned probes; these declarations are
an adapter contract, not a substitute for a deployed implementation.

## Automated evidence and limitations

- `home.test.tsx`: native handshake/start returns UP; the UI renders VERIFYING
  INTERNET; HTTPS fails; the UI renders FAILED. Neither rendered heading nor
  state-transition history ever contains Connected/CONNECTED.
- `vpnConnection.test.ts`: success, all normalized initial failures, failed
  handshake, fresh restoration, degradation, recovery, persistent failure,
  immediate route-leak failure, and stale/overlapping monitor results.
- Native tests cover expected status/body, DNS/HTTPS failure, malformed HTTP,
  egress mismatch, endpoint redundancy, unsafe configuration, and rejection of
  a real nonmatching Windows route before transmitting a probe.

The current WireGuard client supports IPv4 only. DNS truncation/TCP fallback,
private-CA endpoints, HTTP/2-only endpoints and non-Windows verification are not
implemented. These cases fail closed. This is verification of the VPN path, not
a system-wide kill switch or a guarantee about all application/IPv6 traffic.
Tests use controlled failures and loopback/mocked adapters; a live VPN outage
exercise requires a running node and privileged client setup and is not claimed
by these automated results.

Windows socket binding follows the documented
[IP_UNICAST_IF option](https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ip-socket-options).
