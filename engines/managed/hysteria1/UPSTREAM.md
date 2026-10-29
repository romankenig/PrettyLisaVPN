# Hysteria 1 compatibility

The wire format is Hysteria protocol version 3, as published in
`apernet/hysteria` v1.3.5, commit `57c5164854d6cfe00bead730cce731da2babe406`
(MIT). This is distinct from Hysteria 2. No GPL TUN component is included.

The adapter uses the current pinned QUIC implementation already used by the
managed runtime; it does not require the obsolete Go 1.20-only QUIC runtime.
Framing has explicit allocation limits, fragment lifetime and ownership bounds.
Authentication and certificate validation must complete before proxying traffic.
No packet, destination, DNS-query or credential logging is provided.
