# Backend: актуальный статус и журнал продолжения

## Актуальный срез — 2026-10-19

Актуальные функции, границы проверки и backlog собраны в
[project-status.md](project-status.md): backend **0.10.0**, Windows **0.11.1**,
schema **0026**. PR #17 слит; deployed source develop —
`090dd4117fb829f6faad1853cba5ae577c8837aa`.
[Backend run 39200525561](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39200525561),
attempt 1, успешно выполнил development deployment с runtime
`0.10.0-dev.39200525561+g090dd4117fb829f6faad1853cba5ae577c8837aa`:
health/readiness/точная версия подтверждены workflow 2026-10-19.

Windows acceptance проверяла source HEAD `4452327e6904a1cbf520f3088f908f51e453e00d`;
между ним и deployed HEAD отличается только deployment README. Реальный провайдер
не подключён; OTP остаётся на паузе; inbox поддержки и полный Windows VPN data plane
не приняты. Тексты ниже — **журнал предыдущих задач**: старые версии, migration head,
условия Cloud и статусы «не слито/не развёрнуто» относятся к своим историческим
срезам и не заменяют актуальную сводку. Изменение этой документации — version unchanged.

## Windows development acceptance — Windows 0.11.1 / backend 0.10.0 unchanged

Development base SHA `4347935f2c5c20cabc523ff94acc12a2f1bd3c21`, runtime
`0.10.0-dev.39126998534+g4347935f2c5c20cabc523ff94acc12a2f1bd3c21`, schema 0026.
Native acceptance connects directly through HTTPS. Disposable identities are
created through server services and removed in cleanup; separate manual OTP
acceptance is paused by the owner and requires explicit workflow_dispatch opt-in.
Public location now uses a fixed native HTTPS command: generic plugin Origin
caused provider HTTP 403. No general HTTP header/TLS restrictions were relaxed.
Payment checks use isolated CI
PostgreSQL/sandbox; deployed billing remains disabled. Home refresh is fixed in
Windows 0.11.1; backend source is unchanged. Actual SHA/run/attempt and observations
are recorded in PR #17 and [acceptance runbook](windows-development-acceptance.md).


## Route capabilities — backend 0.10.0 / Windows 0.11.0

Исходные версии 0.9.0 / 0.10.0; новые версии 0.10.0 / 0.11.0. Schema остаётся
0026. Overview дополнен mode и route/currency/recurring capabilities; Windows
требует явного LIVE для платежей, SANDBOX/legacy read-only. Реальный провайдер
не подключён. Матрица проверяется до provider IO; принятые recurring terms
сохраняются в quote. Старые receipts/provider requests совместимы.
Base develop 334bd1bb3570dce7d75d29efd20071aafa1583df. Проверенные product/build
SHA/run/attempt, нативные скриншоты и артефакты — в task PR. Наличие исходников
не означает deploy; текущий deploy-статус также фиксируется в PR.

## Subscription lifecycle — backend 0.9.0

Исходная версия 0.8.0 → 0.9.0; Windows unchanged 0.10.0. Миграция 0026
добавляет сохраняемое состояние тестовых разрешений и восстанавливает его из
существующих receipts. Публичный billing-контракт совместим. Продление, смена
способа и отмена проходят через тот же provider port; частичные/противоречивые
внешние результаты остаются PENDING. Реальные списания/привязки не включаются.
Исходный develop: 6dc75c9e8c28b421e0def30366ad0f7d930006bb. Точные проверенные
product/build SHA, run/attempt, артефакты и итоговый deploy-статус — в task PR.
При откате приложения сохранять схемы 0024/0025/0026, операции, receipts и
разрешения; незавершённые операции требуют прежнего адаптера. Не переигрывать
успешные внешние мутации новым UUID.

## Development sandbox — задача backend 0.8.0

Исходная версия 0.7.0 → 0.8.0, Windows unchanged 0.10.0; миграция 0025
добавляет постоянные тестовые receipts/events. HTTP-контракт совместим, обычный
runtime по умолчанию disabled. Настройка и восстановление описаны в
[billing-sandbox.md](billing-sandbox.md). Изменения готовятся от develop
`0fb3a42a61d95fae2b086bfe1397642b380784e7`; проверяемые product/build SHA,
run/attempt и артефакты — в PR #14. Development deploy 0.8.0 завершился успешно:
SHA 6dc75c9e8c28b421e0def30366ad0f7d930006bb, run 39121363281, attempt 1.
Реальный платёжный provider не подключается. Не откатывать/удалять журналы
0024/0025 при откате приложения; PENDING требует прежнего адаптера.

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


## Support — backend 0.3.0 → 0.4.0 / Windows 0.8.0 → 0.9.0

Migration 0020 is additive; requests/attachments/outbox share a PostgreSQL
transaction. Application rollback leaves these tables and queued requests.
Separate DEV_SUPPORT_SMTP_PASSWORD is required; SMTP sender app-helper and sole
recipient help@prettylisavpn.com are configured only on the server.

Cloud has no bound secrets/outbound identities; dependency installation and
loopback socket creation are blocked in this executor. Verification uses Actions.
Source/build/run/attempt, every workflow, native screenshots, real development
deploy and SMTP evidence are recorded in the task PR. Native support screenshots
use a synthetic loopback API; inbox delivery and mailbox/backup retention need
separate operator evidence.

## Подписки: backend 0.4.0 → 0.5.0

Единый effective_plan для /me, VPN и messages; миграция 0021 сохраняет оплаченные
даты при CANCELED. Окончание подписки обрабатывается и для открытых платных peers.
Windows 0.9.0 без изменений. Free: час/сутки UTC без рекламы, миграция 0022 с durable учётом; Platinum ручной с правами Premium.
Платёжный провайдер не добавлен.
Контракт, продуктовые решения и ограничения: [subscription-entitlements.md](subscription-entitlements.md).
Текущая задача ещё проходит проверки; реальные SHA/run/attempt и deploy будут
зафиксированы в PR, прежние артефакты не подтверждают эту версию.


## Billing overview: backend 0.5.0 → 0.6.0, Windows 0.9.0 → 0.10.0

Новая возможность: авторизованный GET /billing/overview и read-only подключение
существующего экрана. Миграция 0023 добавляет группы/назначения, атомарный каталог с
периодами и неизменяемые снимки цены договора. Действующие права остаются общими с
/me и VPN; изменение каталога не меняет зафиксированную цену. Старые неизвестные
цены не заполняются задним числом. Каталог имеет разрешённые владельцем временные
цены 199 ₽/$2,99 (обычные 299 ₽/$3,99). Закрытый CLI, CAS, default-группа и точные
UTC-границы описаны в [subscriptions-ui.md](subscriptions-ui.md).

Схема/API additive, старые backend не используют новые таблицы. Для rollback
приложения оставлять схему 0023 и данные; downgrade до 0022 уничтожает каталог,
группы и снимки договоров и не является безопасным rollback данных. Снимки нельзя
переписывать при откате или заново вычислять из сегодняшнего каталога.

План проверки: backend format/lint/mypy/unit/integration/Alembic/image; Windows
format/types/lint/tests, новая native-сборка и replay реальных backend GET из CI.
Проверенные product HEAD, временный merge SHA, все workflow, скриншоты и фактические
development build SHA/run/attempt фиксируются в PR этой задачи после завершения
проверок. Наличие этого текста не доказывает deployment. Платежи выключены:
actions=[], payment_operations_available=false, operations endpoints отсутствуют.
Для будущих платежей остаются provider adapter/credentials, webhook confirmation,
идемпотентность, подтверждённые mandates и атомарный вызов lock_contract_price.


## Billing operations — backend 0.6.0 → 0.7.0; Windows unchanged 0.10.0

Миграция 0024, POST /billing/operations и GET /billing/operations/{id}. Durable
account-scoped keys, immutable quotes, частичный unique pending index, leased/fenced
provider reconciliation и append-only подтверждённые договоры. Существующие снимки
0023 не удаляются. Live provider/credentials не подключены: новые операции в обычном
runtime получают BILLING_DISABLED; статусы и повторы уже принятых запросов читаются
из PostgreSQL. Внешние/локальные неопределённые сбои остаются PENDING с тем же UUID.
Контракт adapter и закрытая сверка SUBSCRIPTION_CHANGED: docs/subscriptions-ui.md.

Проверки на тестовом provider используют изолированный ledger, настоящий PostgreSQL,
JWT/HTTP, гонки, crash/timeout/DB rollback, price revisions и подтверждение mandate.
Это не банковские списания. Точный проверенный HEAD, все CI runs/jobs, build SHA и
фактический development deploy/smoke после завершения фиксируются в PR этой задачи.
Для application rollback сохранять схему 0024/ключи/договоры. Downgrade уничтожает
финансовую историю/возможность идемпотентного восстановления и не является безопасным
rollback данных. Если остаются PENDING, сохранять совместимый reconciler и adapter:
старый backend 0.6.0 не умеет продолжать новые операции, поэтому предпочтителен
совместимый forward fix. Ни реальный платёж, ни live-provider webhook не включены.
