# VPN protocol boundary

The capability catalog and multi-profile node declarations extend this boundary;
see [Connection profiles](connection-profiles.md) for runtime availability and
server/client requirements.

The Windows UI uses `VpnConnectionManager`. The manager owns session lifecycle,
expiry, reconciliation, cleanup, and product state. It depends on `VpnProtocol`
and `VpnSessionProvisioner`; it neither manages WireGuard keys nor calls native
WireGuard commands. `defaultConnection.ts` is the composition root.

`VpnProtocol` supplies `connect(config)`, `disconnect()`, `status()`, `health()`,
and `diagnostics()`. `ConnectionResult` distinguishes tunnel establishment from
Internet verification and includes a stable failure code and safe diagnostics.
`ProtocolConfiguration` combines the common `ConnectionConfig` fields with an
opaque `parameters` payload interpreted only by the protocol adapter.

The first adapter is WireGuard. Its provisioner obtains the local public key,
creates the backend session, and translates the existing bootstrap response.
Private keys remain in native storage. The adapter preserves native startup,
including handshake and data-plane verification, and the existing packet
transport policy. `transport=NATIVE` and `obfuscation_mode=NATIVE` mean use that
existing local policy; they do not select a new transport. MTU remains 1280,
with VPN DNS, full-tunnel routing, and WireGuard encryption. Unsupported settings
fail explicitly instead of being silently ignored.

`health()` combines the last successful startup verification in this adapter
instance with current native state and transport health. It does not perform a
fresh Internet probe. After adapter recreation, Internet verification is unknown
(represented as false) until a successful connect. Existing restart reconciliation
continues to use native status. Diagnostics expose only status, transport health,
and numeric byte counters. Native messages, bootstrap payloads, endpoints, keys,
and tokens are never copied into these diagnostics or connection results.

## Ordered candidates and compatibility

New clients send `X-VPN-Candidates: 1` on session creation and current-session
requests. The backend then includes an ordered `candidates` array. Legacy clients
receive the original response shape, and the new client accepts legacy responses
by constructing the equivalent single WireGuard configuration.

For this stage the backend returns exactly one candidate: the already provisioned
WireGuard session. Additional nodes are not provisioned. An explicit empty list
fails; the client attempts only the first candidate and never retries another.
The legacy `transport` payload supplies that candidate's WireGuard bootstrap data.
Node profile declarations now have their own migration; see the profile guide.

Each candidate describes country, protocol, transport, port, encryption mode,
obfuscation mode, MTU, DNS mode, and routing mode. The backend's internal
`ConnectionConfig` also carries `node_id`; the HTTP response excludes it.
Selection requests still accept only Autopilot or country plus the provisioning
public key, and reject node targeting. React product/discovery state has no node
or protocol settings.

## Completing additional runtime integrations

1. Implement the five `VpnProtocol` methods in a separate adapter. Interpret its
   payload there, map errors to stable codes, and construct allowlisted diagnostics.
2. Add its backend provisioning and validated bootstrap payload contract. Extend
   the currently WireGuard-specific API bootstrap schema and supply that payload
   through a `VpnSessionProvisioner`; keep credentials out of common orchestration.
3. Wire the implementation at the composition root, selecting by the first
   candidate's protocol and retaining the active implementation for status and
   disconnect. The manager and UI do not need protocol-specific branches.
4. Add adapter and contract tests. Any policy for trying subsequent candidates
   requires a separate stage; profile adapters do not implement fallback.
