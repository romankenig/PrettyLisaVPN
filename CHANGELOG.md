# История изменений

Версии клиентов и backend независимы. Правила повышения и выпуска:
[docs/versioning.md](docs/versioning.md). Наличие записи под Unreleased не означает
опубликованный релиз, production deploy или проверку реального VPN.

## Unreleased

### Backend — 0.22.1

- Recheck configured zero-rated servers every three minutes on the main server,
  with distinct slots, existing operation locks and no replay of missed intervals.
- Use the dashboard rating, including stale/unverified results; return to hourly
  checks after recovery. Active connections do not suppress the normal probe.
  No schema change. See [monitoring retry handoff](fleet-fast-rechecks.md).

### Android — 0.15.1 / dashboard — 0.4.2

- Replace the 253 MB universal debug APK with standalone per-CPU APKs, strip Go
  debug symbols and compress native libraries. Each APK must stay below 40 MB.
- Dashboard distributes the ARM64 phone APK and labels its architecture; CI
  tests the matching x86_64 build and retains ARM32/x86 builds separately.
- Preserve all VPN engines, six locales, signing identity and one-APK installation.
  Backend and Windows versions are unchanged by this packaging task.
  See [APK size handoff](android-apk-size.md) for build and publication evidence.

### Managed transports — in progress

- Add dispatch-only real Android/Windows TUN acceptance per selected method,
  including sustained connection, independent tunneled HTTPS and cleanup proof.
- Use our own verified TLS target in the fleet rollout after isolating an
  SNI-dependent relay handshake failure; retain strict client identity checks.
- Backend 0.22.0 adds common session admission and durable managed grants, keeping
  account-wide Free quota and the WireGuard API compatible (migration 0035).
- Android 0.15.0 adds private in-APK engine control and Advanced settings.
  Windows 0.18.0 adds a private elevated engine host and the same method selection.
- Add direct/relay adapters for AmneziaWG, SSTP, SoftEther, SS2022, VMess, VLESS, REALITY, Hysteria 1/2 and
  Salamander; keep placeholders in UI-test fixtures only.
- MIT/MPL runtime 0.3.0 excludes sing-box and GPL/LGPL integrations.
- Add an MIT SSTP adapter with authenticated TLS/PPP and in-memory TCP/UDP;
  verify DNS/HTTPS with official SoftEther, with DE/US client acceptance pending.
- Add an MIT native SoftEther adapter with authenticated, isolated Ethernet
  segments and tunneled DNS/HTTPS interoperability against official SoftEther.
- Preserve Hysteria 1 response
  bytes and graceful EOF when the upstream server closes its connection.
- Dashboard 0.4.1 exposes matching source/license archives beside new managed
  client downloads; atomic publication rejects missing or mismatched sources.
  [Rollout and remaining validation](docs/managed-transports.md).

### Dashboard — 0.4.0

- Place individual speed/rating/active-connection charts inside each server card.
  Active connections use hourly bars; repeated probes in one hour are not summed.
- Show only aggregates for the selected group/server set in the shared chart and
  summary: mean download/upload speed, median rating, sum of active connections.
  Preserve real zeros, report missing-data coverage and respect both filters.
- Backend schema/API and client binaries are unchanged by this dashboard commit.
  See [dashboard metrics handoff](docs/dashboard-group-metrics.md).

### Deployment follow-up — product versions unchanged

- Publish verified client downloads through the deployment user's existing Docker
  access, without exposing dashboard credentials or requiring root SSH in CI.

### Backend — 0.21.1 / Android — 0.14.2 / Windows — 0.17.2

- Fix account-wide Free quota admission: reserve renewable grants of at most 180
  seconds, allowing multiple devices to share the hour instead of reserving it all
  for the first device. Preserve summed device time, UTC reset and confirmed cleanup.
- Revoke unverified setup automatically after 90 seconds, retry uncertain removal
  durably, and preserve confirmed sleeping-device connections. Migration 0034.
- Attempt remote revocation even when local tunnel shutdown fails; recover this
  device's abandoned grant on client startup and allow cleanup retry in the UI.
  Windows waits for asynchronous service deletion. Freeze stale balance estimates
  after 60 seconds without a fresh account response.
- See [quota/cleanup handoff](docs/free-quota-cleanup.md).

### Android — 0.14.1 / Windows — 0.17.1 (included in the following patch builds)

- Name the relay method **WireGuard+** in every language, preserving method IDs
  and fallback preferences. Remove the implementation-status banner and display
  the first-connection hint with 60% text opacity.

### Dashboard — 0.3.0 / Backend — 0.21.0 / Android and Windows unchanged

- Permanent Android APK and Windows EXE download links on the private dashboard.
  Successful develop CI builds publish verified binaries to the main server;
  atomic updates preserve both platforms and reject outdated or corrupt builds.
- Display all dashboard timestamps in GMT+3, including hour details and downloads.
  Backend storage, probes and the Free UTC-day allowance remain unchanged.
- Preserve rating at each completed probe (migration 0033) and expose individual
  historical download/upload speeds, rating and active connections on hour selection.
  Legacy speeds remain available; missing historical ratings stay unknown.
- Add a speed/rating/active-devices chart switch respecting server/group selection
  and missing data. Devices count observed active VPN connections per node;
  relay routes appear on both nodes, not as unique devices across the service.
- Set new-node capacity to 20 and speed-rating target to 30 Mbps; allow capacity
  changes through the existing admin PATCH while preserving omitted values.
- See [deployment and verification handoff](docs/dashboard-client-downloads.md).

### Android — 0.14.0 / Windows — 0.17.0 / Backend unchanged 0.20.0

- Remember the last Internet-verified VPN method on the device and try it first
  on subsequent connections, including after restarting the app. Preserve every
  remaining fallback and confirmed cleanup; cancellation/failure never changes it.
- Show a short first-connection timing hint while connecting in all six languages.
- Store only the method ID, with no keys, endpoints, account or browsing history.
  See [handoff](docs/connection-method-preference.md).

### Android — 0.13.0 / Windows — 0.16.0 / Backend — 0.20.0 / Dashboard — 0.2.0

- Direct WireGuard falls back through a permanent RU intermediary, with verified
  exit IP, both-hop cleanup and concise progress. Other methods remain timed
  placeholders; Android remains one APK.
- INTERMEDIATE/FREE/PREMIUM groups, admin rename/group API, intermediate exclusion
  from customer selection, dashboard group summaries and filters.
- Account-wide Free balance includes unused active reservations; both clients show
  remaining time and reset. Audited server-only one-time allowance reset.
- **BREAKING (backend rollback):** migrations 0031/0032 require draining both-hop
  leases before downgrade. See [design and rollback](docs/wireguard-relay-quota.md).

### Android — 0.12.2 / Backend — 0.19.0 / Windows unchanged 0.15.0

- Established WireGuard access no longer depends on Android delivering HTTP
  heartbeats during sleep. Server-owned grants still enforce account/device/auth
  revocation, subscription deadlines, Free quota and short node expiry.
- Android keeps the verified tunnel during temporary API outages and reconciles
  after waking; confirmed revocation/expiry still stops it. Legacy servers retain
  bounded heartbeat behavior through capability negotiation.
- Hourly full VPN checks now run alongside managed customer connections. Customer
  grants/revocations remain runnable during checks; the separate probe does not
  occupy a customer address or enter the weighted load score.
- Add regressions for silent clients, access revocation, concurrent monitoring,
  load-weighted ratings and a real Android five-minute deep-Doze acceptance test.
  Source changes alone do not prove deployment or device acceptance; see
  [sleep stability handoff](docs/android-sleep-stability.md).

### Android — 0.12.1 / Windows unchanged 0.15.0

- После включения WireGuard API, heartbeat и проверка доступности сервера используют
  VPN-сеть и свежие HTTP-пулы, без переиспользования соединений прежнего маршрута.
- Временный сбой heartbeat повторяется в ограниченном окне; отзыв доступа,
  окончание сессии и ошибки авторизации по-прежнему останавливают VPN.
- Реальная проверка расширена до двух минут и нескольких heartbeat; прежний
  короткий тест 0.12.0 не подтверждал длительную устойчивость подключения.

### Backend — 0.18.1 / клиенты unchanged

- Исправлена первичная установка WireGuard на Ubuntu 26.04: firewall запускается
  отдельными шагами systemd, без Python hooks внутри AppArmor-профиля wg-quick.
  Ограничения AppArmor сохраняются; rollback удаляет только собственный drop-in.
- Добавление `timeweb-rus-001` (RU, все тарифы) проходит через существующие admin API,
  inventory и серверный планировщик; фактическая проверка и deploy — в handoff.

### Backend — 0.18.0 / Windows — 0.15.0 / Android — 0.12.0

- Restore real WireGuard through a new authenticated customer lease API and the
  main-server worker. Preserve Free daily quota, paid access, device revocation,
  confirmed cleanup and short node deadlines; add migration 0030.
- Android uses one APK with WireGuard, system VPN consent and foreground lifetime.
  Windows manages the official installed WireGuard client through UAC and detects
  conflicts with another VPN without disabling it.
- Confirm tunnel-bound DNS/HTTPS and expected server egress before Connected;
  preserve automatic fallback/progress for the remaining placeholder methods.
- See [client handoff](docs/client-wireguard.md) and PR #32 for exact build,
  deployment and real-connection acceptance evidence.

### Fleet dashboard — 0.1.0

- Serve the separate monitoring dashboard on the main server at `/dashboard/`,
  protected by an operator login/password over HTTPS. ChatGPT sign-in is not used.
- Protect both assets and metric responses; keep the read-only monitoring token
  out of the browser. Preserve credentials and the site across backend deploys.
- Backend remains 0.17.0; Windows 0.14.1 and Android 0.11.1 are unchanged in this
  dashboard change. Client WireGuard integration is the next step in this task.

### Backend — 0.17.0 / Ubuntu fleet helper — 0.1.0

- Add an explicit administrator API and durable Ubuntu WireGuard provisioning
  operations, executed by a separate worker with a pinned SSH inventory.
- Add staggered hourly cross-node VPN checks, passive observations, seven-day
  history and plan-aware country ratings. Full success requires handshake, DNS,
  HTTPS, expected egress IP and confirmed temporary-peer cleanup.
- Run scheduling and acceptance reporting on the main server independently of
  Codex/ChatGPT; node-local timers expire temporary access even if the worker stops.
- Migration 0029 adds independent fleet tables; legacy records remain untouched.
  Windows 0.14.1 and Android 0.11.1 remain placeholders; no client tunnels enabled.
- Private Sites monitoring and real DE/US acceptance are tracked separately from
  automated tests: [fleet lifecycle handoff](docs/fleet-lifecycle.md).

### Android — 0.11.1 / Windows — 0.14.1

- Fix current location when the primary geolocation provider cannot resolve or
  returns an error: native Windows and Android fall back to IPinfo over HTTPS.
  Android public location refresh no longer waits for account/country API calls.
- Windows displays the validated backend SemVer core from GET /version, like
  Android (for example, `0.16.0`); unavailable/invalid versions stay unavailable.
- Backend remains 0.16.0, schema unchanged. The 14 VPN placeholders remain in place.
  Build evidence and limitations: [location fix handoff](docs/client-location-fix.md).

### Android — 0.11.0 / Windows — 0.14.0 / Backend — 0.16.0

- BREAKING: remove the real VPN connection implementation, managed Xray engine,
  WireGuard runtime/keys, node agent, server profiles, obfuscators and provisioning.
  Old session/credential endpoints no longer exist. Upgrade clients together;
  do not use older clients to connect to the retired DE/US data plane.
- Keep a sequential executor with 14 independent adapter slots. Every shipped
  adapter waits 3 seconds and fails. Show current/previous method, support Cancel,
  stop after verified success when a future real adapter replaces its placeholder.
- Android remains one APK; no VPN/foreground consent or native engine dependency.
  Windows no longer requests administrator rights or a VPN DLL.
- Preserve authentication, account/devices, billing, support, locale and UI routes.
  Historical database mappings/quota accounting and migrations through 0028 stay;
  there is no schema/data deletion. Country metadata reports no live availability.
- Migration/rollback and exact build evidence: [reset handoff](docs/vpn-placeholder-reset.md).


### Android — 0.10.0 (code18), backend — 0.15.0, node agent — 0.3.0, engines — 0.2.0

- One Android APK with a private engine process; the separate companion is no
  longer required. One native VPN service handles WireGuard and managed methods.
- Preserve WireGuard candidates, then try the complete authenticated 20-profile
  server catalog, with bounded verification, confirmed stop and method comments.
- Add backward-compatible managed-plan issuance, isolated per-session listener
  blocks and pinned-CA TLS. Every access is revoked together on stop or expiry.
- Bounded VPN-bound DNS/HTTPS verification prevents a stalled system DNS lookup
  from blocking fallback. Tests exercise real encrypted TCP/UDP on every managed
  variant; live DE/US acceptance is separate and limited to three new attempts.
- Schema remains 0028; Windows remains 0.13.0. Scope and rollout evidence:
  [single APK plan](docs/android-single-apk-plan.md).

### Backend — 0.14.0 / node agent — 0.2.0, development acceptance in progress

- Authenticated, opt-in VLESS/REALITY leases for owned DE/US sessions; migration
  0028 persists issuance/revocation intent and node removal acknowledgement.
- Isolated Xray processes enforce bounded authorization and close established
  connections on revoke. Existing WireGuard cleanup cannot bypass managed cleanup.
- Android 0.9.0/code17 now controls the separately installed, identically signed
  companion through Binder v3, including real consent and tunnel-bound DNS/HTTPS.
  Update both preview APKs together; the earlier Binder v2 pair is incompatible.
  Windows remains 0.13.0; its new-engine wiring is still pending.
- This source change does not claim a deployed or verified real connection.
  Bounded trial and rollout: [docs/managed-vpn-acceptance.md](docs/managed-vpn-acceptance.md).

### Windows — 0.13.0 / Android — 0.9.0 (code17), transport task in progress

- Ordered candidates are tried until independent Internet verification succeeds;
  failed attempts must stop before the next starts. Cancellation stops the loop.
- Android monitors the selected candidate and shows its verified method.
- Windows and Android show brief localized attempt comments, including switching
  after a failed method. Android keeps the comment visible during verification;
  completion clears it. Development engine diagnostics expose only closed stage
  codes, never destinations, DNS names, profiles or exception messages.
- Windows fallback consumes the original server allowance during startup and
  verification. Expired attempts cannot connect or try another candidate;
  canceled attempts retain backend ownership when local cleanup fails.
- This is not yet delivery of the additional article protocols or managed engines.
  Scope, current limits and owner decisions:
  [docs/vpn-methods-from-article.md](docs/vpn-methods-from-article.md).

### Managed engine component — 0.1.0, in development

- Separate process and Android companion sources, pinned Xray MPL-2.0 core, typed
  private profiles and closed status/error responses. No raw engine config,
  traffic logs, direct DNS fallback or unverified Connected result. The unpublished
  sing-box prototype was replaced following the owner's license decision.
- Constructors accept 21 method/transport combinations with the pinned Xray
  core. Windows/Android dependency license checks exclude GPL/AGPL/LGPL; the
  REALITY limiter uses a separately tested MIT implementation.
- Android wiring and development server authorization are implemented in this
  task; Windows wiring, full article coverage and real device acceptance remain
  tracked in [docs/managed-vpn-acceptance.md](docs/managed-vpn-acceptance.md).

### Backend — 0.13.0 / Windows — 0.12.1 / Android — 0.8.1 (code16)

- Opt-in DELETE confirmation distinguishes persisted termination intent from
  acknowledged server peer removal. Legacy clients keep the same response.
- Windows and Android retain cleanup retries until the requested session has
  explicit confirmation; missing or malformed acknowledgements fail closed.
- Deploy backend before these clients. This does not enable OpenVPN fallback;
  external-client acceptance and compatibility are tracked in
  [docs/vpn-cleanup-confirmation.md](docs/vpn-cleanup-confirmation.md).

### Backend — 0.12.0 / клиенты unchanged

- Миграция 0027 и PostgreSQL-реестр OpenVPN credentials: неизменяемая привязка
  запроса, точный сохранённый сертификат для повторной доставки, устойчивый intent
  отзыва и отдельное подтверждение удаления на узле.
- Конкурирующие повторы не перезаписывают результат; поздняя выдача после отзыва
  запрещена. Полный CRL snapshot сохраняет уже подтверждённые отзывы.
- Реестр пока не подключён к публичному API, signer worker и node-agent.
  WireGuard sessions работают по прежнему пути. Handoff:
  [docs/openvpn-credential-ledger.md](docs/openvpn-credential-ledger.md).

### Backend — 0.11.0 / клиенты unchanged

- Первый этап OpenVPN TCP fallback: изолированный модуль подписания клиентского
  CSR и полного списка отзыва (CRL), с заменяемым интерфейсом выпуска сертификатов.
- Приватный ключ клиента остаётся на устройстве; идентификатор и clientAuth-права
  задаёт подписант. Проверяются подпись CSR, ключ CA и срок авторизации; срок
  сертификата ограничен одним часом. Публичная выдача сессий остаётся WireGuard-only.
- Это основа подписания, не работающий fallback в приложениях. Хранение выдач,
  доставка/применение CRL, отключение отозванных соединений и native-движки клиентов
  ещё не подключены. Handoff: [docs/openvpn-credentials.md](docs/openvpn-credentials.md).

### Android — 0.8.0 / Windows и backend unchanged

- Реальный VpnService/WireGuard adapter: системное разрешение, ephemeral key pair,
  foreground notification, connect/disconnect и существующие backend VPN sessions.
- Connected требует VPN-bound DNS/HTTPS, handshake, route identity и RX/TX growth;
  неподдерживаемые профили, ошибки и revoke останавливают tunnel и удаляют session.
- Durable account-scoped cleanup, восстановление после restart и защита от
  повторного POST при неизвестном исходе; backend/платежи не меняются.
- Android 0.7.2/code14 → 0.8.0/code15 (MINOR). Ограничения профилей, проверки и
  ручная приёмка: [docs/android-vpn-runtime.md](docs/android-vpn-runtime.md).

### Android — 0.7.2 / Windows и backend unchanged

- Повторная отправка OTP доступна через 60 секунд вместо 30; monotonic deadline
  сохраняется при повороте, смене языка и возврате к email.
- Метка текущего устройства использует Heliotrope/Christalle вместо кнопочного Viking.
- Уведомления убраны из настроек и отдельного экрана. Как в Windows, показываются
  автоматически по одному popup после входа; «позже» не отправляет ACK. Подтверждение
  и переход используют revision-aware ACK; при ошибке popup остаётся для повтора.
  Нет локального архива; отсрочка только в памяти текущего входа, expiry соблюдается.
- Android 0.7.1/code13 → 0.7.2/code14 (PATCH); handoff:
  [docs/android-otp-popup-polish.md](docs/android-otp-popup-polish.md).

### Android — 0.7.1 / Windows и backend unchanged

- Один выбор локации: автопилот, три лучших и все доступные страны; флаги и
  серверный рейтинг 0–100, включая ранее потерянный рейтинг автопилота.
- Текущие регион/IP компактно внутри блока подключения; кнопка остаётся UI preview.
- Отозванные устройства скрыты, текущая установка первая с яркой крупной отметкой.
- «Сообщения аккаунта» уточнены как уведомления сервиса; добавлено пояснение.
- Исправлены начала предложений во всех шести каталогах, расширена проверка текста.
- Общая полоса потери связи над версиями: Android default-network callback и
  ограниченный публичный GET /version; автоматическое восстановление, только foreground.
- Android 0.7.0/code12 → 0.7.1/code13 (PATCH). Handoff:
  [docs/android-location-connectivity-polish.md](docs/android-location-connectivity-polish.md).

### Android — 0.7.0 / Windows и backend unchanged

- Главная приведена к Windows: сводка аккаунта, автопилот/страна с фактическими
  странами API, текущие регион/IP, режимы защиты трафика. Кнопка подключения
  активна как UI preview и не запускает VPN; цепочка служебных кнопок убрана.
- Настройки получили значки Windows, подписи и красный выход; сообщения доступны
  в настройках, поддержка — из About. Устройства обновляются жестом на краю списка,
  даты показываются локально в читаемом виде, текущая установка помечена.
- Постоянная публичная debug-подпись и scoped installation fallback предотвращают
  новые устройства при дальнейших обновлениях/переустановке с тем же ключом.
  Уже существующий installation UUID сохраняется. Старые серверные записи не
  скрываются и не отзываются по совпадению имени. При переходе со старого debug
  APK требуется однократная переустановка из-за прежних случайных CI-ключей.
- Поддержка показывает имена/подготовку файлов, удаление по крестику и реальный
  прогресс записи multipart. Одна отправка, без «готово»; Back/draft guard сохранён.
  Opt-in Android диагностика с preview добавляется к тексту обращения: серверный
  structured diagnostics остаётся WINDOWS-only, Android не выдаётся за Windows.
- Android 0.6.5/code11 → 0.7.0/code12 (MINOR). Handoff:
  [docs/android-home-support-polish.md](docs/android-home-support-polish.md).

### Android — 0.6.5 / Windows и backend unchanged

- Фон значка APK изменён с Viking на Purple Heart `#5f22d9`; замок использует
  Mercury `#e4e4e4` для контраста. Исправленная симметрия и размеры сохранены.
- Android 0.6.4/code10 → 0.6.5/code11 (PATCH); handoff:
  [docs/android-otp-icon-polish.md](docs/android-otp-icon-polish.md); CI/artifacts — PR #25.

### Android — 0.6.4 / Windows и backend unchanged

- Область OTP-ссылок с отступами уменьшена с 80dp до 56dp при стандартном шрифте;
  48dp touch targets, перенос и 30-секундный resend сохранены. Rubik Medium,
  Christalle и подчёркивание согласуют ссылки с оформлением приложения.
- По замечанию владельца исправлена симметрия Android замка-сердца: дужка,
  сердечко и скважина имеют общую ось; launcher центрирован. Шапка и полный
  Android логотип используют исправленную геометрию, надпись не меняется.
- Android 0.6.3/code9 → 0.6.4/code10 (PATCH); handoff:
  [docs/android-otp-icon-polish.md](docs/android-otp-icon-polish.md), CI/artifacts — PR #25.

### Android — 0.6.3 / Windows и backend unchanged

- OTP resend/change email оформлены как подчёркнутые фиолетовые ссылки в компактном
  FlowRow над sign in, с переносом при крупном шрифте. Размер текста и 48dp touch
  targets сохранены; 30-секундный монотонный resend deadline не меняется.
- Общий About для live/fixture повторяет Windows 0.12.0: версии frontend/backend,
  FAQ-карточка, помощь с кнопкой обращения и исходное английское посвящение внизу.
  Две desktop-карточки адаптированы в вертикальные мобильные; build SHA и сообщения
  убраны из About. Fixture-инструменты доступны из Settings, build — в Scenarios.
- Android 0.6.2/code8 → 0.6.3/code9 (PATCH). Контракт и приёмка:
  [docs/android-about-otp-ui.md](docs/android-about-otp-ui.md); SHA/CI/artifacts — PR #25.

### Android — 0.6.2 / Windows и backend unchanged

- Версии frontend/backend перенесены из шапки в общую тонкую нижнюю полоску
  Christalle; она есть на auth/OTP и экранах аккаунта, под навигацией.
- Нижние safe drawing/IME отступы учитываются общим контейнером без повторного
  отступа внутри навигации. При клавиатуре полоска остаётся над ней.
- Флаг и центрированные English/native names сближены в selector и меню;
  приглушённый native name, порядок языков и сохранение выбора не меняются.
- Android 0.6.1/code7 → 0.6.2/code8 (PATCH). Handoff:
  [docs/android-language-ui.md](docs/android-language-ui.md); CI/SHA/artifacts — PR #25.

### Android — 0.6.1 / Windows и backend unchanged

- В общей шапке показана только проверенная числовая часть фактической backend
  SemVer: `0.10.0-dev.<run>+g<sha>` → `0.10.0`. Серверный runtime не меняется.
- Увеличены знак и PrettyLisaVPN; языки центрированы в отдельных колонках,
  native name приглушено. Узкие экраны и крупный шрифт используют две строки.
- Исправлены native-термины электронной почты и начальные строчные буквы во всех
  шести каталогах. Введённый текст, бренды, протоколы и данные API не преобразуются.
- Android 0.6.0/code6 → 0.6.1/code7 (PATCH); handoff и приёмка:
  [docs/android-language-ui.md](docs/android-language-ui.md), актуальные SHA/CI — в PR #25.

### Android — 0.6.0 / Windows и backend unchanged

- Добавлен выбор Chinese/English/French/German/Russian/Spanish с флагами и обоими
  названиями языка в правом верхнем углу общей шапки. Ручной выбор сохраняется;
  без него English, для подтверждённой RU-локации до VPN — Russian.
- Общая шапка на auth/OTP и остальных экранах: исходный знак, PrettyLisaVPN,
  frontend BuildConfig.VERSION_NAME и фактическая backend-версия GET /version
  либо локализованное «недоступна». Прежний development banner удалён.
- OTP resend/change email оформлены вторичными текстовыми ссылками над sign in;
  30-секундный монотонный cooldown сохранён без сброса при смене языка.
- Android 0.5.0/code5 → 0.6.0/code6. Контракты и приёмка:
  [docs/android-language-ui.md](docs/android-language-ui.md); SHA/run/artifacts — в task PR.

### Android — 0.5.0 / Windows и backend unchanged

- Подключены profile/devices/messages/subscription/support API и мобильная навигация.
- Добавлены ACK id+revision, обновление данных после мутаций, ciphertext journal для
  immutable support/payment retries, восстановление receipt и защита смены аккаунта.
- Поддержка отправляет diagnostics:null и выбранные через SAF ограниченные изображения.
- DISABLED/SANDBOX запрещают платёжные действия в UI/data layer; LIVE требует capabilities
  и повторной проверки price revision. Реальный provider не подключался.
- Android 0.4.0/code4 → 0.5.0/code5; ручной OTP-вход 0.4.0 подтверждён владельцем.
  Контракты, ограничения и CI evidence: docs/android-account-api.md и task PR.


### Android — 0.4.0 / Windows и backend unchanged

- Подключены существующие OTP/refresh/me/logout API с ANDROID installation identity.
- Refresh credentials шифруются Android Keystore AES-GCM и сохраняются атомарно без backup;
  bearer/OTP остаются в памяти. Добавлены restore, single-flight rotation, expiry/revoke,
  честный offline logout и защита от повторного refresh после неоднозначного сбоя.
- Обычный launcher использует auth-only live shell; offline fixture UI изолирован в
  instrumentation. VPN/платежи и остальные live-интеграции недоступны.
- Android 0.3.0/code3 → 0.4.0/code4. JVM/HTTP, Keystore и native UI проверки описаны в
  docs/android-auth-session.md; фактические SHA/run/artifacts — в task PR.


### Android — 0.3.0 / Windows и backend unchanged

- Перенесены auth/OTP, Home/countries/details/location, settings/devices/subscription,
  четыре payment routes, account messages и support receipt на debug-only ScreenSource.
- Добавлены confirmation/Back, loading/error/retry/empty/stale и fault scenarios.
  Сохранены Rubik/палитра/logo/mobile insets и прежняя design acceptance.
- Постоянный TEST DATA / NO VPN TUNNEL; имитация не создаёт туннель, не отправляет
  OTP/support, не списывает деньги. Release не содержит FixtureSource.
- Android 0.2.0/code2 → 0.3.0/code3. English base; шесть языков остаются отдельной
  задачей 0.4.0. CI и ограничения: docs/android-fixture-screens.md; evidence — task PR.

### Android — 0.2.0 / Windows 0.12.0 и backend 0.10.0 unchanged

- Перенесены брендовые поверхности, исходные logo contours, Rubik variable weights,
  карточки, кнопки enabled/disabled/loading, focus/error text fields и телефонная навигация.
- Home/Settings/About адаптированы под вертикальную прокрутку, крупный шрифт и insets.
  Добавлена локальная форма поддержки с email validation/recreation, без реальной отправки.
- CI проверяет текущий APK на API 26/35/36: 320/360/412dp, landscape, fontScale до 2.0,
  настоящую IME, system bars, native PNG/source identity. См. docs/android-design.md.
- Версия 0.2.0/code 2; API/VPN/payments и шесть языков ещё не подключены.
  Точные SHA/run/attempt, статусы и PNG — в task PR; следующая локализация отдельно.

### Android — план под Windows 0.12.0, version unchanged

- Эталон переноса обновлён до develop 78f5999 после Windows PR #21; история
  Windows 0.12.0 и начального Android 0.1.0 сохранена без изменения runtime.
- Добавлены требования шести языков, мобильного размещения выбора, English/RU
  auto-origin, хранения и проверки locale/гео/VPN races; локализация ещё не реализована.
- Обновлены архитектура, этапы, ближайший промпт и handoff PR #20.
- Android 0.1.0/code 1, Windows 0.12.0 и backend 0.10.0/schema 0026 unchanged.

### Android — 0.1.0 (первая версия) / Windows и Backend unchanged

- Создан отдельный Kotlin/Jetpack Compose проект: Gradle wrapper, pinned toolchain,
  debug APK, minSdk 26 / targetSdk 36, собственные versionName 0.1.0 / versionCode 1.
- Добавлены главная, настройки и «о приложении», Back/сохранение вкладки,
  брендовая палитра, Rubik с OFL и исходные контуры логотипа Windows.
- GitHub Actions собирает текущий checkout с source SHA и APK SHA-256; тот же APK
  проверяется на API 26/35/36, с instrumented navigation tests и native screenshots.
- API, VPN runtime и платежи ещё недоступны; никаких реальных подключений,
  списаний и новых backend изменений. Результаты и артефакты — в task PR.

### Android — архитектура и план переноса, version unchanged

- Зафиксирован аудит Windows 0.11.1 на develop 69ab8d1: карта экранов/API,
  дизайн-токены, Kotlin/Compose слои и замена Windows native-зависимостей.
- Разделены протокольный каталог и реальные runtime capabilities; первый
  VPN-этап — WireGuard IPv4 full tunnel, остальные профили gated/disabled.
- Документированы support diagnostics WINDOWS-only с безопасным null для Android,
  legacy NATIVE policy, first-candidate/no-fallback и service ownership GoBackend.
- Добавлены этапы переноса, критерии приёмки и ссылка из apps/android/README.md.
- Только документация: Android APK/проект ещё не создан; backend 0.10.0,
  Windows 0.11.1, schema 0026 не меняются. Новая сборка/deploy не выполнялись.

### Windows — 0.12.0 / Backend — 0.10.0 unchanged

- Добавлены English, Russian, Chinese, Spanish, German и French для всего UI,
  ошибок, диалогов и accessibility labels, с сохранением технических английских имён.
- Выбор флага и English/native названий внизу sidebar, клавиатура и сохранение выбора.
- По умолчанию English; подтверждённая исходная локация RU до VPN выбирает Russian.
  Ручной выбор имеет приоритет, ответы после смены VPN-состояния игнорируются.
- Даты/цены/страны учитывают язык; формы, auth и VPN сохраняют состояние.
- Native UI review снимает текущую сборку на шести языках. Результаты — в task PR;
  реальные провайдеры и backend не меняются. См. docs/windows-localization.md.

### Документация — актуальный статус на 2026-10-19

- Исправлены устаревшие описания backend-каркаса, отсутствующей аутентификации,
  неподключённого Home flow и якобы отсутствующего development deployment.
- Добавлена единая сводка реализованных модулей, фактической приёмки, source/build
  SHA, runtime/deploy и backlog. Исторические handoff-записи явно отделены от неё.
- OTP остаётся на паузе; inbox поддержки и полный Windows VPN data plane не
  объявляются проверенными. Реальный платёжный провайдер остаётся отдельной задачей #18.
- Version unchanged: Windows 0.11.1, backend 0.10.0, schema 0026; только документация.

### Windows — 0.11.1 / Backend — 0.10.0 unchanged

- Fixed: Home refreshes `/me` on entry so changed device counts and plans do not
  remain hidden behind the restored profile cache. Long runtime versions stay
  inside the sidebar with ellipsis and the complete tooltip.
  Public location uses a fixed native HTTPS request because the generic plugin's
  automatic Origin header is rejected by the free provider. TLS and general HTTP
  protections remain enabled.
- Added native Windows acceptance against actual development HTTPS, disposable
  identities, refresh rotation/logout, optional email OTP with manual encrypted handoff,
  and isolated sandbox lifecycle/race/restart checks. No live payment provider.
  Owner-assisted OTP is paused by request and explicitly reported as unverified.
- Evidence and limits: docs/windows-development-acceptance.md and task PR #17.

### Backend — 0.10.0 / Windows — 0.11.0

- Added: server-declared capabilities for MIR, BANK_CARD, ALIPAY_WECHAT and CRYPTO,
  including available currencies, recurring currencies and explicit provider mode.
- Backend enforces the matrix at admission and freezes accepted recurring terms;
  capability changes invalidate stale revisions.
- Windows displays unsupported routes disabled, describes recurring/one-time terms,
  and permits mutation/browser checkout only for explicit LIVE capabilities.
- Disabled, sandbox and legacy responses remain read-only. No real provider,
  charge or binding configured. Database schema unchanged (0026).

### Backend — 0.9.0 (Windows unchanged: 0.10.0)

- Added: persistent simulated mandate lifecycle (migration 0026), including recovery
  from saved 0.8.0 receipts. Sandbox renewals retain the active authority; method
  replacement revokes the old authority and cancellation stops recurring payments.
- Hardened: contradictory method-change/revocation confirmations and failed receipts
  containing mandate mutations stay PENDING for reconciliation.
- Tested: exact calendar-month extension once, preserved paid dates/contracts,
  cancellation/mandate state, failures/timeouts, rollback, notification replay and races.
- Real charges/bindings remain disabled; the sandbox is opt-in in development/test.

### Backend — 0.8.0 (Windows unchanged: 0.10.0)

- Added: opt-in development/test payment adapter with PostgreSQL receipts and
  deduplicated notifications (migration 0025). Default billing remains disabled.
- Added: server-only CLI for delayed success, decline and payment cancellation;
  conflicting events cannot replace terminal receipts or settle a payment twice.
- Added: tests for subscription/renewal/cancellation, notification races, lost
  responses, settlement rollback and recovery with fresh database pools.
- No payment SDK, external payment service, credentials, public simulation controls
  or real charges. Enable only on an isolated development database; see
  docs/billing-sandbox.md and the task PR for actual validation status.

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
