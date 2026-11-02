# Windows installer and connection service

Windows **0.22.0 → 0.23.0** adds machine-wide installation and a privileged VPN
service. Android remains **0.19.0**, backend **0.27.0**, managed engines **0.5.1**;
no API or database changes. This is a MINOR packaging/runtime feature.

## Installation and migration

Download the current Windows installer from the dashboard, close the old
standalone app, run setup and approve the Windows administrator prompt once.
Setup installs in Program Files/PrettyLisaVPN, adds shortcuts/uninstaller and
starts PrettyLisaVPNService automatically. Account credentials and preferences
retain their existing Tauri identifier and user storage. Setup stops/removes only
the old PrettyLisaVPN WireGuard tunnel, not other VPN products or their drivers.

**BREAKING (pre-1.0 distribution):** the new executable needs the installed
service; copying it out of its installation directory does not produce a portable
VPN client. The public `/dashboard/downloads/windows.exe` URL now serves the NSIS
setup executable; CI artifacts call it `PrettyLisaVPN-Setup.exe`. Versions before
0.23.0 retain the legacy publication contract. Downgrade requires uninstalling
0.23.0 without clearing account data, then using the previous immutable binary;
legacy WireGuard again requires its external official client and UAC approval.

Setup/repair/update/uninstall may request administrator approval. Connecting,
disconnecting and protocol fallback do not invoke UAC. The WebView remains an
ordinary user process. All WireGuard modes, including full traffic, now use the
existing managed WireGuard core; keys are generated natively using OS randomness
and X25519. Private keys never enter the renderer or a configuration file.

Android already calls `VpnService.prepare()` and opens the system VPN consent
only when it returns an intent. Android's first consent (or consent after another
VPN revokes it) cannot be bypassed. The existing optional notification request is
remembered and does not repeat during fallback. No Android behavior/version change
is necessary for this task.

## Privilege boundary and cleanup

- A LocalSystem service accepts only local named-pipe clients. The pipe is unique,
  rejects remote connections, denies network logons and does not grant interactive
  users permission to create pipe instances.
- Before sending credentials the client compares the pipe server PID with SCM.
  Client security-QOS identification prevents a pipe impostor impersonating it.
  The service checks the actual caller PID and protected installed executable;
  an identical executable copied elsewhere is rejected.
- Only bounded start/profile, stop and status envelopes are accepted. The existing
  core validates all profile fields; no executable path, script or arbitrary
  engine config is accepted. There is one client owner at a time.
- Engine extraction uses a new administrator-only System32 directory. A
  kill-on-close job owns the child; caller exit, broken IPC and service shutdown
  trigger cleanup. The next owner is accepted only after child termination.
  Ambiguous stop remains a cleanup failure until a new authenticated session
  confirms DOWN or SCM confirms the service is stopped.
- Installer hooks enforce a fixed protected path, reject reparse points and
  untrusted ownership/write access, and stop services before replacing files.
  Uninstall preserves user data unless the user explicitly requests its removal.
- Source bundles retain corresponding engine sources and notices. New native
  cryptography dependencies use permissive licenses, included in setup resources.
  No sing-box or new GPL engine is introduced.

## Validation and delivery evidence

Local validation: client lint/typecheck, 324 frontend tests, 21 Rust tests,
Rust formatting/Clippy and publisher validation tests. Publisher Linux-only
flock/symlink tests and all platform workflows must also pass in CI.

`test-installer.ps1` runs only on isolated Windows CI: clean install, service
identity/current-binary hash, standard-account IPC without elevation, uninstalled
client rejection, repair, uninstall and absence of orphan engine processes.
Opt-in live acceptance uses the installed current build, real backend sessions,
tunnel-bound Internet verification and cleanup. Windows UI review supplies native
screenshots of the current checkout. These tests must not replace or disable the
owner's active VPN on their PC.

At source preparation, remote CI, live acceptance and dashboard publication are
pending. The task PR records the final checked product HEAD, actual build SHA,
run/attempt, artifacts and publication result after checks finish. Prior binaries
are not evidence for this change. There is no required backend migration/deploy;
the existing development workflows may rebuild unchanged component versions.

References: [Tauri NSIS hooks](https://v2.tauri.app/distribute/windows-installer/),
[Android VPN consent](https://developer.android.com/develop/connectivity/vpn).
