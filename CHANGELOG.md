# История изменений

Версии клиентов и backend независимы. Правила повышения и выпуска:
[docs/versioning.md](docs/versioning.md). Наличие записи под Unreleased не означает
опубликованный релиз, production deploy или проверку реального VPN.

## Unreleased

### Backend — 0.7.0 (Windows unchanged: 0.10.0)

- Added: private billing POST/status endpoints, account-scoped persistent idempotency,
  immutable quotes, price-revision admission and one pending operation per account.
- Added: replaceable sandbox provider port and leased/fenced durable reconciliation,
  including recovery from accepted-but-lost responses and local transaction failures.
- Added: append-only confirmed contracts and verified mandate/cancellation application;
  renewal preserves fixed prices and extends the paid period exactly once (migration 0024).
- Safety: no live adapter, credentials or real charges enabled; default new requests
  return BILLING_DISABLED. Test provider runs only under explicit test injection.
- Compatibility, uncertainty/manual reconciliation and actual validation/deploy evidence:
  docs/subscriptions-ui.md and task PR.


### Backend — 0.6.0 / Windows — 0.10.0

- Added: authenticated read-only billing overview, stable cross-device revisions
  and UTC/group-scoped monthly RUB/USD offers with independently discounted prices.
- Added: client groups, scheduled PostgreSQL catalogue with private CAS publication
  and immutable confirmed subscription price snapshots (migration 0023).
- Windows now displays server data and disables payments while the provider is
  unavailable; manual Platinum stays outside sales, historical unknown prices stay null.
- Temporary owner-authorized Premium prices: 199 RUB / 2.99 USD, regular 299 / 3.99.
- Compatibility: additive schema/API/capability. Payment operations and provider
  are not implemented. Exact current-source CI/native/development evidence: task PR.


### Backend 0.5.0 — права подписки

- Отмена автопродления сохраняет Premium до оплаченного срока; единая политика /me/VPN/messages.
- /me дополняется сведениями о подписке и правах; существующие поля совместимы.
- Открытые платные VPN-сессии учитывают истечение и продление; durable peer cleanup.
- Миграции 0021/0022: отмена автопродления отдельно от срока; ручной Platinum с правами Premium.
- Free: без рекламы, час/сутки UTC на аккаунт, durable резервации и возврат остатка после peer cleanup.
- Правила суточного лимита и ограничения удаления offline peer: docs/subscription-entitlements.md.

### Backend — 0.4.0 / Windows — 0.9.0

- Added: private support POST/status API, transactional requests, sanitized images,
  account-scoped idempotency and PostgreSQL delivery outbox (migration 0020).
- Added: app-helper@prettylisavpn.com → help@prettylisavpn.com mail with a separate
  Timeweb credential, fixed envelope, validated Reply-To and durable retries.
- Added: Windows SupportSender, stable retry UUID/snapshot, receipt/status UI and
  current-source native capture of recovery after a lost acceptance response.
- Privacy: strict diagnostic whitelist, ownership-checked session IDs, image
  metadata removal, quotas and 30-day content retention with deduplication tombstones.
- Compatibility: additive API/schema. SMTP acceptance differs from inbox delivery;
  exact checks, builds, deployment and remaining limitations are in the task PR.


### Backend — 0.3.0

- Added: authenticated JSON v1 account messages, immutable localized revisions,
  schedules, priorities and audiences by account/plan/platform/SemVer range.
- Added: durable account-wide, idempotent acknowledgement; an ACK on Windows
  removes that revision from subsequent Android/other-device requests.
- Added: trusted server-only publish/withdraw CLI with explicit redisplay policy;
  no public admin endpoint, arbitrary URL, HTML or executable content fields.
- Compatibility: migration 0019 is additive; Windows stays 0.8.0. Other platforms
  receive messages after implementing the common contract in their own clients.
- Validation and actual deployment status: task PR; docs/account-messages.md.

### Documentation — карта Windows 0.8.0

- Added: сводная схема экранов/popup, таблица маршрутов, auth/возвраты/ошибки,
  подготовленный платёжный flow и фактическая доступность интеграций.
- Changed: ссылка в README и правило актуализации карты в AGENTS; карта учитывает
  backend 0.2.0 и реализованный last_login_at после merge PR #8.
- Version unchanged: Windows 0.8.0, backend 0.2.0; только документация.

### Backend — 0.2.0

- Added: nullable UTC `last_login_at` on device responses, persisted only after
  successful OTP login in the same transaction as the new auth session.
- Fixed: device revocation atomically invalidates auth sessions and terminates
  PENDING/ACTIVE VPN sessions, with durable peer cleanup across node outages.
- Fixed: provision/revoke races, concurrent cleanup and premature reuse of an
  unremoved peer public key or client address. Cleanup acknowledgement is durable.
- Compatibility: additive migration 0018 leaves legacy timestamps null; refresh,
  listing, renaming and VPN connect do not change last login. Windows remains 0.8.0.
- Validation: current CI/source/build SHA and screenshot provenance are recorded
  in the task PR and docs/devices-ui.md; development rollout is separate.

### Backend infrastructure — version unchanged (0.1.0)

- Changed: runtime-версия CI из pyproject: `<base>-dev.<run>+g<полный SHA>`;
  отдельные теги/каталоги SHA/run/attempt и сохранённые runtime metadata/image ID.
- Fixed: rollback использует сохранённый env/образ без pull, rebuild и миграций;
  точное JSON-сравнение `/version` допускает пробелы, отвергает неверную версию.
- Validation: offline contract tests и реальные ограничения Cloud, исторический
  CI/deploy и необходимые доступы описаны в docs/backend-cloud-handoff.md.
- Compatibility: версия пакета, схема БД и HTTP API не изменены;
  реализация CI не означает, что новый runtime уже развёрнут на стенде.

### Windows — 0.8.0

- Added: сообщения аккаунту после входа/восстановления сессии: JSON-заголовок,
  абзацы, списки, категории новостей/обновлений/акций и внутренние переходы.
- Added: серверное подтверждение ID + revision; показ не означает прочтение,
  «позже» не записывает прочтение, ошибки подтверждения допускают повтор.
- Added: очередь, срок действия, отмена при смене аккаунта, ожидание других
  modal-окон и безопасный текстовый fallback для будущих блоков/действий.
- Compatibility: отдельный MessagesClient и предлагаемый кроссплатформенный
  API v1; backend 0.1.0 не изменён. При отсутствии API нет popup и блокировки входа.
  Серверное хранение/аудитория/общие подтверждения — docs/account-messages.md.
- Validation: итоговые HEAD/build SHA, все CI runs и native screenshots в PR.

### Windows — 0.7.0

- Changed: «о приложении» без eyebrow и окружения, с frontend/backend версиями.
- Added: пустой раздел FAQ и popup «помощь и поддержка»: тема, описание,
  email для ответа, до трёх скриншотов и отключаемые технические данные.
- Added: безопасная проекция версий/состояния сессий, предпросмотр состава,
  проверка формата/размера скриншотов и интерфейс будущего отправителя.
- Added: подпись «inspired by love of my life, Lisa» внизу экрана.
- Compatibility: backend 0.1.0 не изменён; отправка пока недоступна, реального
  адресата и backend endpoint нет. Контракт и этап подключения — docs/support-ui.md.
- Validation: финальные SHA, все CI runs и native screenshots фиксируются в PR.

### Windows — 0.6.1

- Changed: экран устройств без надписи «аккаунт», пояснения разделены строкой.
- Changed: вместо платформы — стабильный ID и дата добавления; совпадающие
  сокращения ID разворачиваются полностью. ID виден и перед отзывом доступа.
- Added: отображение последнего входа из необязательного last_login_at;
  отсутствующее значение — «нет данных», updated_at не подменяет дату входа.
- Compatibility: текущий backend 0.1.0 совместим и не изменён; last_login_at
  пока только клиентское расширение контракта, см. docs/devices-ui.md.
- Validation: итоговые SHA, CI runs и native screenshot фиксируются в PR.

### Windows — 0.6.0

- Added: выбор способа оплаты перед оформлением/продлением: «мир», банковские
  карты (Visa/Mastercard/UnionPay/AmEx), Alipay/WeChat Pay и криптовалюта, с иконками.
- Changed: выбранная валюта определяет порядок/предвыбор: RUB → «мир», USD →
  банковская карта. Регион задаёт начальную валюту; ручной выбор имеет приоритет.
- Added: отдельная кнопка «перейти к оплате». До её нажатия нет backend-операции
  и открытия браузера; цена/валюта/предложение фиксируются при открытии окна.
- Compatibility: в предлагаемый billing-контракт добавлен payment_route;
  backend 0.1.0 и реальные провайдеры по-прежнему отложены владельцем.
- Validation: финальные SHA, все CI runs и native screenshots фиксируются в PR.

### Windows — 0.5.0

- Fixed: симметричная восьмизубая шестерёнка настроек с общим центром.
- Added: экран подписки с данными backend: уровень, срок, текущая стоимость,
  месячные цены в RUB/USD и необязательные зачёркнутые цены акции.
- Added: выбор основной валюты по последней стране до VPN (RU → RUB, иначе USD)
  и ручное переключение отдельно для аккаунта; IP/город не сохраняются.
- Added: оформление, продление, изменение способа оплаты и подтверждение отмены
  через отдельный клиентский адаптер; внешнее подтверждение не считается оплатой.
- Compatibility: backend source 0.1.0 не менялся; API и платёжный провайдер
  реализуются позже по решению владельца. Без API показывается недоступность,
  без выдуманных цен. Данные в UI review только синтетические.
- Validation: финальные SHA, все CI runs и native screenshots фиксируются в PR.

### Windows — 0.4.4

- Changed: подпись подписки — «управление подпиской и платежами»; выход —
  «завершить сессию на этом устройстве».
- Compatibility: backend 0.1.0, платежи и поведение приложения без изменений.
- Validation: финальные SHA, все CI runs и native screenshot фиксируются в PR.

### Windows — 0.4.3

- Changed: убрана надпись «приложение» над настройками, подписка расположена перед
  устройствами. Подпись подписки — «управление подпиской и картой» (четыре слова).
- Compatibility: экран подписки пока пуст; backend 0.1.0 и платежи без изменений.
- Validation: финальные SHA, все CI runs и native screenshot фиксируются в PR.

### Windows — 0.4.2

- Added: пункт «подписка» в настройках с иконкой карты; открывает пустой экран
  с заголовком и возвратом в настройки. Управление оплатой пока не реализовано.
- Compatibility: backend 0.1.0, платежи и VPN-поведение без изменений.
- Validation: финальные SHA, все CI runs и native screenshots фиксируются в PR.

### Windows — 0.4.1

- Changed: из правого блока Home убраны подписи «подключение» и
  «выбор сайтов появится позже»; карточки режимов и их поведение сохранены.
- Compatibility: backend 0.1.0 и VPN-маршрутизация без изменений.
- Validation: финальные SHA, CI и native screenshot фиксируются в PR.

### Windows — 0.4.0

- Changed: Home подписан home, email — аккаунт; статичный статус аккаунта удалён.
- Added: блок «что защищаем» — весь трафик, только выбранные сайты, кроме выбранных
  сайтов. Два выборочных режима отключены с «скоро»; реальная маршрутизация отложена.
- Added: после CONNECTED показаны публичные параметры действующего соединения
  небольшим приглушённым текстом и в раскрываемых подробностях, без ключей клиента.
- Compatibility: backend 0.1.0 и VPN-маршрутизация не менялись; adapter metadata
  optional, отсутствие сведений не блокирует подключение/отключение.
- Validation: финальные SHA, runs и native screenshots будут записаны в PR после
  завершения всех проверок, без дополнительного docs push.

### Windows — 0.3.0

- Changed: домашний экран — dropdown с автопилотом, топ-3 по рейтингу и всеми
  доступными странами по алфавиту; круглыми флагами и сохранением выбора аккаунта.
- Changed: кнопка и статус подключения находятся слева; правая панель оставлена пустой.
- Added: ⭐ для premium и 💎 для platinum; клиент готов принимать platinum,
  backend-тарифы и платежи в этой задаче не менялись.
- Added: текущие город, страна и внешний IP через заменяемый HTTPS-провайдер,
  обновление раз в минуту и после смены сети/VPN; старые ответы не перезаписывают новые.
- Compatibility: backend 0.1.0 и VPN-контракты сохранены; прежний статичный статус
  аккаунта пока сохранён. Подробности и ограничения — docs/home-screen.md.
- Validation: финальные SHA, все CI runs и native screenshots фиксируются в PR
  после окончания проверок, без дополнительного docs push.

### Windows — 0.2.1

- Fixed: PrettyLisaVPN сохраняет точное написание в заголовках и сообщениях об ошибках.
- Changed: заголовок входа — «вход по email», подсказка над «продолжить» без точки.
- Compatibility: API, backend 0.1.0 и VPN-поведение не менялись.
- Validation: финальные SHA, workflow и native screenshots фиксируются в описании PR
  после завершения всех проверок; отдельный docs commit для результатов не создаётся.

### Windows — 0.2.0

Переход на 0.2.0 применён к package.json, Cargo.toml, tauri.conf.json
и собственной записи Cargo.lock. Выпуск ещё не опубликован; новую сборку
подтверждает отдельный Windows run в журнале продолжения.

- Added: кастомные оконные кнопки, общий заголовок с исходным замком, навигация
  иконками, настройки с устройствами и выходом из аккаунта.
- Changed: прозрачный фон замка с контрастным светлым знаком, строчные подписи,
  приглушённые версии, отключённая навигация во время входа/OTP.
- Changed: упрощён экран входа: «отправим одноразовый код» и ненавязчивый placeholder
  example@email.com, не влияющий на введённое значение.
- Changed: фиксированное окно 960 × 640 со скруглением, отдельная прокрутка списков,
  две колонки на Home, локально включённый Rubik.
- Added: версии frontend/backend внизу sidebar; backend читается из GET /version,
  ошибка получения не блокирует интерфейс.
- Compatibility: backend API/VPN-логика не менялись; /devices перенаправляется
  в /settings/devices. Проверка версии реального backend остаётся в handoff.
- Validation: 206 тестов, native Windows build 0.2.0 и UI capture прошли для
  PR head `b0f559dda4f7aa14d1e55dddbc0822e46fbce4c1`, фактический build SHA
  `cabd1b49f1766c64bc1a54fae754e9ce805c537c`:
  [Windows run](https://github.com/romankenig/PrettyLisaVPN/actions/runs/38941095884).
  Это UI review с synthetic fixtures, не подтверждение production VPN.

### CI — без повышения версии приложения

- Fixed: Windows window capture больше не запускает сценарий нового интерфейса
  на старом exe из фиксированного run; сборка и capture используют общий workflow
  текущего commit.
- Fixed: ограниченный native PowerShell timeout увеличен с 20 до 60 секунд;
  повторный запуск workflow может перезаписать одноимённый артефакт.
- Added: обязательная проверка всех Actions events и финальных jobs последнего
  remote HEAD, включая проверки после docs commit.

### Документация — без повышения версии приложения

- Added: независимый SemVer, правила build identity, changelog и дальнейших задач,
  закреплённые в docs/versioning.md и AGENTS.md.
- Recorded: текущий legacy runtime-формат backend dev-SHA и отдельная задача
  перехода его CI/deploy/rollback. Развёртывание в этой задаче не менялось.

## Исходная база при принятии правил — 2026-10-16

Windows и backend объявляют 0.1.0 в исходных манифестах. Предыдущая история
релизов здесь не реконструируется и стабильный выпуск задним числом не объявляется.
