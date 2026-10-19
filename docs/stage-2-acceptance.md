# Stage 2 acceptance: passwordless authentication

Актуальный срез — [project-status.md](project-status.md): backend **0.10.0**,
Windows **0.11.1**, schema **0026**. Это инструкция ручной приёмки, не отчёт о её
успехе. По решению владельца реальный OTP-прогон Windows на паузе; автоматически
письмо не запрашивается. Возобновлять только при согласованной готовности читать
почту, через отдельный opt-in из [Windows acceptance](windows-development-acceptance.md).

Этот runbook проверяет цепочку Windows → OTP → Timeweb → PostgreSQL/Valkey → session
restoration → devices → logout. Не вставляйте SMTP-пароль, OTP, access token или refresh token в
командную строку, issue, отчёт или лог. Реальную доставку письма можно считать успешной только
после проверки inbox получателя.

## 1. Автоматические проверки Backend

Из корня репозитория в PowerShell запустите PostgreSQL и Valkey из существующего Compose:

```powershell
docker compose -f infra/docker/compose.yaml up -d postgres valkey
docker compose -f infra/docker/compose.yaml ps
```

Настройте только текущий PowerShell-процесс и примените миграции:

```powershell
$env:POSTGRES_URL = "postgresql+asyncpg://prettylisa:local-development-only@127.0.0.1:5432/prettylisa"
$env:VALKEY_URL = "redis://127.0.0.1:6379/0"
$env:OTP_HMAC_SECRET = "local-stage2-acceptance-secret-at-least-32-characters"
$env:RUN_INTEGRATION_TESTS = "1"

Push-Location backend
..\.tools\bin\uv.exe run alembic heads
..\.tools\bin\uv.exe run alembic history --verbose
..\.tools\bin\uv.exe run alembic upgrade head
..\.tools\bin\uv.exe run alembic current
..\.tools\bin\uv.exe run alembic check
..\.tools\bin\uv.exe run ruff format --check .
..\.tools\bin\uv.exe run ruff check .
..\.tools\bin\uv.exe run mypy
..\.tools\bin\uv.exe run pytest -m "not integration and not docker" -q
..\.tools\bin\uv.exe run pytest -m integration -q
Pop-Location
```

Ключевые группы можно повторить отдельно:

```powershell
Push-Location backend
..\.tools\bin\uv.exe run pytest tests/test_otp_integration.py tests/test_auth_request_otp_integration.py -q
..\.tools\bin\uv.exe run pytest tests/test_auth_verify_otp_integration.py -q
..\.tools\bin\uv.exe run pytest tests/test_authenticated_sessions_integration.py -q
..\.tools\bin\uv.exe run pytest tests/test_device_management_integration.py tests/test_devices_integration.py -q
..\.tools\bin\uv.exe run pytest tests/test_stage2_acceptance_integration.py -q
Pop-Location
```

Они проверяют invalid/expired/replayed OTP, cooldown и email/IP limits, атомарное потребление OTP,
создание FREE-подписки, отсутствие duplicate User/Device, конкурентный лимит 5 устройств,
восстановление места после отзыва, refresh rotation/replay, logout и revoked sessions.

## 2. Проверка PostgreSQL и Valkey

Исторический Stage 2 использовал `0008_auth_session_device_fk`; текущий migration
head — `0026_sandbox_mandates`. Полная актуальная приёмка:
[Windows с development](windows-development-acceptance.md). Просмотрите таблицы и ключевые
колонки без вывода чувствительных значений:

```powershell
docker compose -f infra/docker/compose.yaml exec postgres psql -U prettylisa -d prettylisa -c "SELECT version_num FROM alembic_version;"
docker compose -f infra/docker/compose.yaml exec postgres psql -U prettylisa -d prettylisa -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
docker compose -f infra/docker/compose.yaml exec postgres psql -U prettylisa -d prettylisa -c "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns WHERE table_schema = 'public' AND table_name IN ('users','subscriptions','devices','auth_sessions','product_events') ORDER BY table_name, ordinal_position;"
docker compose -f infra/docker/compose.yaml exec postgres psql -U prettylisa -d prettylisa -c "SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY conrelid::regclass::text, conname;"
docker compose -f infra/docker/compose.yaml exec postgres psql -U prettylisa -d prettylisa -c "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname;"
```

Не выбирайте `refresh_token_hash` в smoke-отчёт. Его SHA-256 длина и отсутствие plaintext
проверяются тестами. После успешного нового login ожидается одна нормализованная User-запись, одна
ACTIVE/FREE Subscription, один ACTIVE Device для installation ID и одна активная AuthSession.

Valkey предназначен только для временных OTP/cooldown/rate-limit записей. Следующая dev-команда
печатает только имена ключей и оставшийся TTL, но не значения:

```powershell
docker compose -f infra/docker/compose.yaml exec valkey valkey-cli --raw EVAL "local ks=redis.call('KEYS','*'); table.sort(ks); for _,k in ipairs(ks) do redis.log(redis.LOG_NOTICE,k..' ttl='..redis.call('TTL',k)) end; return #ks" 0
docker compose -f infra/docker/compose.yaml logs --since 1m valkey
```

Допустимы только ключи вида `otp:challenge:<HMAC>`, `otp:cooldown:<HMAC>`,
`otp:rate:email:<HMAC>` и `otp:rate:ip:<HMAC>`, каждый с положительным TTL. После успешной
проверки `otp:challenge:*` удаляется. Постоянные User, Device, Subscription и AuthSession в Valkey
появляться не должны.

## 3. Windows и native checks

```powershell
Push-Location apps/windows
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm native:format
pnpm native:lint
pnpm native:test
pnpm tauri build --no-bundle
Pop-Location
```

## 4. Реальная Timeweb-доставка и Windows E2E

Реальный Backend URL клиента должен быть HTTPS. Проверьте без credentials:

```powershell
$apiBase = "https://api.prettylisavpn.com"
if (([Uri]$apiBase).Scheme -ne "https") { throw "Real authentication traffic must use HTTPS" }
curl.exe --proto "=https" --tlsv1.2 --silent --show-error --fail-with-body "$apiBase/health"
curl.exe --proto "=https" --tlsv1.2 --silent --show-error --fail-with-body "$apiBase/ready"
```

Для полного Windows smoke создайте локальную конфигурацию без секретов и запустите Tauri:

```powershell
if (-not (Test-Path apps/windows/.env.local)) { Copy-Item apps/windows/.env.example apps/windows/.env.local }
Select-String -Path apps/windows/.env.local -Pattern '^VITE_BACKEND_BASE_URL=https://api\.prettylisavpn\.com$'
Push-Location apps/windows
pnpm tauri dev
```

В окне клиента:

1. Введите тестовый email, inbox которого доступен проверяющему, и нажмите Continue.
2. Убедитесь, что письмо пришло от `PrettyLisaVPN <auth@prettylisavpn.com>`, содержит тему
   `Your PrettyLisaVPN verification code`, plain-text/HTML содержимое и срок действия. Не копируйте
   OTP в отчёт.
3. Нажмите resend до окончания cooldown: новый запрос не должен уйти. После cooldown resend должен
   снова показать generic success без раскрытия существования аккаунта.
4. Введите OTP только в клиенте. Проверьте Home: email, FREE plan, active device count и отключённый
   Stage 3 CONNECT.
5. Полностью закройте приложение, снова выполните `pnpm tauri dev`: refresh credential должен
   ротироваться через Windows Credential Manager, `/me` должен открыть Home без нового OTP.
6. Откройте Devices, проверьте current-device indicator и подтверждение отзыва другого устройства.
7. Нажмите Logout. Следующий запуск должен открыть Email login.

Для независимого SMTP adapter smoke с безопасным вводом пароля:

```powershell
Push-Location backend
$mailbox = Get-Credential -UserName "auth@prettylisavpn.com" -Message "Timeweb mailbox password"
$recipient = Read-Host "Test recipient email"
$env:EMAIL_SMTP_PASSWORD = $mailbox.GetNetworkCredential().Password
$env:EMAIL_SMOKE_RECIPIENT = $recipient
$env:RUN_EMAIL_INTEGRATION_TEST = "1"
..\.tools\bin\uv.exe run pytest tests/test_email_provider_integration.py -q
Remove-Item Env:EMAIL_SMTP_PASSWORD, Env:EMAIL_SMOKE_RECIPIENT, Env:RUN_EMAIL_INTEGRATION_TEST
$mailbox = $null
$recipient = $null
Pop-Location
```

Успешный SMTP return подтверждает приём сообщения сервером Timeweb, но delivery считается
подтверждённой только после появления письма в inbox.

## 5. Temporary outage

Не удаляйте credential из Windows Credential Manager для этой проверки. После успешного login и
до Logout запустите клиент один раз с недоступным HTTPS origin, затем верните реальный origin:

```powershell
Push-Location apps/windows
$env:VITE_BACKEND_BASE_URL = "https://127.0.0.1:1"
pnpm tauri dev
Remove-Item Env:VITE_BACKEND_BASE_URL
pnpm tauri dev
Pop-Location
```

При первом запуске клиент должен показать отдельную сетевую ошибку и сохранить credential. После
возврата реального origin Retry или следующий запуск должен восстановить сессию. Нельзя
останавливать публичный shared development Backend ради этой проверки.

## 6. Очистка локального окружения

```powershell
Remove-Item Env:POSTGRES_URL, Env:VALKEY_URL, Env:OTP_HMAC_SECRET, Env:RUN_INTEGRATION_TESTS
docker compose -f infra/docker/compose.yaml down
```

Команда `down` сохраняет volume PostgreSQL. Удалять volume для acceptance-проверки не требуется.

