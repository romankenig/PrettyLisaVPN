# Device scrolling and connection-method confirmation

## Scope and versions

Windows **0.28.0 → 0.28.1**, Android **0.27.1/code 51 → 0.27.2/code 52**.
PATCH: corrections to existing device and connection controls. Backend **0.40.1**,
website **0.5.2** and managed engine **0.6.2** unchanged. No migration, new product
endpoint, payment activation or data collection.

## Behavior and compatibility

- Windows Devices uses the main content viewport as its only scrolling owner.
  The inner list no longer contains wheel propagation while a parent overflows.
  Native acceptance uses actual mouse-wheel input over a five-device fixture,
  checks the last card is reachable and scrolls back up.
- The current device has **sign out on this device**. Confirmation first stops
  the local VPN, then invokes existing `DELETE /devices/{id}` and clears secure
  credentials before opening Login. Cleanup/network failure preserves sign-in
  and displays a retryable error. An already-invalid session clears credentials.
  Repeated clicks are fenced; account changes cannot revoke or clear a new session.
  Other-device revocation retains its existing behavior. The API already supports
  current-device revocation and durable peer cleanup; no backend work is pending.
- On both clients, the small translucent refresh icon beside the current protocol
  opens a confirmation explaining forgotten learned methods, brief disconnection
  and retained country/services. Cancel/Escape/Android Back has no connection effect.
  Confirm invokes the existing reset executor, retaining cleanup, method ordering,
  allowed-method settings, country and traffic rules. No control without a method.
- Windows uses a native modal dialog with an accessible label/description, initial
  focus on Cancel and focus restoration. Android uses the existing Material dialog
  style and an icon with an accessible label. All six locales are updated.

## Verification and release handoff

Source changes, native capture scenarios and tests are part of the same commit.
Windows tests cover confirmation/cancellation, duplicate submissions, cleanup and
API failures, credential deletion and Login. Android instrumentation checks no
reset on open/cancel, confirmation, and dismissal when the connection disappears.
The native Windows fixture's extra three devices and self-revoke mode are explicit
loopback-only overlays; original backend-recorded device responses stay unchanged.
These tests do not claim a new live VPN or production-account revocation exercise.

The owner authorized merge and Windows/Android publication after successful checks
and conflict review. Exact final source HEAD, temporary PR merge SHA, all workflow
runs/jobs/checks, native screenshots and build artifacts will be recorded in the PR.
After merge, verify automatic develop publication using the merge build identity
and compare permanent-download binary/source/license bytes with that CI artifact.
No backend deployment is required. Earlier artifacts are not evidence for this task.
