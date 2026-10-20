# PrettyLisaVPN для Android

Android **0.3.0 / versionCode 3** — экраны на изолированном тестовом источнике.
Эталон Windows **0.12.0**, develop `41feac6`; backend0.10.0/schema0026 unchanged.
Версии платформ независимы. [Карта экранов и ограничения](../../docs/android-fixture-screens.md).

Debug стартует с синтетическим Premium-аккаунтом. Через Settings → Sign out можно
проверить вход: любой корректный email, test code **123456**; **000000** показывает
expired. Письмо не отправляется. About → Test scenarios переключает Free/Expired/
Platinum/Empty/Device limit/Stale/Offline/Fail next/Payment pending. Это не development API.

Постоянный **TEST DATA · NO VPN TUNNEL**; кнопка **simulate connection** не создаёт
VPN, не меняет IP/маршруты и не защищает трафик. Платежи, привязка карты, отправка
поддержки и прикрепление скриншотов исключительно симулируются, без сети/личных файлов.
Source из src/debug не включается в release: там unavailable screen, пока не создан
реальный адаптер. В main manifest нет network/VPN permissions. После process death
fixtures сбрасываются; Activity recreation сохраняет навигацию/черновик/операцию,
но OTP не сохраняется. English base; шесть языков — отдельная задача 0.4.0.

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
на API26/35/36: 3 navigation + 8 flow tests + 3 design tests ×6конфигураций =
29 instrumented tests/API. Сохраняются native PNG baseline/flows/design, JSON
viewport/fontScale/IME/source и runtime/ANR diagnostics. Source SHA, PR merge SHA,
run/attempt и APK SHA-256 — в build-identity.json; после завершения — в task PR.
Артефакты APK/native evidence хранятся14дней. Проверки не доказывают настоящий VPN.

Прежний [дизайн0.2.0](../../docs/android-design.md), [архитектура](../../docs/android-architecture.md),
[план](../../docs/android-porting-plan.md), [требования локализации](../../docs/android-localization.md).
Rubik/OFL: [лицензия](app/src/main/assets/licenses/Rubik-OFL.txt).
Release signing/store publication/auth/API/VPN/SAF/TalkBack и device E2E — будущие задачи.
