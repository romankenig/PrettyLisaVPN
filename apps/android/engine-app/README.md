# PrettyLisaVPN Engines for Android (in development)

Separate companion APK, version 0.1.0. Its VpnService owns Android VPN consent
and one Go runtime. The main client must have the same signing certificate.
Every Binder call also checks its exact package and UID. Profiles and secrets
never enter intents, preferences, files, notifications or logs.

This adapter is MIT (see LICENSE); Xray is MPL-2.0. No sing-box/GPL library is
included. Release packaging must preserve dependency notices and supply the
corresponding MPL source. The main `:app` module does not link this native AAR.

CI builds the AAR from `engines/managed/mobile` using pinned Go/gomobile/NDK
versions. It is not checked in. Main-client IPC integration and real device
acceptance are pending; this APK is not yet an enabled connection method.

Protocol v1: signature-protected `ConsentActivity` (start for result), then
bind `ControlService` and call `IEngineControl`. The owner Binder stays alive.
Native cleanup failure or a stuck operation terminates the companion process,
so Android closes TUN descriptors. Losing the underlying network stops the
session. RUNNING only describes the engine; the client must verify DNS and
HTTPS using the actual VPN Network before publishing Connected.
