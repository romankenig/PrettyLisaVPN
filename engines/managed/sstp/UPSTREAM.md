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

The adapter is registered in backend and client source. Its official-peer test
uses SoftEther Stable 4.41 build 9787 in a disposable container without host
networking, TUN or published ports. The official archive SHA-256 is
`c766f92fc664cc95eb4b78d7c041a1e26dbd20d2e714438426c7bc45b146ffd9`.
Reference binaries and their bundled libraries are test-only, never redistributed
with PrettyLisaVPN clients. See reference/ and interop_test.go. TLS/PPP negotiation,
tunneled DNS and HTTPS passed manually; CI repeats the reference test. Actual
DE/US and packaged-device acceptance remain required.
