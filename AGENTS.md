# PrettyLisaVPN Repository Guidelines

## Product Context

PrettyLisaVPN is a multi-platform commercial VPN service.

Supported client platforms:

- Windows
- macOS
- Linux
- Android
- iOS
- Android TV
- Chrome Extension

The Chrome Extension is browser-only. It must use a proxy-based implementation rather than a system-wide WireGuard tunnel.

## Product Requirements

- Authentication is passwordless and uses email OTPs.
- Free users receive one account-wide hour per UTC day, without ads; AUTO/country selection uses free-only nodes.
- Free sessions may use the remaining daily hour and end at UTC midnight; unused time returns after confirmed peer removal.
- Premium users have no ads or daily/session time cap within their paid period. Manually assigned Platinum has exactly the same capabilities.
- Premium users can explicitly select a VPN server country.
- Split tunneling must eventually support both whitelist and blacklist modes. Do not implement this future capability unless the current task requires it.
- Each account may have up to five active devices.
- Payments and recurring subscriptions use external payment providers such as ЮКасса.
- Support product and acquisition analytics without collecting or logging users' browsing history.

## Architecture

- Start the Backend as a modular monolith, not microservices.
- Use Python 3.13 and FastAPI.
- PostgreSQL is the source of truth for persistent business data.
- Use Redis only for ephemeral concerns such as OTPs, caching, locks, rate limits, and short-lived sessions.
- Use SQLAlchemy 2.x for persistence.
- Use Alembic for database migrations.
- Use Pydantic v2 for API schemas and configuration.
- Integrate external services through ports/adapters or provider interfaces. Providers must be replaceable and mockable.
- Keep business logic out of HTTP controllers. Controllers should validate and translate transport concerns, then delegate to application/domain services.
- WireGuard is the primary system-wide VPN protocol.
- Keep the VPN control plane and VPN data plane separate.
- User VPN traffic must never pass through the Backend API.
- Manage infrastructure with Terraform and Ansible.
- Use Docker for local development and deployment packaging.
- Avoid Kubernetes for the MVP unless explicitly requested.
- Prefer simple, concrete solutions over speculative abstractions.
- Do not implement future roadmap items unless required by the current task.

## Data, Privacy, and Security

- Do not collect or log browsing history.
- Never log browsing destinations, DNS queries, URLs, or packet contents.
- Never log OTP values in production.
- Never log WireGuard private keys.
- Never commit secrets. Keep `.env.example` synchronized with required configuration using safe placeholder values.
- Never store raw payment-card details. Payment data must be handled by external payment providers.
- Use structured logging.
- Use UTC timestamps internally.
- Use UUIDs for externally exposed IDs unless there is a strong documented reason not to.
- API errors must expose stable, machine-readable error codes.

## Engineering Rules

- Inspect the repository and its existing conventions before editing.
- Do not rewrite or reformat unrelated code.
- Preserve backwards compatibility unless the task explicitly requires a breaking change.
- Reuse existing tooling and dependencies when they already solve the requirement.
- For client UI work, follow the shared logo and color rules in `docs/design-system.md`.
- При изменении экранов, popup, маршрутов, auth guard и внешних переходов обновлять `docs/windows-navigation.md`; различать реализованные UI-переходы и ожидающую backend интеграцию.
- Always write the product name exactly as `PrettyLisaVPN`, including rendered UI and error messages. Preserve this casing when applying lowercase typography.
- Every database schema change requires an Alembic migration.
- Every new endpoint requires tests.
- Every business rule requires unit tests.
- Add integration tests when behavior crosses module or infrastructure boundaries.
- External providers must be mockable in tests.
- Run the relevant formatting, linting, type-checking, and test commands before finishing.
- After completing and verifying changes, commit them and push the current branch to `origin` so the remote repository stays synchronized, unless the user explicitly says not to push.

## Версии и дальнейшие изменения

- Следовать [docs/versioning.md](docs/versioning.md); это основной документ о версиях, сборках и выпуске. История поставляемых изменений — [CHANGELOG.md](CHANGELOG.md).
- Версии клиентов по платформам и backend независимы: `MAJOR.MINOR.PATCH`. В Windows одна версия охватывает React, Rust/native и упаковку.
- Исправления/небольшие визуальные правки и внутренние изменения поставляемого кода — PATCH; новые возможности/существенный UI — MINOR; несовместимые изменения после 1.0 — MAJOR. До 1.0 несовместимые изменения повышают MINOR и требуют BREAKING-записи с планом перехода.
- Повышать версию один раз на логическую продуктовую задачу, не на каждый commit/CI run. Следующая самостоятельная задача получает следующий номер, даже в том же PR. Только docs/tests/CI без изменения поставляемого приложения — без bump.
- До реализации назвать затронутые компоненты, исходную/целевую версии и основание повышения либо `version unchanged`. Менять версии только затронутых компонентов.
- Windows: основной источник `apps/windows/package.json`; синхронно сверять `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, собственную запись `src-tauri/Cargo.lock`. Backend: основной источник `backend/pyproject.toml`; согласовать локальный default в `backend/src/prettylisavpn/config.py` и примеры окружения.
- Backend UI-версия берётся только из фактического GET /version; при недоступности — «недоступна». Не считать равенство frontend/backend номеров признаком API-совместимости.
- Backend CI формирует SemVer runtime из pyproject через `infra/deployment/runtime_version.py`; образы и каталоги различаются по SHA/run/attempt. Наличие реализации не доказывает реальный deploy/rollback: см. `docs/backend-cloud-handoff.md`. Исторические legacy `dev-<SHA>` не переименовывать.
- Для каждой продуктовой задачи обновлять CHANGELOG под Unreleased и handoff: версии до/после, совместимость, проверенный product SHA, реальный build SHA/run/attempt, артефакты и backend follow-up. Не заявлять проверку нового кода по старой сборке; различать PR head и временный merge SHA.
- Для Windows UI обязательны соответствующие проверки и реальные native-скриншоты. Для docs-only проверять ссылки, согласованность правил и diff; нативную сборку из-за текста не повторять.
- После проверок выполнять commit и push, если владелец не запретил, и обновлять PR. Merge, release-теги/публикация и production deploy — отдельные действия, требующие соответствующего поручения; учитывать существующий автоматический development-deploy.
- Переход Windows на 0.2.0 применён в задаче полировки UI от 2026-10-16; backend остаётся 0.1.0 в исходных манифестах. Правки названия и экрана входа от 2026-10-17 повышают Windows до 0.2.1. Домашний экран переработан в 0.3.0 (2026-10-17); см. docs/home-screen.md. Блок режимов трафика и сведения о соединении добавлены в 0.4.0; выборочная маршрутизация отложена по решению владельца. Удаление двух подписей правого блока повышает Windows до 0.4.1. Пункт подписки с пустым экраном добавлен в Windows 0.4.2. Порядок пунктов и подписи настроек уточнены в Windows 0.4.3. Подписи подписки/выхода уточнены в Windows 0.4.4. Windows 0.5.0 добавляет экран подписки и клиентский billing-контракт; backend и провайдер отложены по решению владельца, см. docs/subscriptions-ui.md. Windows 0.6.0 добавляет выбор платёжного маршрута перед оформлением/продлением. Windows 0.6.1 уточняет экран устройств: ID, дата добавления и необязательный last_login_at, см. docs/devices-ui.md. Windows 0.7.0 обновляет «о приложении» и добавляет UI поддержки, см. docs/support-ui.md; доставка писем отложена, отправка без backend недоступна. Windows 0.8.0 добавляет JSON-сообщения аккаунту после авторизации и контракт общих backend-подтверждений, см. docs/account-messages.md; backend доставки пока не реализован. Следующую самостоятельную продуктовую задачу Windows версионировать от 0.9.0 по docs/versioning.md; повторные исправления/CI текущей задачи номер не повышают.

Backend devices task: source version 0.2.0 adds migration 0018, real OTP-only
last_login_at and durable VPN cleanup on device revocation. Windows remains 0.8.0.
See docs/devices-ui.md; task PR records actual validation and deployment status.

## Task Workflow

For every coding task:

1. Inspect the relevant files and existing conventions.
2. Briefly state the implementation plan.
3. Implement the smallest coherent solution.
4. Add or update tests.
5. Run the relevant formatting, linting, type-checking, and test commands.
6. Review the diff for security, correctness, backwards compatibility, and unrelated changes.
7. Commit the verified changes and push the current branch to `origin`, unless explicitly instructed not to push.
8. Summarize:
   - files changed;
   - architecture decisions;
   - tests and checks run;
   - remaining risks or follow-up work.

## Полное завершение CI

- Перед итоговым «готово» проверить ВСЕ запуски последнего remote HEAD: pull_request, push, workflow_dispatch и вызываемые/reusable workflow. Проверки только одного Windows workflow или только PR-triggered списка недостаточно.
- Получать общий список Actions runs по repository/branch/head_sha с пагинацией, а не полагаться только на fetch_commit_workflow_runs: этот connector фильтрует события pull_request. Дополнительно сверять check-runs/check suites и commit statuses; пустой список statuses не означает успешный CI.
- Для каждого ожидаемого запуска дождаться status=completed и conclusion=success; затем проверить все jobs. Skipped допустим только при объяснимом условии (например, deploy-development вне develop). Failure, timed_out, action_required, неожиданно missing или cancelled для текущего HEAD не считать успехом.
- Старый cancelled допустим только как superseded-run прежнего commit; он не заменяет проверку текущего HEAD. Не скрывать ошибки отключением нужной проверки, continue-on-error или удалением истории запусков.
- После ЛЮБОГО последнего push, включая docs/handoff commit, снова проверить remote HEAD и все автоматически запущенные workflow. Не завершать задачу, пока они pending/in_progress. Итоговые ссылки и результаты можно обновлять в описании PR без нового commit, чтобы не создавать бесконечные повторные прогоны документацией.
- Источник бинарного артефакта обязан соответствовать проверяемым исходникам. Не скачивать фиксированный исторический exe для нового UI/capture-сценария. Windows window capture теперь вызывает общий Windows UI review через workflow_call и собирает текущий commit; обычные UI/script-изменения автоматически проверяет основной PR workflow.
- В итоговом отчёте указывать проверенный HEAD, названия всех workflow, конечные статусы и ссылки. Если полноценный обзор Actions недоступен, явно сообщить ограничение и не утверждать, что все проверки прошли.

Backend account messages task: source 0.3.0, migration 0019, shared JSON v1 GET/ACK
and closed server-only publication CLI. Read receipts belong to the account and
revision, not the device. Windows stays 0.8.0; Android/other clients require their
own contract adapter/UI. See docs/account-messages.md and the task PR for evidence.

Support task: backend 0.4.0, Windows 0.9.0, migration 0020. Connected private
POST/status API, account-scoped idempotency, app-helper SMTP, fixed help recipient,
durable retries and 30-day content retention. See docs/support-ui.md and task PR
for real evidence. Next independent task starts from these component versions.

Subscription access task: backend 0.5.0, migrations 0021/0022; Windows stays 0.9.0.
Free may select AUTO/country among free nodes (README clarification). Canceled
renewal preserves paid access through the exclusive paid deadline. Read
docs/subscription-entitlements.md before changing plans; Platinum is manual with Premium parity; Free is now one hour/day UTC with no ads.


Billing overview task: backend 0.6.0, Windows 0.10.0, migration 0023. Read
`docs/subscriptions-ui.md` before changing commercial pricing. Groups and scheduled
RUB/USD offers are PostgreSQL-owned; confirmed contract prices are immutable and
never backfilled from current offers. GET is implemented; provider/payment operations
remain disabled (actions=[]). Temporary prices were explicitly authorized by owner.


Billing operations task: backend 0.7.0, migration 0024; Windows unchanged 0.10.0.
POST/GET operations and durable recovery are implemented; live provider stays disabled.
Idempotency keys and immutable quotes belong to the account. Unknown provider outcomes
must stay PENDING and reuse the same provider operation UUID; never create a new charge
on timeout or idempotency-window expiry. Keep provider adapters for their pending rows.
Read docs/subscriptions-ui.md before changing settlement, contract prices or cancellation.

Development sandbox task: backend 0.8.0, migration 0025; Windows unchanged 0.10.0.
Read docs/billing-sandbox.md. BILLING_PROVIDER defaults to disabled; sandbox requires
exact development/test environment. Server-only notification CLI never charges money.
Keep provider receipts/event deduplication until pending operations are settled.

Subscription lifecycle task: backend 0.9.0, migration 0026; Windows unchanged 0.10.0.
Sandbox authority state is durable. Renewals retain active authorities; replacements
revoke the previous one. Preserve both paid dates for CHANGE_METHOD/CANCEL and
apply RENEW once per operation. Partial/contradictory external outcomes stay PENDING.

Route capabilities task: backend 0.10.0 / Windows 0.11.0, schema unchanged (0026).
Overview owns route currencies/recurring currencies and provider mode. Windows
requires explicit LIVE plus operations availability/actions; sandbox/legacy responses
stay read-only. Sandbox API tests remain isolated. Freeze accepted recurring terms.


Windows development acceptance task: Windows 0.11.1, backend unchanged 0.10.0.
Read docs/windows-development-acceptance.md. Direct HTTPS/native checks differ
from fixture replay. Disposable acceptance credentials and ephemeral OTP private
keys must never enter artifacts; manual OTP is encrypted for its single run.
Home refreshes /me on entry. Keep real payment integration a separate future task.
