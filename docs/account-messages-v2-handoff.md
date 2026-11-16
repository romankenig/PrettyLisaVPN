# Account message popup v2 — handoff

Source base: `2ded0291` (`origin/develop`, including app-version analytics).
Independent task versions: backend 0.48.0 → 0.49.0; Windows 0.29.1 → 0.30.0; Android 0.28.2/code57 →
0.29.0/code58; iOS 0.4.1 → 0.5.0; macOS 0.3.1 → 0.4.0. Other components unchanged.
No database migration: existing immutable JSONB publications hold the v2 fields.

Implementation and operator examples: [account-messages.md](account-messages.md).
v1 remains readable/writable; new clients negotiate v2 and fall back on old-server
422 only. Required publications are never silently downgraded to dismissible v1.
Operators publish through the existing server-only CLI; no public write API added.
HTTPS opening is separate from billing URL validation and never attaches credentials.

Local validation: backend contract and PostgreSQL integration tests, Ruff and mypy;
Windows ESLint, TypeScript and Vitest; Apple packaging/locale structural checker.
The broad backend suite on this Windows host reached 793 passing tests but its
Linux shell cases and 40 tmp_path fixtures failed on host tooling/permissions;
the full Linux workflow is required before acceptance. Message-specific tests
passed (43 unit, 15 PostgreSQL integration at the initial validation).
After incorporating app-version analytics from develop, the combined local
message/analytics suites passed 59 unit and 17 PostgreSQL integration tests;
Ruff and mypy also passed. The Android acceptance runner now expects all 27
account-screen tests, including the new mandatory-message scenario.
Native screenshot review also applies the shared action/error palette directly
inside the Apple sheet: presented sheets do not inherit the root view's tint.
Full native Windows/Android/Apple builds and screenshots use this task's Actions
runs. The local Windows native test initially could not compile because the
workspace lacks the generated managed-engine embedding; no historical executable
or placeholder engine is substituted. CI builds the engine from the checked-out source.

The task PR records the **final verified product HEAD**, each actual checkout/build
SHA (PR merge SHA may differ), run ID/attempt, every workflow/job conclusion and
artifact names/links. These are live validation evidence, not release labels.
Native UI artifacts cover empty, optional and mandatory popup states, dismiss/back
handling and server withdrawal; API integration tests use real disposable PostgreSQL
and authenticated account/device sessions. Fixture screenshots do not prove a live
production account received a publication.

Backend follow-up: deploy compatible backend, distribute each new client, then
publish a targeted message to an approved test account before wider rollout.
No merge, release tag, production deploy or actual user message is authorized by
this source change. Existing development deployment remains branch-dependent.
Known scope: UI blocking after delivery, no server-side VPN version enforcement,
no message push to clients whose successful startup list contained no required notice.
