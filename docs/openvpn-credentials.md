# OpenVPN credentials — first implementation boundary

Backend source version: 0.10.0 → 0.11.0 (new signing capability). Windows and Android
unchanged. Schema remains 0026; no new endpoint, environment variable or migration.
This module is deliberately not wired into the application composition root.
Existing WireGuard issuance, eligibility and cleanup are unchanged.

## Implemented

`backend/src/prettylisavpn/vpn_sessions/certificates.py` defines an injectable
`ClientCertificateIssuer` port and an X.509 signing adapter. The client submits a
signed CSR; its private key never enters the signing interface. Standard X.509
operations use the cryptography dependency, pinned by `backend/uv.lock`.

The adapter checks CA constraints, signing/CRL usage and CA/key correspondence.
Only RSA 2048–4096 (exponent 65537) or EC P-256/P-384 keys are accepted; CSR signatures
must use SHA-256/SHA-384 and verify. CSR size is bounded. Caller-provided subject,
SAN and privilege extensions are discarded. The signed certificate contains only
the server-assigned session UUID as CN, credential UUID as serial, clientAuth and
digitalSignature; it cannot act as a CA or server certificate. Validity ends at the
earliest of authorized access expiry, CA expiry and one hour from issuance.

The CRL signer accepts a complete durable revocation snapshot, validates duplicate
IDs and future revocation times, and produces a numbered signed CRL valid for at
most 15 minutes (also capped at CA expiry). It has no storage or node side effects.
An empty snapshot is meaningful only when the durable ledger has no revocations.

The adapter does not read files, open network connections, log PEM or generate
client private keys. Its result hides certificate PEM from its dataclass repr.
Errors expose closed diagnostic codes. Production signing belongs behind this
port in a trusted signing process; do not load the on-node lab CA into the API.
The existing lab CA may lack the strict KeyUsage extension and is not automatically
accepted as a production authority.

## Required next integration

The subsequent [credential ledger](openvpn-credential-ledger.md) implements the
storage boundary of item 1; it does not yet wire authorization, signer delivery
or node cleanup into public sessions.

1. Persist credential UUID, session/node identity, CSR key fingerprint, exact signed
   certificate and terminal/revocation state. Authorize access before issuance.
   Retries must return the saved certificate; never reuse a credential UUID for
   changed input. The stateless signer cannot enforce issuance idempotency.
2. Implement an authenticated signer adapter and node provisioning/revocation port.
   Apply complete CRLs monotonically and acknowledge successful publication. CRL
   publication does not disconnect an existing OpenVPN connection: explicitly kill
   it and confirm removal before releasing session/quota reservations.
3. Persist lifecycle transitions and durable compensation around ambiguous failures,
   device revocation, expiry, process restarts and concurrent connect/disconnect.
   Add migrations and integration tests as part of that change.
4. Negotiate capabilities and issue TCP candidates only to clients with an actual
   OpenVPN runtime; US TLS_TRANSPORT also requires an independent TLS carrier.
   Both layers must validate server identity/CA. Never distribute lab credentials.
5. Package native runtimes, implement bounded fallback after complete teardown, and
   validate Android cellular and Windows DNS/HTTPS/route/egress behaviour.

## Evidence and deployment status

Tests cover privilege escalation through a CSR, signatures, key strength, CA/key
mismatch, expiry, identity, bounded lifetime and CRL validation. A separate OpenSSL
verification test checks actual client/server purposes and revocation; it skips
only when OpenSSL is absent locally and runs in the Ubuntu backend CI environment.

This source change has not been deployed and does not establish a working product
TCP connection. Live DE handset and DE/US isolated-container tests performed on
2026-10-23 used separate operator test credentials and the previously deployed
services, not this signer. Server certificates were manually renewed through
2026-11-22; automatic renewal and lab client renewal remain separate operations.

The exact reviewed product HEAD, CI run/build identity and results are recorded in
the task PR after the final push; no build/deploy SHA is inferred from a source
version. Development and production were not updated by this feature branch.

Reference: [cryptography X.509 API](https://cryptography.io/en/latest/x509/reference/).
