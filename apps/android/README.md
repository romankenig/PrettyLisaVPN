# PrettyLisaVPN Android

Android 0.11.0 (versionCode 19) is a single APK with no VPN engine, Binder companion,
VpnService, native tunnel library, VPN consent or foreground-service permission.
Connect invokes 14 adapters in order; each currently delays three seconds and fails.
Cancel interrupts the active delay. All failures end disconnected after about 42 seconds.

Build with JDK 17 and Android SDK 36:

```sh
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug :app:assembleRelease :app:lintRelease
python3 scripts/check-localization.py
python3 scripts/check-source-isolation.py
python3 scripts/check-vpn-packaging.py
```

No Go, NDK, AAR or engine source build is needed. CI checks the installed APK on
API 26/35/36, the actual 42-second sequence, cancellation, account flows and screenshots.
The debug signature and application ID are unchanged; install over the existing app
to retain the login. The old separate Engines APK can be uninstalled.

See [adapter contract, scope and rollback](../../docs/vpn-placeholder-reset.md).
