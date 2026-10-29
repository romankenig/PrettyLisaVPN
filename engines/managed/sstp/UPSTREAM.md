# SSTP wire and PPP codecs

MIT portions from https://github.com/wanan9999/veepin at
`6e8d2aca383ee2e74fb7e1ee3f01adfc1d1d2596`, copyright 2026 Remy.
See LICENSE-UPSTREAM and upstream-files.json for original file hashes.
PPP/MS-CHAPv2 and SSTP framing/crypto-binding codecs and their tests are retained;
imports use this private package, with TrimToIP extracted from dataplane/shape.go.
The original system TUN, routes, registry, logging and server are not included.

PrettyLisaVPN owns strict TLS verification, packet authorization, nonce checks,
bounded resource lifetime and its in-memory IP stack. In particular data must
never be forwarded before PPP authentication, crypto binding and IPCP complete.
Legacy PPP algorithms operate only inside authenticated TLS.

This adapter is under implementation and not yet admitted by either client or
backend. Official-peer interoperability and real-server acceptance are required.
