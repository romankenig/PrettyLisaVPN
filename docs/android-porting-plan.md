# Android: последовательный план переноса

Основа — [архитектура Kotlin/Compose](android-architecture.md), аудит Windows
0.11.1 и backend 0.10.0 на commit `69ab8d1d3d3c5680fc72bb23980776242606a104`.
Это roadmap. **Реализован каркас этапа 1: Android 0.1.0**, базовые три вкладки
и тема из этапа 2. [Инструкции/CI и ограничения](../apps/android/README.md).
Приёмка APK/эмуляторов и точные SHA/run/attempt фиксируются в task PR.
Backend 0.10.0 / Windows 0.11.1 / schema 0026 unchanged; API/VPN пока отсутствуют.

## Порядок и результаты этапов

| Этап | Что делаем и зачем | Проверяемый результат / зависимость |
| --- | --- | --- |
| 0. Аудит и архитектура — этот документ | Карты экранов/API/дизайна/native, матрица профилей, совместимость frozen backend | Исходники и точный SHA зафиксированы; нет обещаний Android runtime/E2E |
| 1. Каркас и первый APK | Kotlin/Compose project, Gradle/toolchain, flavors, CI, простой стартовый экран | Устанавливаемый debug APK текущего HEAD, launch на эмуляторе, независимая Android 0.1.0; не UI screenshot из Windows |
| 2. Тема и мобильная навигация | Rubik/логотип/токены, компоненты, 3 вкладки, auth graph, адаптация insets/IME/Back | Native screenshots 320/360/412dp и landscape/fontScale; бренд и регистр PrettyLisaVPN сохранены |
| 3. Все экраны на fixtures | Auth/Home/countries/settings/devices/subscription/about/support/messages, loading/error/stale/disabled | Просматриваемый APK без сервера, Compose tests переходов; fake VPN явно обозначен и исключён из release |
| 4. Auth/session | Существующие OTP/refresh/me/logout, ANDROID platform, installation UUID, Keystore vault | Contract/MockWebServer tests, single-flight rotation, expiry/revocation/offline/process restart; настоящее письмо не запрашивается автоматически |
| 5. Остальные API | Устройства, сообщения JSON v1, read-only billing, поддержка без diagnostics, public location | Последствия действий отражаются на Home; optional APIs не блокируют вход; server constraints не обходятся |
| 6. VPN runtime spike и базовый WireGuard | Зафиксировать published AAR и service ownership/FGS; реализовать VpnProtocol adapter, consent, local start/stop/status | GoBackend интеграция проверена на целевых SDK/ABI, один TUN, реальная верификация; backend не меняется; runtime включается только при совместимом config |
| 7. Product VPN lifecycle | Create/current/terminate, first candidate, cleanup, reconnect/restart, quota и truthful states | Нет двойной сессии, false Connected или потерянного cleanup; проверки VPN DNS/route/egress и IPv6 policy обязательны |
| 8. Нужные дополнительные transport-адаптеры | Только отдельным этапом после выбора фактически нужного режима, без скрытой подмены direct | Wrapper/legacy modes включаются по wire/MTU/lifecycle tests и проверенной паре client/node; OpenVPN/MASQUE остаются disabled при frozen backend |
| 9. Реальная сквозная приёмка | Android handset + development API, DNS/traffic/egress/handover/revoke/expiry/stop | Доказательства SHA/APK/device/OS/time/actual network; ручной OTP только после готовности владельца; остающиеся ограничения явно перечислены |
| 10. Тестовое распространение | Release signing, APK/AAB, update test, install instructions, current artifact identity | Подписанный проверенный артефакт и успешное обновление с сохранением допустимых настроек/сессии; store publication отдельным поручением |

Этап 8 не означает обязательное внедрение всех экспериментальных режимов до первого
Android MVP. Если доступные узлы требуют неподдерживаемый режим, это реальный блокер
VPN-приёмки: нельзя выдать direct UDP за эквивалент или изменить backend/узлы без
отдельной задачи. Ранние APK этапов 1–5 всё равно полезны для проверки UI и API.

## Общие правила реализации

- Не менять backend/Windows/узлы, не активировать реальный provider и не выполнять
  списания/привязки. Обнаруженное расширение контракта записать отдельной задачей.
- Android minSdk26 закреплён в каркасе 0.1.0; toolchain и dependency versions
  выбираются/фиксируются при bootstrap. Не использовать динамические Maven versions.
  Signing credentials не добавлять в git, CI log или APK; release upload key отдельно.
- Версия Android независима: первая реализация 0.1.0, далее bump один раз на
  самостоятельную продуктовую задачу по [versioning.md](versioning.md).
  Docs-only этап не создаёт versionCode, APK, новую версию Windows или backend.
- Каждый этап — ограниченный diff, необходимые проверки и отдельный PR. Merge,
  публикация и rollout — по поручению владельца. Не исправлять новый UI проверками
  старого фиксированного APK; артефакт обязан соответствовать текущему SHA.
- MockWebServer/fixture runtime не смешивать с development API и реальным tunnel.
  Kotlin contract tests не заменяют handset routing, DNS и background acceptance.
- Миграция Windows support diagnostics в ANDROID требует нового backend-контракта;
  до него отправлять только явное `diagnostics=null`. Никакой подмены platform.
- Внешний IP/город определяются запросом к HTTPS provider, не GPS. Ошибка geo-service
  не является сама по себе ошибкой туннеля; InternetVerifier работает независимо.
- Не объявлять APK release-ready, пока не проверены service ownership, foreground
  policy, сохранение credentials, IPv6 leakage и соответствующий реальный node.

## Примерные промпты для следующих задач

К каждому промпту относятся общие правила выше и источники из архитектуры.

**1 — каркас:**

> Создай Android-проект PrettyLisaVPN на Kotlin и Jetpack Compose по
> docs/android-architecture.md. Зафиксируй совместимый toolchain и зависимости,
> настрой debug/test/development flavors, базовую навигацию и GitHub Actions с APK
> текущего коммита. Проверь установку/запуск на эмуляторе. Backend и Windows не меняй.

**2 — дизайн:**

> Перенеси утверждённые logo/Rubik/colors/components в PrettyLisaTheme и мобильную
> навигацию. Сохрани оформление Windows, адаптируй размеры, Back, insets и IME.
> Проверь small widths, landscape, TalkBack и большой шрифт; приложи native screenshots.

**3 — экраны:**

> Реализуй все согласованные Android-экраны и состояния на изолированных fixtures.
> Проверь переходы, ошибки, loading/stale/disabled, диалоги и длинные значения.
> Тестовый VPN явно обозначь; не включай fake transport в release и не заявляй E2E.

**4 — auth:**

> Подключи существующие auth/session API, platform=ANDROID, installation UUID,
> защищённое атомарное хранение refresh credentials, single-flight rotation,
> восстановление, /me и logout. Проверь timeout, offline, expiry, revoke и restart.
> Настоящее OTP-письмо не запрашивай: ручной сценарий остаётся на паузе владельца.

**5 — API остальных экранов:**

> Подключи devices/messages/billing/support к текущим API без доработки backend.
> Для support отправляй diagnostics=null; для сообщений используй ANDROID и
> Android app_version. Сохрани request UUID/revision, обновление Home и read-only
> DISABLED/SANDBOX. Проверь вложения и pending recovery. Писем/платежей реально не отправляй.

**6 — VPN spike:**

> Выбери и закрепи официальный WireGuard tunnel AAR; проверь GoBackend service
> ownership, consent, foreground policy, ABI/page size и IPv4/IPv6 routing на Android.
> Реализуй заменяемый runtime port и DNS/HTTPS/route verification. Не создавай второй
> независимый VpnService и не показывай Connected по одному состоянию UP.

**7 — VPN lifecycle:**

> Подключи Android ConnectionCoordinator к create/current/terminate сессий.
> Соблюдай ordered first candidate, empty/legacy policy и native capability gates.
> Проверь смену сети, screen lock, process restart, отмену, expiry, revoke и cleanup.
> Неподдерживаемую конфигурацию не обходи новым узлом, другим профилем или изменением backend.

**8 — выбранный transport, отдельный объём:**

> Исследуй необходимость и реализуемость [конкретного согласованного режима]
> на Android. Перед включением проверь wire compatibility, секреты, JNI/ABI,
> protected outer sockets, MTU и lifecycle с соответствующим node. Не включай
> другие экспериментальные режимы и не меняй инфраструктуру без отдельного поручения.

**9 — приёмка:**

> Проведи Android acceptance на реальном устройстве с development backend.
> Проверь DNS/IPv4/IPv6/egress/traffic, Wi‑Fi ↔ mobile, фон, expiry, stop и удаление peer.
> Сохрани SHA/APK/device/OS/time и результаты. Реальный OTP — только после готовности
> владельца; платежи — только изолированным тестовым адаптером. Неизвестное не считай пройденным.

**10 — распространение:**

> Подготовь подписанную Android release-сборку и установку/обновление поверх
> предыдущей проверенной версии. Проверь credentials/settings migration,
> release без test adapters, секретов и debug logging. Приложи APK/AAB и инструкции;
> публикацию в магазине автоматически не выполняй.

## Матрица проверок и evidence

| Уровень | Что проверяет | Что не доказывает |
| --- | --- | --- |
| Kotlin unit tests | DTO, денежные minor units, dates/quota, error mapping, state transitions, candidate policy, vault epoch | Реальный Android tunnel/OS lifecycle |
| MockWebServer | Platform fields, auth headers, multipart, UUID/revision replay, timeout/cancel/races, отсутствие auto-POST retry | Development SMTP, внешний provider, node readiness |
| Compose/instrumented emulator | Навигация, тексты/семантика, screenshots, insets/fontScale/IME, rotation, consent UI | Совместимость всех OEM и мобильных сетей |
| Native/runtime tests | Реальные service callbacks/TUN ownership, key storage, network routing, stop/revoke | Production data plane без живого node |
| Handset + matching node | Handshake, VPN DNS/HTTPS/egress, IPv6 policy, handover/фон, quota/cleanup | DPI-evasion, бесшовность на всех провайдерах, store approval |

Для каждого этапа записывать source HEAD и build/run/attempt, device/API/ABI,
артефакты, тестовые/реальные зависимости и точные ограничения. OTP, refresh/private
keys, PSK и пользовательская история трафика не входят в отчёт/скриншоты/артефакты.
У исходного архитектурного этапа **не было Android APK и native screenshots**;
каркас 0.1.0 добавляет сборку/эмуляторную проверку, см. task PR и apps/android/README.
Настоящий API/VPN runtime E2E остаётся отдельным этапом;
его отсутствие ожидаемо и не означает ошибку сборки каркаса.

## Источники и открытые блокеры

- [Android architecture, contracts and native gates](android-architecture.md).
- [Текущий проект](project-status.md), [Windows navigation](windows-navigation.md),
  [Windows acceptance](windows-development-acceptance.md).
- [VPN profiles](connection-profiles.md), [verification](connection-verification.md),
  [obfuscation](obfuscation-providers.md).
- Реальные платежи остаются отдельной [issue #18](https://github.com/romankenig/PrettyLisaVPN/issues/18).
- Уточнение support diagnostics для Android, дополнительные protocol bootstrap,
  legacy transport secret provisioning и always-on — отдельные будущие задачи,
  не разрешение дорабатывать замороженный backend в ходе переноса.
