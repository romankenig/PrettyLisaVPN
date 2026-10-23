# OpenVPN credential ledger

Backend 0.11.0 → 0.12.0, migration `0027_vpn_credentials`. Clients unchanged.
This is the persistence step after [the signing boundary](openvpn-credentials.md).
It does not expose OpenVPN sessions or enable TCP fallback in the clients.

## Durable boundary

`vpn_sessions/credentials.py` implements a transactional SQLAlchemy repository.
`vpn_credentials` binds a server-allocated credential UUID to an existing session,
the session's node, an authority SHA-256 fingerprint, a signing-request fingerprint
and an immutable expiry. The future application service must fingerprint the
canonical, validated signing request and pin the trusted CA before reservation.

Reservations use a PostgreSQL unique key and ON CONFLICT, then lock the record.
Identical retries recover the original record; changed session, authority, request
or expiry cannot reuse that identity. Issuance stores exact already-verified
certificate bytes and its first completion time. It never overwrites a different
result. PEM is excluded from snapshot repr; client private keys and CSR content
are not stored. The database connection already hides SQL parameters.

The repository intentionally does not parse PEM, perform authorization or contact
the signer. Those are application/provider responsibilities. Its methods require
the caller to commit the transaction: reserve before contacting the signer, save
the result before replying to the client. A signer must use the same credential
UUID for retry after an ambiguous outcome. The local stateless signer alone is
not an idempotent remote issuance service.

Revocation intent is durable even if a signing result is unknown. Once revoked,
the record cannot accept late issuance. Expiry does not imply that an active
connection disappeared. Recovery queries return pending revocations; confirmation
requires the correct session/node/authority and an existing intent. The future
authenticated node adapter must validate acknowledgement of BOTH CRL application
and active-client termination before calling `confirm_removed`.

CRL snapshots are scoped to node and CA and retain confirmed revocations. They
are not a publication queue or sequence-number allocator: durable monotonic CRL
versions and worker coordination remain required before node integration.

Session/node foreign keys use RESTRICT, so account/session deletion cannot silently
erase a revocation record. Future account deletion must first revoke credentials
and apply an explicit retention/purge policy after they can no longer authenticate.
There is deliberately no public purge method or certificate body in diagnostics.

## Scope and next integration

This table has no backfill; existing WireGuard sessions create no credential rows.
The session model is still WireGuard-specific. Do not manufacture a WireGuard peer
just to issue OpenVPN: introduce negotiated transport-specific sessions together
with their authorization, address allocation, cleanup and quota integration.

Next: authenticated issuance orchestration with durable signer idempotency, worker
recovery, monotonic CRL publication and node termination acknowledgements. Then add
the versioned API and client OpenVPN/TLS runtimes. Do not activate public issuance
before all these lifecycle paths have working adapters and acceptance coverage.

## Validation and release

Unit tests reject malformed identities/fingerprints/times before storage access.
Real PostgreSQL tests exercise concurrent retry and conflicting results, reconnect,
rollback, late signing completion, expiry, scoped acknowledgement, retained CRL
entries and database constraints. CI also checks Alembic against ORM metadata,
the existing backend tests and the built container.

The task PR records the exact source HEAD and CI/build SHA after the final push.
This feature branch is not a deployment. The prior signing module and Android
WireGuard PRs were merged separately; their builds are not evidence for this ledger.
