# Native SoftEther wire codecs

MIT portions from https://github.com/wanan9999/veepin at
`6e8d2aca383ee2e74fb7e1ee3f01adfc1d1d2596`, copyright 2026 Remy.
LICENSE-UPSTREAM and upstream-files.json retain the license and SHA-256 hashes
of the original files. Only PACK/HTTP/Ethernet-block/authentication/policy codecs
and their tests are retained. Traffic shaping, bridges, host TUN and the original
session implementation are excluded. Local control limits are 64 KiB and 256
elements/values; duplicate fields and trailing data are rejected.

PrettyLisaVPN owns strict pinned TLS 1.2+ chain/name/expiry verification, fresh
challenge authentication, per-lease resource ownership, IPv4 source validation,
ARP and a bounded in-memory IP stack shared with SSTP. The managed segment has
static client 172.30.252.2 and gateway 172.30.252.1, one TLS connection, no
compression, UDP acceleration, DHCP, host routes or cross-session L2 bridging.
The protocol's SHA-0 password challenge is only used inside authenticated TLS.

The independent official SoftEther Stable 4.41/9787 server passed native handshake,
tunneled DNS and HTTPS in an isolated container. CI repeats this test using the
pinned archive and setup in ../sstp/reference. No reference binaries or libraries
are included in client builds. DE/US and packaged-device acceptance remain open.
