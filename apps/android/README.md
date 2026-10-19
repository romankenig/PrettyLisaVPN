# PrettyLisaVPN для Android

Текущий этап — **проектирование**, 2026-10-19. Kotlin/Compose-проект, Gradle,
APK и VPN runtime ещё не созданы. Эта документация не объявляет Android готовым
или проверенным. Backend и Windows не меняются; version unchanged.

Основа аудита: Windows **0.11.1**, backend **0.10.0**, schema **0026**,
`develop` **69ab8d1d3d3c5680fc72bb23980776242606a104**.

- [Архитектура, экраны/API, дизайн и native-зависимости](../../docs/android-architecture.md).
- [Последовательный план переноса и промпты](../../docs/android-porting-plan.md).
- [Общий статус проекта](../../docs/project-status.md),
  [правила версий](../../docs/versioning.md), [визуальный стиль](../../docs/design-system.md).

Выбран отдельный Kotlin + Jetpack Compose клиент, без запуска React/Tauri/Win32.
Предлагаются minSdk26 и первая версия Android 0.1.0 при реализации каркаса;
точные SDK/toolchain/dependency versions фиксируются в следующем техническом этапе.
Первые APK должны сохранять logo/Rubik/палитру Windows с мобильной компоновкой,
insets/IME, системным Back и доступными размерами элементов.

Первый VPN-этап проектируется для WireGuard IPv4 full tunnel через Android runtime.
Объявленные в каталоге OpenVPN/MASQUE и Windows legacy wrappers не становятся
автоматически поддерживаемыми Android. До runtime/transport acceptance они disabled.
`NATIVE` не подменяется direct UDP, explicit empty candidates не заменяются legacy.

Существующий backend допускает ANDROID для auth/messages, но support diagnostics
принимает только WINDOWS. Android-обращения могут отправляться с `diagnostics=null`;
подменять платформу или менять backend для обхода ограничения нельзя.

Реальные платежи отключены, ручной OTP остаётся на паузе владельца. Никаких
реальных писем, списаний, привязок или изменений VPN-узлов этот этап не выполняет.
