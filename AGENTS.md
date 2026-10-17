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
- Free users receive 15-minute Autopilot VPN sessions.
- After a free session expires, the user must complete a rewarded-ad flow before starting another 15-minute session.
- Premium users have no ads and no 15-minute session limit.
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
- Текущий backend CI использует legacy `dev-<SHA>`. Целевой SemVer runtime-формат из документа не считать внедрённым до отдельного изменения и проверки deploy/rollback.
- Для каждой продуктовой задачи обновлять CHANGELOG под Unreleased и handoff: версии до/после, совместимость, проверенный product SHA, реальный build SHA/run/attempt, артефакты и backend follow-up. Не заявлять проверку нового кода по старой сборке; различать PR head и временный merge SHA.
- Для Windows UI обязательны соответствующие проверки и реальные native-скриншоты. Для docs-only проверять ссылки, согласованность правил и diff; нативную сборку из-за текста не повторять.
- После проверок выполнять commit и push, если владелец не запретил, и обновлять PR. Merge, release-теги/публикация и production deploy — отдельные действия, требующие соответствующего поручения; учитывать существующий автоматический development-deploy.
- Переход Windows на 0.2.0 применён в задаче полировки UI от 2026-10-16; backend остаётся 0.1.0 в исходных манифестах. Правки названия и экрана входа от 2026-10-17 повышают Windows до 0.2.1. Домашний экран переработан в 0.3.0 (2026-10-17); см. docs/home-screen.md. Блок режимов трафика и сведения о соединении добавлены в 0.4.0; выборочная маршрутизация отложена по решению владельца. Удаление двух подписей правого блока повышает Windows до 0.4.1. Пункт подписки с пустым экраном добавлен в Windows 0.4.2. Порядок пунктов и подписи настроек уточнены в Windows 0.4.3. Подписи подписки/выхода уточнены в Windows 0.4.4. Windows 0.5.0 добавляет экран подписки и клиентский billing-контракт; backend и провайдер отложены по решению владельца, см. docs/subscriptions-ui.md. Windows 0.6.0 добавляет выбор платёжного маршрута перед оформлением/продлением. Windows 0.6.1 уточняет экран устройств: ID, дата добавления и необязательный last_login_at, см. docs/devices-ui.md. Windows 0.7.0 обновляет «о приложении» и добавляет UI поддержки, см. docs/support-ui.md; доставка писем отложена, отправка без backend недоступна. Windows 0.8.0 добавляет JSON-сообщения аккаунту после авторизации и контракт общих backend-подтверждений, см. docs/account-messages.md; backend доставки пока не реализован. Следующую самостоятельную продуктовую задачу Windows версионировать от 0.8.0 по docs/versioning.md; повторные исправления/CI текущей задачи номер не повышают.

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
