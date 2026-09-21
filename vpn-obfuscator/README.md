# PrettyLisaVPN UDP obfuscator (Stage 3AB)

This service is a deliberately small first-party transport between the public network and an
unchanged local WireGuard listener. It does not parse WireGuard packets, inspect VPN traffic, call
the Backend, or replace WireGuard cryptography.

## Packet path

```text
client -> public UDP/443 -> prettylisavpn-obfuscator
       -> 127.0.0.1:51820/udp -> WireGuard wg0 -> Internet
```

Replies use the per-client connected loopback UDP socket in reverse. Each public client source
endpoint receives its own loopback socket, so multiple clients can use the relay concurrently.
Idle mappings expire after a configurable timeout.

WireGuard's Linux UDP socket listens on all local addresses; it cannot be bound to only loopback.
Isolation is therefore enforced by using a distinct internal port and removing every public UFW
and provider-firewall allow rule for that port. The obfuscator itself always forwards to
`127.0.0.1`.

## Version 1 envelope

```text
+---------+----------------+------------------------------------------+
| version | random nonce   | ChaCha20-Poly1305 ciphertext + auth tag |
| 1 byte  | 12 bytes       | encrypted length + packet + padding     |
+---------+----------------+------------------------------------------+
```

The version byte is authenticated as associated data. The encrypted plaintext starts with a
two-byte big-endian packet length, followed by the unchanged WireGuard datagram and 0..255 random
padding bytes by default. Every packet receives a new cryptographically random nonce and random
padding. Raw WireGuard message headers are therefore not visible on the public interface.

V1 intentionally does not provide fragmentation, timing obfuscation, port hopping, replay state,
STUN, QUIC, or TLS impersonation. WireGuard itself rejects replayed inner packets. The protocol
codec lives in `protocol.py`; UDP forwarding lives in `server.py`, and the `ObfuscationTransport`
interface permits later versioned modes.

## Configuration

`PRETTYLISA_OBFUSCATION_SECRET` is required and must be canonical Base64 encoding of exactly 32
random bytes. Ansible generates it on the VPN node in
`/etc/prettylisavpn-obfuscator/secret.env` with mode `0640`; it is never returned to the controller.
Never place it in inventory, Git, command output, or service logs.

Other environment variables:

| Variable | Default |
| --- | --- |
| `PRETTYLISA_OBFUSCATION_BIND_HOST` | `0.0.0.0` |
| `PRETTYLISA_OBFUSCATION_BIND_PORT` | `443` |
| `PRETTYLISA_WIREGUARD_HOST` | `127.0.0.1` |
| `PRETTYLISA_WIREGUARD_PORT` | `51820` |
| `PRETTYLISA_MAX_PACKET_SIZE` | `4096` |
| `PRETTYLISA_MAX_PADDING_SIZE` | `255` |
| `PRETTYLISA_MAX_CLIENTS` | `1024` |
| `PRETTYLISA_CLIENT_IDLE_TIMEOUT_SECONDS` | `180` |

Logs contain service state and aggregate counters only. They do not contain secrets, client
addresses, packet bodies, WireGuard keys, DNS queries, URLs, or browsing destinations.

## Development checks

```bash
python3.13 -m venv vpn-obfuscator/.venv
vpn-obfuscator/.venv/bin/pip install -e 'vpn-obfuscator[dev]'
vpn-obfuscator/.venv/bin/ruff format --check vpn-obfuscator
vpn-obfuscator/.venv/bin/ruff check vpn-obfuscator
vpn-obfuscator/.venv/bin/mypy --config-file vpn-obfuscator/pyproject.toml vpn-obfuscator/src
vpn-obfuscator/.venv/bin/pytest vpn-obfuscator/tests -q
```


## Independent packet providers

The default legacy `PRETTYLISA_V1` mode is unchanged. Explicitly select `NONE`
(version 0) or `SIMPLE_PACKET_WRAPPER_V1` (version 1) using the environment in
[.env.example](.env.example). Neither mode needs a shared secret. The simple wrapper
is keyless reversible framing, not encryption or integrity protection; the VPN
protocol remains responsible for security. Do not mix its packets with legacy V1.

See [provider architecture, compatibility and measured overhead](../docs/obfuscation-providers.md).
Run `python tools/benchmark_providers.py` in this project's environment to reproduce
the codec CPU benchmark. No deployment is automatically changed.
