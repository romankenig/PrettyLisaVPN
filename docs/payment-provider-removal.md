# Discontinued payment provider removal — 2026-11-03

The owner abandoned 1Plat and requested removal of its integration and materials.
Backend 0.30.0 → 0.31.0 (MINOR, explicit removal of an HTTP endpoint before 1.0).
Windows 0.25.0 and Android 0.21.0 are unchanged: neither contains provider-specific
code. Source baseline is 91a3c45f3bdde9e99f5b522ddb3b583b86719138 in PR #49.

## Scope and compatibility

- Remove the unused callback from FastAPI and public reverse-proxy routing.
  GET and POST now return 404; the endpoint is absent from OpenAPI.
- Remove the merchant TXT route, read-only mount, deploy/CI variable and examples.
- Remove local provider credentials, downloaded API bundles and diagnostic helpers;
  remove the verification token and its staging copies from the main server.
  Do not print credentials or commit them. No provider account deletion or billing
  operation is needed: no invoice, charge or mandate was created.
- Preserve static payment success/failure and support pages, generic billing
  ports, existing payment-method management UI and all paid entitlements. Payment
  operations stay disabled. No schema migration or financial-data deletion.
- Replace provider-specific setup instructions with the current generic contract.
  Git history and release history remain available for audit, not active integration.

## Checks and rollout

Tests cover 404 for former callback GET/POST, no OpenAPI exposure, ignored forged
claims, preserved return/support pages and Caddy's closed public-host boundary.
Run backend format/lint/types/unit/integration/image/deployment checks and inspect
all latest-HEAD Actions runs/jobs/check suites/statuses before claiming completion.
No client UI was changed, so previous client binaries remain valid.

On the main server, build the exact committed source with a unique manual runtime
identity, retain the previous application image/environment for recovery, deploy
the new backend/Caddy configuration and verify health, readiness, exact version,
payment/support HTTP 200 and both former URLs HTTP 404 on public/API hosts. Delete
only identified provider files; do not delete unrelated secrets or old releases.
If recovery is needed, restore application availability while retaining removal of
the verification file; an old runtime may contain the disabled callback until a
forward fix. Do not reactivate the abandoned integration or downgrade the database.

Final product SHA, manual build SHA/run/attempt/image, deleted-file counts, live
HTTP evidence and all CI links belong to PR #49; this document is not deployment
proof. No merge, stable client publication or real payment test is part of this task.
