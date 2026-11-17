# Account message popup v2 — handoff

Source base: `d67cde11` (`origin/develop`, including app-version analytics and
pending-device access and connection-outcome reporting). Independent task versions:
backend 0.50.0 → 0.51.0;
Windows 0.30.0 → 0.31.0; Android 0.29.0/code58 → 0.30.0/code59;
iOS 0.5.0 → 0.6.0; macOS 0.4.0 → 0.5.0. Other components unchanged.
No database migration: existing immutable JSONB publications hold the v2 fields.

Implementation and operator examples: [account-messages.md](account-messages.md).
v1 remains readable/writable; new clients negotiate v2 and fall back on old-server
422 only. Required publications are never silently downgraded to dismissible v1.
Operators publish through the existing server-only CLI; no public write API added.
The operator explicitly selects REQUIRE_LINK, NEXT_VISIT or ONCE. Link-gated
closing repeats on every launch, as requested; only ONCE persists account-wide
ACK. Every v2 revision reappears, even with the legacy redisplay flag false.
HTTPS opening is separate from billing URL validation and never attaches credentials.

Local validation: backend contract and PostgreSQL integration tests, Ruff and mypy;
Windows ESLint, TypeScript and Vitest; Apple packaging/locale structural checker.
The broad backend suite on this Windows host reached 793 passing tests but its
Linux shell cases and 40 tmp_path fixtures failed on host tooling/permissions;
the full Linux workflow is required before acceptance. Message-specific tests
passed (43 unit, 15 PostgreSQL integration at the initial validation).
After incorporating app-version analytics from develop, the combined local
message/analytics suites passed 59 unit and 17 PostgreSQL integration tests;
Ruff and mypy also passed. The Android acceptance runner now expects all 28
account-screen tests, including the new mandatory-message scenario.
Native screenshot review also applies the shared action/error palette directly
inside the Apple sheet: presented sheets do not inherit the root view's tint.
The device-limit cabinet from develop retains its private-API boundary. Message
loading/presentation resumes after activation; Apple reacts to that profile change
without waiting for another OTP. Both native cabinet and popup tests are retained.
After merging device-limit access: 73 backend unit tests and 28 PostgreSQL
integration tests passed; Alembic upgrade/check, Ruff and mypy passed. Windows
passed all 401 Vitest tests, ESLint, TypeScript and Vite build. Apple structural
checks and five packaging unit tests passed; native evidence comes from CI.
Full native Windows/Android/Apple builds and screenshots use this task's Actions
runs. The local Windows native test initially could not compile because the
workspace lacks the generated managed-engine embedding; no historical executable
or placeholder engine is substituted. CI builds the engine from the checked-out source.

The task PR records the **final verified product HEAD**, each actual checkout/build
SHA (PR merge SHA may differ), run ID/attempt, every workflow/job conclusion and
artifact names/links. These are live validation evidence, not release labels.
Native UI artifacts cover empty and all three popup modes, link unlocking,
dismiss/back handling, next-launch repeat and server withdrawal; API integration tests use real disposable PostgreSQL
and authenticated account/device sessions. Fixture screenshots do not prove a live
production account received a publication.

Backend follow-up: deploy compatible backend, distribute each new client, then
publish a targeted message to an approved test account before wider rollout.
No merge, release tag, production deploy or actual user message is authorized by
this source change. Existing development deployment remains branch-dependent.
Known scope: UI blocking after delivery, no server-side VPN version enforcement,
no message push to clients whose successful startup list contained no required notice.

Final three-mode clarification is part of the same version bump. Local checks and
all native workflows are rerun after this change; older screenshots do not verify
these final semantics. Final run/attempt, checkout SHA, artifacts and results are
recorded in PR #96 without another documentation-only push.

After the three-mode change, local validation passed 47 backend contract tests,
16 real-PostgreSQL message integration tests, Alembic upgrade/check, Ruff and mypy;
408 Windows tests, ESLint, TypeScript and production Vite build; Apple project
checks and five packaging tests; Android six-language catalog checks.

Native acceptance follow-up fixes duplicate IDs in the Apple example envelope,
validates that entire envelope in Swift core tests, covers all modes in the
separate macOS UI suite, and resets the Windows repeat fixture before unrelated
relaunch/language tests. Concurrent develop reporting changes are merged intact;
only the popup backend version advances to 0.51.0. Final evidence is in PR #96.
