# Разработка Backend

Backend — сервер управления PrettyLisaVPN на Python 3.13 и FastAPI. Это модульный монолит: настройки, подключения к PostgreSQL и Valkey, структурированные логи, служебные API и модуль пользователей. Пользователь хранится в PostgreSQL с нормализованным уникальным email, UUID, статусом и UTC-временем создания и изменения. HTTP-методов аутентификации пока нет. Каждое изменение схемы должно добавлять новую миграцию Alembic.

VPN-узлы выбираются только внутри Backend. FREE и PREMIUM передают режим AUTO или страну, но никогда не получают список отдельных узлов. Общая eligibility policy требует `ACTIVE`, свежий healthy-check и свободную ёмкость; для FREE дополнительно требуется `is_available_for_free=true`. AUTO рассматривает все подходящие страны, COUNTRY — только запрошенную. Оба режима используют заменяемую стратегию; MVP выбирает узел с наименьшей загрузкой по отношению числа активных сессий к capacity, затем с наибольшим свободным запасом и стабильным UUID tie-break. Внутренние оценки наружу не возвращаются. Создание сессии блокирует строки узлов candidate set и повторно применяет ту же policy, чтобы конкурентные запросы не превысили capacity.

Country Quality — целое число `0..100`, рассчитанное заменяемой стратегией только из уже сохранённого Backend snapshot, поэтому вычисление не вызывает Node Agent для каждого запроса. Сначала применяется та же eligibility policy, что при создании сессии; отсутствие кандидатов всегда даёт `0`. Для каждого кандидата MVP умножает долю свободной capacity на confidence свежести health snapshot: confidence равен `1` в первой половине stale timeout, затем линейно снижается до минимального `0.01`. Вклад кандидатов объединяется как `100 × (1 − Π(1 − contribution))` с округлением half-up. Это не арифметическое среднее: дополнительный работоспособный узел повышает устойчивость страны, а один слабый узел не размывает хороший. Для непустого eligible set результат ограничивается `1..100`; здоровье остаётся жёстким eligibility gate. До появления проверенных latency/loss measurements формула намеренно не имитирует качество сети по провайдеру, региону или IP.

## Выбор способа запуска

| Способ | Когда использовать |
| --- | --- |
| Весь стек в Docker | Быстро проверить проект без установки Python на компьютер. |
| Python на компьютере, базы в Docker | Разрабатывать Backend с автоматической перезагрузкой после изменения исходников. |
| Backend на VPS | Использовать [инструкцию развёртывания](../docs/backend-deployment.md), а для обновлений — [инструкцию обслуживания](../docs/vps-maintenance.md). |

Образ — собранный пакет приложения и зависимостей. Контейнер — запущенный экземпляр образа. Compose описывает несколько контейнеров, их сеть и настройки. Изменение исходников не меняет уже собранный образ автоматически.

## Весь стек в Docker

Установите Docker с Compose v2; на Windows включите Linux-контейнеры. Убедитесь, что Docker запущен:

```sh
docker version
docker compose version
```

Команды ниже выполняются из корня репозитория, а не из `backend/`.

```sh
docker compose -f infra/docker/compose.yaml up --build -d --wait
docker compose -f infra/docker/compose.yaml ps
```

Первая команда собирает Backend, запускает PostgreSQL и Valkey в фоне и ожидает запуска. Вторая показывает состояние контейнеров. Порты опубликованы только на `127.0.0.1`: API — 8000, PostgreSQL — 5432, Valkey — 6379. Они доступны с вашего компьютера, а не со всей локальной сети. Данные PostgreSQL сохраняются в именованном Docker-томе.

Откройте `http://127.0.0.1:8000/ready`: ожидается HTTP 200. При HTTP 503 одна из баз ещё не готова или недоступна. Для просмотра сообщений:

```sh
docker compose -f infra/docker/compose.yaml logs -f backend
```

`Ctrl+C` закрывает просмотр. После изменения кода повторите `up --build -d --wait`: у образа нет автоматической перезагрузки исходников.

Если порт занят, задайте другой порт **до запуска Compose**. Пример для PowerShell:

```powershell
$env:POSTGRES_PORT = "5433"
docker compose -f infra/docker/compose.yaml up --build -d --wait
```

Для Bash на Linux/macOS: `export POSTGRES_PORT=5433`. Аналогично доступны `VALKEY_PORT` и `BACKEND_PORT`. Меняются только порты компьютера; внутри Docker-сети используются прежние порты. Если запускаете Python вне Docker, укажите выбранный порт в его `.env`. Существующий локальный файл `.tools/compose.local.yaml`, если он есть на вашем компьютере, остаётся совместимым.

Чтобы остановить стек:

```sh
docker compose -f infra/docker/compose.yaml down
```

Без `-v` том PostgreSQL сохраняется. Не используйте локальные демонстрационные пароли для общего сервера.

## Python на компьютере, базы в Docker

Нужны Python **3.13**, менеджер зависимостей **uv**, Git и Docker с Compose. Проверьте `python --version` и `uv --version`. Если установлен другой Python, настройте доступ к 3.13 перед установкой зависимостей.

1. В корне репозитория запустите только базы:

   ```sh
   docker compose -f infra/docker/compose.yaml up -d --wait postgres valkey
   ```

   Контейнер Backend здесь не нужен: иначе он займёт порт, который потребуется локальному Python.

2. Перейдите в `backend/` и создайте личную конфигурацию. В PowerShell:

   ```powershell
   cd backend
   Copy-Item .env.example .env
   ```

   В Linux/macOS используйте `cp .env.example .env`. Копируйте шаблон только при первой настройке: не перезаписывайте уже заполненный `.env`. Файл должен оставаться вне Git.

3. Откройте `.env` в редакторе. Для стандартного локального Compose значения уже подходят. Если меняли порты, исправьте их в `POSTGRES_URL` и `VALKEY_URL`.

4. Установите версии зависимостей из `uv.lock` и запустите сервер:

   ```sh
   uv sync --frozen
   uv run uvicorn prettylisavpn.main:create_app --factory --reload --no-access-log
   ```

   `--frozen` не пересчитывает версии зависимостей. `--factory` вызывает фабрику приложения, `--reload` перезапускает процесс после изменения кода, `--no-access-log` отключает журнал URL HTTP-запросов. Режим `--reload` предназначен для разработки.

5. Откройте `http://127.0.0.1:8000/ready`. Для завершения Uvicorn нажмите `Ctrl+C`, затем при необходимости остановите базы командой `down` из корня репозитория.

Запускайте uv из `backend/`: Pydantic ищет `.env` в текущем каталоге. Переменные окружения терминала имеют приоритет над файлом.

## Настройки приложения

Таблица соответствует [config.py](src/prettylisavpn/config.py). Все строки подключения с настоящими паролями являются секретами.

| Переменная | Значение по умолчанию / назначение |
| --- | --- |
| `APPLICATION_NAME` | `PrettyLisaVPN`; непустое имя в `/version`. |
| `APPLICATION_VERSION` | `0.1.0`; на VPS задавайте идентификатор фактически развёрнутой сборки. |
| `ENVIRONMENT` | `development`; для рабочего сервиса используйте `production`. |
| `LOG_LEVEL` | `INFO`; допустимы также `DEBUG`, `WARNING`, `ERROR`, `CRITICAL`. |
| `POSTGRES_URL` | Локальная демонстрационная строка; схема обязательно `postgresql+asyncpg://`. На VPS задаётся явно. |
| `VALKEY_URL` | `redis://localhost:6379/0`; допустимы `redis://` и `rediss://` (TLS). На VPS задаётся явно. |
| `OTP_HMAC_SECRET` | HMAC-секрет длиной не менее 32 символов. Для production обязателен отдельный случайный секрет. |
| `OTP_TTL_SECONDS` | `300`; срок действия OTP в секундах. |
| `OTP_REQUEST_COOLDOWN_SECONDS` | `60`; минимальный интервал между запросами OTP для одного email. |
| `OTP_EMAIL_REQUEST_LIMIT`, `OTP_EMAIL_RATE_WINDOW_SECONDS` | `5`, `3600`; лимит запросов на email и окно лимита в секундах. |
| `OTP_IP_REQUEST_LIMIT`, `OTP_IP_RATE_WINDOW_SECONDS` | `20`, `3600`; лимит запросов на IP и окно лимита в секундах. |
| `OTP_MAX_VERIFICATION_ATTEMPTS` | `5`; число неверных попыток до удаления OTP. |
| `ACCESS_TOKEN_TTL_SECONDS` | `900`; срок действия подписанного access token. |
| `REFRESH_TOKEN_TTL_SECONDS` | `2592000`; срок действия refresh-сессии (30 дней). |
| `EMAIL_PROVIDER` | `timeweb`; используется SMTP-интеграция почтового ящика Timeweb. |
| `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT` | `smtp.timeweb.ru`, `465`. |
| `EMAIL_SMTP_TLS_MODE` | `implicit_tls`; также поддерживается `starttls` для порта 587. |
| `EMAIL_SMTP_USERNAME`, `EMAIL_FROM_ADDRESS` | `auth@prettylisavpn.com`; Timeweb требует совпадения SMTP-логина и отправителя. |
| `EMAIL_SMTP_PASSWORD` | Пароль почтового ящика; без значения adapter не создаётся. Никогда не коммитьте. |
| `EMAIL_FROM_NAME` | `PrettyLisaVPN`. |
| `EMAIL_CONNECTION_TIMEOUT_SECONDS`, `EMAIL_SEND_TIMEOUT_SECONDS` | `5`, `10`; сетевой и общий тайм-аут отправки. |
| `VPN_NODE_STALE_TIMEOUT_SECONDS` | `90`; после этого интервала без успешного authenticated health check узел недоступен для новых сессий. |
| `VPN_CLIENT_SUBNET` | `10.77.0.0/16`; общий provider-independent IPv4-пул адресов VPN-клиентов. |
| `VPN_CLIENT_GATEWAY_IPV4` | `10.77.0.1`; зарезервированный адрес gateway внутри `VPN_CLIENT_SUBNET`, клиентам не выдаётся. |
| `VPN_CLIENT_DNS` | JSON-массив IPv4 DNS resolver addresses; по умолчанию `["1.1.1.1","1.0.0.1"]`. Передаётся только native tunnel layer. |
| `VPN_CLIENT_ALLOWED_IPS` | JSON-массив IPv4 CIDR; по умолчанию `["0.0.0.0/0"]` для full tunnel. Передаётся только native tunnel layer. |
| `VPN_SESSION_RECONCILE_INTERVAL_SECONDS` | `15`; период durable expiry/peer cleanup reconciliation, не зависит от клиента. |
| `VPN_NODE_HEALTH_POLL_INTERVAL_SECONDS` | `30`; период опроса, всегда меньше stale timeout. |
| `VPN_NODE_AGENT_PORT` | `8443`; HTTPS/mTLS порт Node Control Agent. |
| `VPN_NODE_AGENT_AUTH_TOKEN` | Дополнительный machine bearer secret, минимум 32 символа. |
| `VPN_NODE_AGENT_TLS_CA`, `VPN_NODE_AGENT_TLS_CLIENT_CERTIFICATE`, `VPN_NODE_AGENT_TLS_CLIENT_KEY` | CA сервера и клиентская mTLS identity Backend; задаются только вместе с token и монтируются read-only. |
| `DEPENDENCY_TIMEOUT_SECONDS` | `2`; тайм-аут проверки зависимости, больше 0 и не больше 30 секунд. |
| `POSTGRES_POOL_SIZE` | `5`; размер пула соединений, минимум 1. |
| `POSTGRES_MAX_OVERFLOW` | `5`; дополнительные временные соединения сверх пула, минимум 0. |

Agent polling включается только при полном наборе mTLS/token настроек. Для production добавьте к обычной Compose-команде `-f infra/deployment/compose.node-agent.yaml`; override требует защищённый host-каталог `VPN_NODE_AGENT_TLS_DIRECTORY` и монтирует его read-only. Без override Backend сохраняет обратную совместимость и не запускает monitor.

Отдельные `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `VALKEY_HOST` и подобные переменные Backend **не читает**. Хост, порт, пользователь и пароль объединяются в URL. Символы со специальным значением в логине/пароле нужно кодировать для URL: например, `@` как `%40`. Не используйте онлайн-сервисы для кодирования настоящих паролей.

Адрес должен быть доступен именно процессу приложения. `localhost` внутри контейнера означает сам контейнер; для локальной Docker-сети используйте имена `postgres` и `valkey`, для внешних баз — адреса провайдера. `host.docker.internal` в Docker Desktop позволяет обратиться к сервису на компьютере. Сохраняйте требования провайдера к TLS и проверке сертификатов.

## Служебные методы и логи

| Метод | Что проверяет | Ожидаемый результат |
| --- | --- | --- |
| `GET /health` | Процесс может отвечать; базы не опрашиваются. | HTTP 200 при работающем приложении. |
| `GET /ready` | На каждый запрос выполняет PostgreSQL `SELECT 1` и Valkey `PING`. | HTTP 200, если обе зависимости доступны; иначе HTTP 503 и код `dependencies_unavailable`. |
| `GET /version` | Метаданные запущенного приложения. | `application_name`, `application_version`, `environment`. |
| `POST /auth/request-otp` | Валидирует email, применяет Valkey cooldown/лимиты и отправляет OTP. | HTTP 202 и `{"status":"accepted"}` без сведений о наличии аккаунта. |
| `POST /auth/verify-otp` | Одноразово проверяет OTP и атомарно создаёт login-состояние. | Возвращает короткоживущий access token, вращаемый refresh token и контекст пользователя, устройства и подписки. |
| `POST /auth/refresh` | Проверяет `session_id` и refresh token, затем атомарно меняет его хеш. | Возвращает новую пару access/refresh; повторное использование старого refresh token отклоняется. |
| `POST /auth/logout` | Проверяет Bearer access token и отзывает связанную с ним текущую сессию. | HTTP 200 и `{"status":"logged_out"}`. |
| `GET /me` | Проверяет access token, сессию, пользователя и устройство. | Возвращает `id`, `email`, текущий `plan` и `active_device_count`. |
| `GET /devices` | Возвращает только устройства владельца текущей сессии. | Для каждого устройства возвращает имя, платформу, статус, UTC-времена и признак `is_current`. |
| `DELETE /devices/{device_id}` | Отзывает принадлежащее пользователю устройство и все его auth-сессии. | Чужой и неизвестный UUID одинаково дают `device_not_found` (404). |

`POST /auth/request-otp` возвращает стабильные коды `otp_rate_limited` (429), `otp_service_unavailable` (503) и `email_service_unavailable` (503). OTP никогда не входит в HTTP-ответ.

`POST /auth/verify-otp` принимает `email`, шестизначный `code`, UUID `installation_id`, `platform` и `device_name`. Ошибки: `otp_invalid_or_expired` (401), `user_blocked` (403), `device_limit_reached` (409), `otp_service_unavailable` и `login_service_unavailable` (503). В PostgreSQL хранится только SHA-256 refresh-токена; access token подписывается отдельным ключом, производным от `OTP_HMAC_SECRET` с доменным разделением. TTL задают `ACCESS_TOKEN_TTL_SECONDS` и `REFRESH_TOKEN_TTL_SECONDS`.

`POST /auth/refresh` принимает `session_id` и `refresh_token`. Истёкший, отозванный, неверный или уже использованный токен даёт `invalid_refresh_token` (401). Защищённые методы используют `Authorization: Bearer <access_token>` и возвращают `authentication_required`, `invalid_access_token` либо `invalid_session` (401), `user_blocked` или `device_revoked` (403), `auth_service_unavailable` (503). Тела запросов и ответов с токенами не журналируются.

Текущее устройство разрешено отзывать. Ответ на `DELETE` ещё возвращается с
`is_current=true`, после чего access token и все refresh token этого устройства становятся
недействительными. Отзыв сериализован той же блокировкой пользователя, что и регистрация:
освободившееся место сразу учитывается в лимите пяти активных устройств. Повторный отзыв уже
отозванного собственного устройства идемпотентен и не создаёт повторное событие аналитики.

Недоступность базы не останавливает процесс. Поэтому Docker-статус `healthy`, основанный на `/health`, ещё не означает готовность сервиса; отдельно проверяйте `/ready`. Docker сам по себе не перезапускает контейнер только из-за статуса `unhealthy`.

Подключения используют SQLAlchemy 2.x/asyncpg и Redis-совместимый асинхронный клиент для Valkey. Пулы создаются на время жизни приложения, подключаются по мере необходимости и закрываются при завершении. `Postgres.session()` закрывает сессию и откатывает незавершённую работу: успешную запись вызывающий код должен явно подтвердить через commit.

Отправка OTP-писем описана в [руководстве EmailProvider](../docs/email-provider.md). SMTP-подключение создаётся на одну отправку и не повторяет её автоматически при неоднозначной сетевой ошибке.

Backend пишет JSON-логи с UTC-временем. Неожиданные HTTP-ошибки возвращают общий код `internal_error`; ошибки валидации не повторяют входные значения. Необработанные тексты исключений, SQL-параметры и HTTP access URL в логах приложения не записываются. Это описание Backend: политику логов внешнего reverse proxy нужно оценивать отдельно.

## Сборка и отдельный запуск образа

Из корня репозитория:

```sh
docker build -t prettylisavpn-backend:0.1.0 backend
```

Тег здесь иллюстративный. Для каждого релиза используйте уникальную версию или хеш коммита. Перед запуском передайте `POSTGRES_URL`, `VALKEY_URL` и `OTP_HMAC_SECRET` через окружение терминала или менеджер секретов:

```sh
docker run -d --name prettylisa-backend --init --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges:true --stop-timeout 30 -p 127.0.0.1:8000:8000 -e ENVIRONMENT=production -e APPLICATION_VERSION=0.1.0 -e POSTGRES_URL -e VALKEY_URL -e OTP_HMAC_SECRET prettylisavpn-backend:0.1.0
```

Команда передаёт переменные по имени, не записывая пароль в аргументы. Приложение работает от UID/GID 10001, с файловой системой только для чтения и временным `/tmp`. Доступ администратора Docker позволяет читать окружение контейнера, поэтому его нужно ограничивать.

Образ собирается в несколько этапов. Версия базового Python 3.13 закреплена digest, зависимости устанавливаются из `uv.lock`; uv, кэш сборки и инструменты тестирования не входят в итоговый образ. Исходники подключаются через `PYTHONPATH`. Контекст сборки ограничен разрешёнными файлами; `.env` и приватные ключи не должны попадать в образ. Секреты нельзя передавать через аргументы сборки.

Uvicorn получает SIGTERM, даёт запросам до 20 секунд на завершение и закрывает пулы. Перед принудительной остановкой предусмотрено 30 секунд:

```sh
docker stop --time 30 prettylisa-backend
docker rm prettylisa-backend
```

## Отдельный production Compose без Caddy

[compose.production.yaml](../infra/docker/compose.production.yaml) запускает **только Backend** с внешними PostgreSQL и Valkey. Это самостоятельный файл; не объединяйте его с локальным Compose. Он явно задаёт `ENVIRONMENT=production` и публикует API на loopback-порту 8000 (`BACKEND_PORT` позволяет изменить порт).

1. Подготовьте образ и доступные из контейнера внешние базы.
2. Скопируйте `infra/docker/.env.example` в неотслеживаемый `infra/docker/.env.production`. Заполните `BACKEND_IMAGE`, `APPLICATION_VERSION`, `POSTGRES_URL`, `VALKEY_URL`, `OTP_HMAC_SECRET`; остальные настройки необязательны.
3. Из корня репозитория запустите:

   ```sh
   docker compose -p prettylisa-production --env-file infra/docker/.env.production -f infra/docker/compose.production.yaml up -d --wait
   docker compose -p prettylisa-production --env-file infra/docker/.env.production -f infra/docker/compose.production.yaml ps
   ```

4. Проверьте `/health`, `/ready`, `/version` по `http://127.0.0.1:8000`. Для публичного доступа нужен отдельно настроенный reverse proxy с TLS. Для готового варианта с Caddy используйте [инструкцию VPS](../docs/backend-deployment.md).

Для остановки используйте те же `-p`, `--env-file`, `-f`, заменив `up -d --wait` на `down`. Не печатайте обычный `docker compose config` в общий лог: он может раскрыть секреты; для проверки используйте `config --quiet`.

## Проверки перед коммитом

Из `backend/`, после `uv sync --frozen`:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

Ruff проверяет форматирование и типичные ошибки, mypy — типы, pytest — поведение. Обычный набор тестов не требует внешних сервисов. Если форматирование нужно исправить, выполните `uv run ruff format .`, просмотрите изменения и повторите проверки.

## Непрерывная интеграция

Workflow [backend.yaml](../.github/workflows/backend.yaml) запускается для pull request и push, если изменены Backend, его Docker-конфигурация, deployment-конфигурация или сам workflow. Все проверки выполняются последовательно в одном job и останавливаются на первой ошибке:

1. установка зависимостей строго из `uv.lock` с безопасным кэшем загрузок uv;
2. проверка форматирования Ruff;
3. lint Ruff и строгая проверка типов mypy;
4. unit-тесты без инфраструктуры;
5. применение Alembic до `head` и `alembic check` на временном PostgreSQL;
6. интеграционные тесты с временными PostgreSQL и Valkey;
7. сборка production Docker-образа и Docker-тесты образа и Compose-файлов.

CI использует только одноразовые локальные учётные данные service containers. Production-секреты и доступ к deployment-среде ему не нужны; workflow ничего не публикует и не развёртывает.

Чтобы воспроизвести проверки качества и unit-тесты, из `backend/` выполните:

```sh
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -m "not integration and not docker"
```

Для проверки миграций и интеграционных тестов сначала запустите PostgreSQL и Valkey из корня репозитория:

```sh
docker compose -f infra/docker/compose.yaml up -d --wait postgres valkey
```

Затем из `backend/`, используя локальные URL из `.env`, выполните:

```sh
uv run alembic upgrade head
uv run alembic check
RUN_INTEGRATION_TESTS=1 uv run pytest -m integration
```

В PowerShell последняя команда записывается так:

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
uv run pytest -m integration
Remove-Item Env:RUN_INTEGRATION_TESTS
```

Docker-часть CI воспроизводится из корня репозитория и затем из `backend/`:

```sh
docker build --tag prettylisavpn-backend:test backend
cd backend
RUN_DOCKER_TESTS=1 uv run pytest -m docker
```

В PowerShell установите `RUN_DOCKER_TESTS` тем же способом, что и `RUN_INTEGRATION_TESTS` выше.

Для интеграционных тестов запустите обе базы, убедитесь, что настройки указывают на тестовое окружение, и в PowerShell выполните:

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
uv run pytest
Remove-Item Env:RUN_INTEGRATION_TESTS
```

В Bash: `RUN_INTEGRATION_TESTS=1 uv run pytest`. Тесты проверяют настоящие соединения и отдельные отказы зависимостей; рабочие базы для тестирования не используйте.

Для тестов Docker сначала из корня соберите `docker build -t prettylisavpn-backend:test backend`. Затем из `backend/`:

```powershell
$env:RUN_DOCKER_TESTS = "1"
uv run pytest -m docker
Remove-Item Env:RUN_DOCKER_TESTS
```

В Bash: `RUN_DOCKER_TESTS=1 uv run pytest -m docker`. `DOCKER_TEST_IMAGE` позволяет выбрать другой тег. Проверяются пользователь контейнера, содержимое образа, liveness без баз, корректная остановка и production Compose. Тесты создают временный контейнер и удаляют его после проверки, не останавливая ваш стек. CI выполняет проверки с настоящими сервисами и собранным образом.

Ручную проверку отказа выполняйте только локально: из корня остановите Valkey командой `docker compose -f infra/docker/compose.yaml stop valkey`. `/ready` должен вернуть 503, а `/health` — 200. Восстановите сервис командой `docker compose -f infra/docker/compose.yaml start valkey` и снова проверьте `/ready`.
