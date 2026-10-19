# PrettyLisaVPN для Android

Android **0.1.0**, versionCode **1** — первая самостоятельная версия клиента.
Текущий Windows-эталон — **0.12.0** (develop `78f5999`, PR #21).
Backend **0.10.0**, schema **0026** не меняются; версии платформ независимы.

Реализован нативный Kotlin/Jetpack Compose каркас: одна Activity, три вкладки
«главная / настройки / о приложении», системный Back и восстановление выбранной
вкладки после пересоздания Activity. Фирменные цвета, Rubik/OFL и контуры логотипа
перенесены из Windows; учитываются системные insets и прокрутка небольших экранов.
Это стартовый APK: API/auth, VPN runtime, платежи и поддержка ещё не подключены.
Кнопка подключения недоступна; приложение не запрашивает VPN-разрешение и не
отправляет сетевые запросы. Backend-версия в UI — «не подключён».

## Что изменилось в требованиях после Windows 0.12.0

Каркас 0.1.0 остаётся без выбора языка: его `values/strings.xml` содержит русские
тексты. Шесть языков, English default и RU auto-origin ещё **не реализованы**
на Android. Следующий UI-этап должен заложить resources/locale policy до расширения
экранов: [требования локализации](../../docs/android-localization.md),
[обновлённый порядок и промпт](../../docs/android-porting-plan.md).
Текущее обновление — документация и синхронизация develop; versionName/code,
Kotlin, ресурсы, Gradle и API/VPN поведение Android не изменяются.

## Сборка и запуск

Требуются JDK **17**, Android SDK platform **36** и лицензии Android SDK.
Открыть эту директорию в Android Studio либо указать `ANDROID_HOME` / `sdk.dir`
в локальном `local.properties` (не коммитить).

```bash
cd apps/android
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -W -n com.prettylisavpn.android.dev/com.prettylisavpn.android.MainActivity
./gradlew :app:connectedDebugAndroidTest
```

Windows: те же Gradle tasks через `gradlew.bat`. Wrapper JAR и distribution checksum
зафиксированы для Gradle **8.13**; AGP **8.11.1**, Kotlin/Compose compiler **2.1.21**,
Compose BOM **2025.05.01**, Navigation **2.9.0**. Версии — в
[libs.versions.toml](gradle/libs.versions.toml). minSdk **26**, compile/targetSdk **36**.
Основной источник Android-версии — [app/build.gradle.kts](app/build.gradle.kts):
`versionName=0.1.0`, `versionCode=1`. Windows package.json не используется.
Debug applicationId — `com.prettylisavpn.android.dev`; подпись локальным debug key.
Release signing, Play Store и auto-update в этот этап не входят.

## CI и происхождение APK

[Android debug workflow](../../.github/workflows/android.yml) запускается при
push/PR с изменением Android и вручную. Сначала собирает APK/тестовый APK текущего
checkout и запускает lint (API/resources/security warnings — errors; онлайн-советы
об обновлении pinned toolchain/dependencies остаются informational); затем устанавливает **тот же APK** на x86_64 эмуляторы
Android **8.0 (API 26)**, **15 (API 35)** и **16 (API 36)**. Три instrumented-теста проверяют вкладки,
недоступность подключения, повторные переходы/Back и Activity recreation.
После тестов выполняется отдельный cold launcher start с проверкой процесса,
resumed Activity и отсутствия AndroidRuntime crash. Нативные PNG сохраняются
с каждого экрана и после запуска.

Артефакт `PrettyLisaVPN-android-debug-<sha>-<run>-<attempt>` содержит `app-debug.apk`
и `build-identity.json`: полный source SHA, PR head SHA, версия/code, package,
run/attempt и SHA-256 APK. В PR-событии source SHA — временный merge commit,
в push — точный head ветки. `BuildConfig.SOURCE_SHA` также встроен в APK и показан
в «о приложении». Локальная сборка без `-PsourceSha=<40 hex>` помечена `local`.
Скриншоты/запуск — отдельные `android-emulator-api26/35/36-...` артефакты; lint —
`android-build-reports-...`. Итоговые run/attempt, проверенный HEAD и ссылки
публикуются в PR после завершения CI, чтобы не создавать цикл новых docs-сборок.

Фактические результаты эмуляторных проверок и визуального просмотра PNG — в PR.
Описанные выше проверки считаются пройденными только для успешного CI того же SHA.
В текущей cloud workspace SDK отсутствует и локальный сетевой proxy недоступен:
локально выполняются проверки исходников/скриптов, Android build — на Actions.

## Продолжение переноса

- [Архитектура, экраны/API, дизайн и native-зависимости](../../docs/android-architecture.md).
- [Последовательный план](../../docs/android-porting-plan.md),
  [статус проекта](../../docs/project-status.md), [версии](../../docs/versioning.md).
- Первый будущий VPN runtime — WireGuard IPv4 full tunnel. Ни один VPN-профиль
  сейчас не исполняется; OpenVPN/MASQUE/legacy wrappers остаются disabled.
- Backend поддерживает ANDROID в auth/messages, но support diagnostics принимает
  только WINDOWS: будущий Android-адаптер отправляет `diagnostics=null`.
- Реальные платежи отключены; ручной OTP остаётся на паузе владельца.
