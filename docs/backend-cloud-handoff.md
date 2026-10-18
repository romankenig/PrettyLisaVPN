# Backend: продолжение работы из Cloud — 2026-10-17

## Проверка SSH и готовности rollback — 2026-10-18

Владелец разрешил использовать существующие development SSH secrets Actions для
проверки. Workflow `Development SSH preflight`,
[run 39082773250](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39082773250),
push SHA `886dcd36828e96fac6a9d5e42de1f4c0bd7d310e`, attempt 1,
успешно выполнил read-only SSH-проверку в 00:26:48 UTC.

- Все пять SSH secrets присутствуют; настроенный DNS alias разрешается точно в
  подтверждённый `95.140.152.42`, порт 22. Значения secrets не выводились.
- SSH-аутентификация успешна с существующим deployment-пользователем из secrets;
  сервер проверен через known_hosts, StrictHostKeyChecking и ED25519 fingerprint
  владельца. Это доступ из Actions, не прямой SSH из Cloud и не отдельная проверка root-login.
- Backend container `c699b077e0ab` — healthy; runtime `development`, версия
  `dev-1938d4d32eb58fd097e7c8840f695b735ec86b8f`.
- Фактический image ID:
  `sha256:51b825d271f21e3555045d9dc5a9c4146ded8795e7ce505fead89ca14c7a4d11`.
  Тег `prettylisavpn-backend:1938d4d32eb58fd097e7c8840f695b735ec86b8f`
  сохранён локально и указывает ровно на этот запущенный image ID.
- `current`, Compose working directory и canonical env согласованы с релизом
  `1938d4d32eb58fd097e7c8840f695b735ec86b8f`; canonical env находится в
  `/opt/prettylisavpn/secrets/deployment.env`, mode 0600.
- Реальные `alembic current` и `alembic heads` завершились с кодом 0 и показали
  одинаковый `0017_profile_evidence`. Миграции этой проверкой не запускались.
- `/health`, `/ready`, `/version` — HTTP 200; PostgreSQL и Valkey доступны.
- На VPS сохранены прежние образы и Compose-каталоги, но в legacy-каталогах нет
  отдельных `deployment.env` и `image-id`. Нельзя реконструировать прошлые
  credentials/config по одному SHA. Перед первым новым deploy необходимо сохранить
  текущий canonical env, Compose-конфигурацию, current и зафиксированный image ID
  как одну пару для возврата. Новый CI перед заменой сохраняет `previous.env`,
  `previous-image-id` и путь `previous-release`; отсутствие старого образа или
  Compose-конфигурации останавливает deployment до переключения контейнеров.

Дополнительно Git tree SHA сравнен между фактически развёрнутым commit `1938d4d...`
и PR: `backend/src`, migrations, pyproject, uv.lock и Dockerfile идентичны.
Переход меняет runtime/deploy tooling, не код приложения и не схему БД.

Preflight не менял контейнеры, образы, env, symlinks или схему БД. Исходный run
39082727021 остановился до SSH на слишком узкой проверке буквального hostname;
исправленный вариант допускает DNS alias только при точном совпадении IP и
проверяет ED25519 host key. Это не обход проверки целевого VPS.

Пункт SSH-доступа через Actions подтверждён. Реальное развёртывание нового runtime
и цикл rollback/restore ещё не выполнялись; PR #7 остаётся неслитым.
Окончательные результаты всех workflow нового HEAD фиксируются в PR description.

## Исходная подготовка и ограничения Cloud

Уточнение владельца: development VPS — `95.140.152.42`, SSH `root`, порт `22`.
Предоставлен ED25519 known_hosts, fingerprint
`SHA256:BrayNvgVNXSzO6xAJ08FwnebiUA8/VlQNgI+ctes96U`.
Приватный ключ не передан и в Cloud не настроен. Это не подтверждение SSH-входа.

Для проверки двух названных кандидатов (`dev-api.prettylisavpn.com` и
`api.prettylisavpn.com`) добавлен `Development API probe`: выполняет только
публичные GET `/health`, `/ready`, `/version` из GitHub runner, с проверкой TLS,
без redirects, SSH и secrets. Результат сохраняется в JSON artifact и run summary.
Успех job означает завершение сбора наблюдений; фактическую доступность определяют
HTTP-результаты. Они не подтверждают сеть самого Cloud. Актуальные результаты,
SHA/run/attempt и вывод о development-домене фиксируются в описании PR.

## Область и версии

Исходная ветка `develop`: `694ec52f5a29a7c7174c09ab340d6e436f2c9328`.
Windows не меняется; backend package/default/example version остаётся `0.1.0`.
Изменены только CI, deployment tooling, их тесты и документация. Новых HTTP API
или миграций нет. История — [CHANGELOG](../CHANGELOG.md).

Новый CI читает base из pyproject и формирует
`0.1.0-dev.<run>+g<полный SHA>`. SHA — фактический checkout/build commit;
для PR это временный merge SHA, а не обязательно head ветки.
`runtime-identity.json` хранит SHA, канал, run и attempt; CI сохраняет несекретный
artifact. Attempt не входит в runtime-строку согласно принятой схеме, но входит
в тег образа и каталог релиза. Release-формат генератор поддерживает отдельно;
автоматического production/release deploy эта задача не добавляет.

На VPS сохраняются env (0600), прежний env, metadata, Compose и локальный image ID.
Повторный run/attempt не перезаписывает прежний каталог. См. точный порядок
[deploy и rollback](backend-deployment.md#ручной-откат-development).
Образ не пересобирается при rollback; схема БД остаётся на месте.

## Что действительно проверено

| Проверка | Результат и границы |
| --- | --- |
| Чтение исходников CI/deploy, `/ready`, `/version`, Alembic | Выполнено на указанном develop snapshot через GitHub connector |
| Cloud readiness | Managed environment running/connected; secrets, runtime variables и outbound identities отсутствуют; HTTP readiness state unknown |
| Получение checkout | Прямой git clone не смог подключиться к proxy:8080; для работы скачан частичный snapshot (backend и связанные инструкции), без бинарных файлов и остальных компонентов |
| Граф миграций | Статически проверены 17 revisions, один head `0017_profile_evidence`, нет пропусков и циклов; это не запуск SQL |
| Новый runtime/deploy/rollback | Локально 9 стандартных unittest: каналы, run/attempt, неверный SHA/номер, deploy до up, rollback без pull/migrations, отсутствие образа, ошибки версии/HTTP/миграции, права env |
| YAML/Bash/Python syntax | YAML разобран; каждый встроенный run-скрипт проверен `bash -n`; deploy.sh и Python syntax проверены; `git diff --check` выполнен |
| Установка зависимостей | `uv sync --frozen` с writable cache нашёл Python 3.13.5, но не смог скачать pydantic через proxy (Operation not permitted); окружение .venv неполное |
| Локальные Ruff/mypy/pytest, PostgreSQL/Valkey и Docker tests | Полный прогон в Cloud не выполнен: зависимости не установлены, Docker socket недоступен (operation not permitted, UID 1000). Не запускать второй daemon от непривилегированного пользователя |
| Текущие публичные `/ready` и `/version` | Не подтверждены: нет подтверждённого URL development; пробный HTTPS к api.prettylisavpn.com остановился на соединении с proxy до обращения к серверу |
| Реальный новый deploy и VPS rollback | Не выполнены: отсутствуют Cloud SSH/known-hosts и адрес стенда. Локальные тесты подставляют Docker/HTTP; не подтверждают состояние VPS |

Дополнительный вызов для сетевых разрешений не завершился до прерывания
пользователем. Это не успешный повтор установки и не подтверждение доступа.

Результаты CI нового remote HEAD, все события/jobs/check-runs/statuses и ссылки
фиксируются в описании PR после финального push, чтобы docs commit не запускал
бесконечный повтор проверки. До зелёного CI новая реализация не считается проверенной
в GitHub runner; до реального deploy/rollback не считается проверенной на стенде.

## Существующий CI и исторический development-deploy

Получен общий список Actions runs для develop: 65 запусков, одна страница
`per_page=100`. Последний Backend run:
[39007175643](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39007175643),
push SHA `1938d4d32eb58fd097e7c8840f695b735ec86b8f`.
Оба jobs завершены success: `Quality, tests, migrations, and image` и
`Deploy development`. Проверены steps и deployment log.

В этом **историческом** run реально прошли Ruff, mypy, unit/integration tests,
`alembic upgrade head`, `alembic check`, сборка и Docker tests. Deployment log
подтверждает миграции, healthy containers и health/readiness/version checks;
сервер сообщил legacy `dev-1938d4d32eb58fd097e7c8840f695b735ec86b8f`.
Это не проверка актуального develop или нового кода задачи и не актуальный HTTP probe.

Существующие тесты `/ready` покрывают обе зависимости, 503 при сбое и timeout,
отсутствие утечки ошибок; `/health` и `/version` не обращаются к БД.
Новая логика JSON-сравнения версии проверяет точное поле, допускает пробелы,
отвергает подстроки, невалидный JSON и отсутствие ожидаемого поля.

Deploy остаётся только push в `develop` при `DEV_DEPLOY_ENABLED=true` и
успешном check job. PR, другая ветка и workflow_dispatch не разворачивают сервер.
Новая версия не была слита в develop этой задачей.

## Что ещё нужно для работы из Cloud

1. Исправное соединение с session proxy для github.com, pypi.org,
   files.pythonhosted.org и образов Docker; Docker socket access в Cloud.
   Сетевые настройки и credentials меняются штатной конфигурацией окружения.
2. Подтверждённый development API URL. Для read-only smoke достаточно HTTPS
   без SSH: получить `/health`, `/ready`, `/version`, сохранить время и точные ответы.
3. Development SSH host/port/user, отдельный ключ и проверенный known_hosts,
   доступ к `/opt/prettylisavpn` и Docker. Не переносить секреты в репозиторий/чат.
   GitHub connector доступен, но не предоставляет Cloud приватный ключ из Actions.
4. Для интеграционных проверок: изолированные тестовые PostgreSQL/Valkey,
   URL и сетевой маршрут. Для приватных сервисов нужны точечные TCP grants/VPN;
   сейчас `vpn_configured=false`, TCP domains/ip_ranges пусты.
5. Доступ к provider snapshot/backup и подтверждённый план восстановления нужен,
   если будущий rollback затронет несовместимую схему. Для этой задачи схема не меняется.

GitHub Actions development secrets уже были достаточны для исторического run;
это не доказывает их нынешнее состояние и не означает их наличие в Cloud.
Список обязательных `DEV_*` приведён в backend-deployment.md. Не создавать
новые provider identities или повторный логин без конфигурации владельца.

## Точка продолжения

После CI и согласованного merge дождаться нового development-deploy, сверить
source/build SHA, run/attempt, metadata, локальный image ID и точный `/version`.
Сначала зафиксировать прежний legacy image ID и env на VPS. Затем выполнить
контролируемый rollback на сохранённый образ, подтвердить `/ready` и прежнюю
runtime-строку, вернуть новый релиз и снова проверить. Зафиксировать реальные
HTTP-ответы, время, образ и результаты миграций. До этого live rollback остаётся
открытой проверкой. Не выполнять downgrade БД ради проверки rollback приложения.
