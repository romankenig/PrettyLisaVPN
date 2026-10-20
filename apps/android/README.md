# PrettyLisaVPN для Android

Android **0.4.0 / versionCode 4** — auth/session API существующего development-backend.
Windows 0.12.0 и backend 0.10.0/schema0026 unchanged. Подробности:
[auth/session, безопасность и приёмка](../../docs/android-auth-session.md).

Обычный debug/release запускает email OTP, восстанавливает защищённую сессию,
показывает профиль из /me и позволяет выйти. Continue/Resend отправляет настоящее
письмо через development API; автоматического запроса нет. VPN, платежи, поддержка
и управление устройствами в этом режиме недоступны. Реального туннеля нет.

Прежние [тестовые экраны](../../docs/android-fixture-screens.md) остались в src/debug
и включаются instrumentation runner только для автоматической проверки UI. Их данные
не смешиваются с реальным аккаунтом. Release не содержит FixtureSource. INTERNET
разрешён для HTTPS API; cleartext/backup запрещены. Шесть языков — следующая задача.

## Сборка и CI

JDK17, Android SDK36, minSdk26, targetSdk36, Gradle8.13/AGP8.11.1/Kotlin2.1.21.
Pinned зависимости — [libs.versions.toml](gradle/libs.versions.toml).

```bash
cd apps/android
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest :app:lintDebug :app:assembleRelease :app:lintRelease
python3 scripts/check-source-isolation.py
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -W -n com.prettylisavpn.android.dev/com.prettylisavpn.android.MainActivity
```

[Android debug workflow](../../.github/workflows/android.yml) собирает текущий SHA,
проверяет debug/release isolation, JVM tests и lint. Тот же debug APK устанавливается
на API26/35/36: 3 navigation + 9 flow tests + 3 design tests ×6конфигураций =
30 instrumented tests/API. Сохраняются native PNG baseline/flows/design, JSON
viewport/fontScale/IME/source и runtime/ANR diagnostics. Source SHA, PR merge SHA,
run/attempt и APK SHA-256 — в build-identity.json; после завершения — в task PR.
Артефакты APK/native evidence хранятся14дней. Проверки не доказывают настоящий VPN.

Прежний [дизайн0.2.0](../../docs/android-design.md), [архитектура](../../docs/android-architecture.md),
[план](../../docs/android-porting-plan.md), [требования локализации](../../docs/android-localization.md).
Rubik/OFL: [лицензия](app/src/main/assets/licenses/Rubik-OFL.txt).
Release signing/store publication/auth/API/VPN/SAF/TalkBack и device E2E — будущие задачи.
