# Текущее состояние PrettyLisaVPN

Срез на **2026-10-19**, исходный `develop`:
`090dd4117fb829f6faad1853cba5ae577c8837aa`.
Windows **0.11.1**, backend **0.10.0**, последняя миграция **0026**
(`0026_sandbox_mandates`). Обновление этой документации — version unchanged.
Срез описывает реализацию и зафиксированные проверки, а не непрерывную доступность
внешних сервисов или готовность всего продукта к production.

## Начальный Android-клиент — 0.1.0

Создан Kotlin/Jetpack Compose каркас в [apps/android](../apps/android/README.md):
независимая версия 0.1.0/code 1, Gradle, debug APK, три вкладки, тема/Rubik/логотип.
Workflow Android debug проверяет APK текущего checkout на эмуляторах API 26/35;
точные результаты, SHA/run/attempt и артефакты публикуются в task PR после CI.
Это не подтверждение API/VPN-приёмки: сетевых интеграций, VPN runtime и платежей
в Android пока нет. Windows/backend/schema не менялись.

## Что реализовано

| Область | Реализация и ограничения |
| --- | --- |
| Аккаунт и вход | Email OTP через заменяемый EmailProvider/Timeweb SMTP, rate limits, проверка кода, access token, сохранённые refresh-сессии с rotation, logout, `/me`. |
| Устройства | Регистрация, лимит пяти активных устройств, список и отзыв доступа с отзывом auth-сессий и durable VPN cleanup. `last_login_at` меняется при успешном OTP-входе. |
| Права подписки | Единые права для `/me`, VPN и сообщений. Free без рекламы: один час в сутки UTC на аккаунт. Premium и ручной Platinum без суточного ограничения в пределах оплаченного срока; отмена автопродления сохраняет оплаченный срок. |
| VPN control plane | Выбор AUTO/страны и подходящего узла, capacity/health policy, country quality, создание и завершение сессии, выдача конфигурации, Node Agent, восстановление и очистка peers. Это не доказательство реального клиентского трафика. |
| Подписки и платежи | Серверный каталог RUB/USD, immutable quotes, ревизия цены, сохранённая идемпотентность, POST/GET operations, фоновая сверка и восстановление, продление, смена способа и отмена через provider port. Реального адаптера нет. |
| Платёжные маршруты | MIR, BANK_CARD, ALIPAY_WECHAT и CRYPTO описаны в контракте; доступные валюты и recurring задаёт backend. Наличие маршрута в модели не означает поддержку реальным платёжным сервисом. |
| Тестовый платёжный адаптер | Явно включаемый sandbox только для development/test, сохранённые receipts/уведомления, проверки гонок, повторов, сбоев и восстановления. По умолчанию `BILLING_PROVIDER=disabled`; Windows с SANDBOX остаётся read-only. |
| Сообщения аккаунту | JSON v1 GET/ACK, подтверждения на уровне аккаунта и ревизии, серверная CLI-публикация. Наличие API не доказывает доставку конкретного опубликованного сообщения на несколько устройств. |
| Поддержка | Защищённые POST/status API, вложения, идемпотентность, сохраняемая очередь и повторные попытки SMTP-доставки. Inbox delivery требует отдельной проверки. |
| Продуктовые события | События OTP, входа, refresh/logout и устройств с allowlist свойств. Полной аналитики VPN/покупок/воронок и отчётов пока нет. |
| Windows | Tauri/React/Rust, реальные API аккаунта/устройств/сообщений/поддержки/billing, native credential storage, Home connect/disconnect flow, WireGuardNT и проверка соединения. Установщик, подпись и автообновления не подготовлены. Остальные платформы не проходили эту приёмку. |
| Развёртывание | Docker, PostgreSQL/Valkey, Caddy HTTPS, Alembic, development CI/deploy с точной runtime identity и сохранением прежней конфигурации/образа. Ansible содержит playbooks VPN-узлов и агентов; Terraform и общий monitoring остаются заготовками. |

## Что действительно проверено

- [PR #17](https://github.com/romankenig/PrettyLisaVPN/pull/17) слит коммитом
  `8e9ac69b9bea5ec7ac1c3e35f7eab47e85e232f7`. Проверенный Windows source HEAD:
  `4452327e6904a1cbf520f3088f908f51e453e00d`.
- [Native Windows → development HTTPS, run 39141375774](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39141375774),
  attempt 1: девять API endpoint вернули 200, восемь native-сценариев прошли.
  Проверены восстановление/rotation сессии временного аккаунта, устройства и отзыв,
  обновление Home 2→1, геолокация, read-only RUB/USD billing, runtime version,
  форма поддержки и logout. Использован временный серверный аккаунт, не OTP-вход.
  Также прошли 339 frontend tests, 2 Rust tests и 65 изолированных sandbox scenarios.
  Снимки окна и JSON-отчёт доступны в артефактах run и описании PR.
- [Backend deployment, run 39200525561](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39200525561),
  attempt 1: source `090dd4117fb829f6faad1853cba5ae577c8837aa`, runtime
  `0.10.0-dev.39200525561+g090dd4117fb829f6faad1853cba5ae577c8837aa`.
  Выкладка 2026-10-19 прошла health, readiness и точное сравнение `/version`.
  CI: 504 unit tests, 177 integration tests (1 skipped), 8 Docker tests.
  Это development environment, несмотря на публичный адрес
  `https://api.prettylisavpn.com`.
- Между проверенным Windows HEAD и deployed HEAD изменился только
  `infra/deployment/README.md`; исходники клиента совпадают. Backend deployment
  не устанавливает Windows-приложение на пользовательские компьютеры.

## Реализовано, но приёмка не завершена

1. **Настоящий OTP-вход Windows.** Поставлен владельцем на паузу; SMTP authentication
   и восстановление seed-сессии не считаются подтверждённым OTP-входом. Автоматический
   прогон не запрашивает письмо; ручной workflow opt-in требует согласованной готовности
   владельца и свежего кода. Коды не сохраняются в git/logs/artifacts.
2. **Доставка поддержки в inbox.** Проверена форма и SMTP authentication, но в этой
   приёмке обращение не отправлялось и получение письма не подтверждено.
3. **Полный VPN data plane Windows.** Нужны проверенный официальный `wireguard.dll`,
   elevated Windows и фактические проверки трафика, DNS, egress, отключения и удаления
   peer. GET стран, health узла и synthetic UI screenshots этого не заменяют.

## Оставшиеся работы

1. **Реальный платёжный провайдер** — [issue #18](https://github.com/romankenig/PrettyLisaVPN/issues/18):
   выбор сервиса, реальные capabilities/валюты/recurring, live adapter, credentials,
   защищённые уведомления и сверка неопределённых внешних результатов. Сначала
   официальная тестовая среда поставщика. LIVE, реальные списания и привязки требуют
   отдельного поручения владельца; текущая документация их не разрешает.
2. **Администрирование.** Нет единого административного API/панели; есть отдельные
   серверные CLI. Интерфейс операторов, роли и аудит операций требуют отдельного объёма работ.
3. **Расширенная аналитика.** События VPN/покупок, конверсии, удержание и отчёты;
   без истории посещений, DNS-запросов и содержимого пользовательского трафика.
4. **Эксплуатационный мониторинг.** Общие метрики, дашборды и алерты API, workers,
   SMTP и платежей. Существующие `/health`, `/ready` и Node Agent monitoring сохраняются.
5. **Резервирование и восстановление.** Подтвердить политику backup/retention и
   провести восстановление PostgreSQL в изолированной среде. По текущим доказательствам
   нельзя заключить ни наличие, ни отсутствие backup у инфраструктурного провайдера.
6. **Production-приёмка.** Отдельно подтвердить боевую конфигурацию, выпуск,
   эксплуатационные процедуры и recovery. Development deploy и сохранённый старый
   образ сами по себе не доказывают успешный production rollout или живой rollback.

Последние пункты — backlog развития и эксплуатации, а не утверждение об отсутствии
уже реализованных API и не новый обязательный контракт Windows MVP.

## Android: начало переноса — проектирование

От Windows 0.11.1 на develop `69ab8d1d3d3c5680fc72bb23980776242606a104`
подготовлены [архитектура Kotlin/Compose](android-architecture.md) и
[план переноса](android-porting-plan.md): экраны, API, мобильные токены,
native ports, VPN runtime/transport gates и этапы приёмки. Android-проект и APK
ещё не реализованы; version unchanged, backend/Windows не меняются.
Support diagnostics Android ограничены текущим WINDOWS-only schema (разрешён
`diagnostics=null`); OpenVPN/MASQUE и legacy wrappers не объявляются рабочими
на Android по наличию Windows descriptors.

## Подробности

- [Разработка Backend](../backend/README.md), [Windows](../apps/windows/README.md).
- [Права подписки](subscription-entitlements.md), [billing-контракт](subscriptions-ui.md),
  [sandbox](billing-sandbox.md), [сообщения](account-messages.md), [поддержка](support-ui.md).
- [Приёмка Windows/development](windows-development-acceptance.md),
  [OTP runbook](stage-2-acceptance.md), [WireGuard runtime](windows-wireguard-runtime.md).
- [Текущий handoff и журнал](backend-cloud-handoff.md),
  [development deployment](../infra/deployment/README.md).
