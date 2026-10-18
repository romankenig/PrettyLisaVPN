# Проверка development deploy, rollback и restore — 2026-10-18

PR [#7](https://github.com/romankenig/PrettyLisaVPN/pull/7) слит с явного разрешения
владельца. Deployed source SHA:
`35fec3ae6ddd3cbe7c3d0f9072db3c0a5f61ccb1`.
Backend package version остаётся `0.1.0`; изменился runtime-идентификатор и CI/deploy tooling.
Код приложения, migrations, pyproject, uv.lock и Dockerfile совпадают с прежним backend.

## Итоговое состояние

На `https://api.prettylisavpn.com` восстановлена новая версия:

```text
0.1.0-dev.39083503869+g35fec3ae6ddd3cbe7c3d0f9072db3c0a5f61ccb1
```

Запущенный образ:
`sha256:50c3296eca3b5acfec5f9ced1a884404ad9359568d42dd70195ccf254cdd9568`.

Тег:
`prettylisavpn-backend:35fec3ae6ddd3cbe7c3d0f9072db3c0a5f61ccb1-run-39083503869-attempt-1`.

Финальный backend container: `79d83fddc528`, healthy.
Canonical env и symlink current сверены с новым сохранённым релизом после restore.
Восстановление завершилось с первой попытки.

## Реальные наблюдения на VPS

| Этап | Время UTC | Backend container | Image ID (кратко) | HTTP health / ready / version |
| --- | --- | --- | --- | --- |
| Новый deploy до отката | 00:43:15 | 48d2dac0f55f | 50c3296eca3b | 200 / 200 / 200 |
| Rollback | 00:43:25 | 183d112d769d | 51b825d271f2 | 200 / 200 / 200 |
| Restore | 00:43:35 | 79d83fddc528 | 50c3296eca3b | 200 / 200 / 200 |

Во время rollback реальный `/version` вернул
`dev-1938d4d32eb58fd097e7c8840f695b735ec86b8f`, а запущенный image ID точно совпал
с прежним preflight:
`sha256:51b825d271f21e3555045d9dc5a9c4146ded8795e7ce505fead89ca14c7a4d11`.

На каждом этапе PostgreSQL и Valkey доступны, public environment — development.
Реальный `alembic current` на каждом этапе — `0017_profile_evidence`.
Rollback и restore вызвали deploy.sh в режиме rollback: без pull, rebuild,
upgrade или downgrade миграций. При обычном новом deploy штатный Alembic upgrade head
выполнялся; текущая схема уже была на head.

Резервная пара legacy env/Compose сохранена только на VPS в закрытом каталоге:
`/opt/prettylisavpn/rollback-baselines/39083783546-attempt-1`.
В ней использован новый deploy driver для поддержки rollback без миграций.
Исходный legacy Compose-каталог сохранён по прежнему пути releases/1938d4d....
Новая поставка также хранит previous.env, previous-image-id и previous-release.
Значения credentials в этот отчёт и Actions artifacts не включались.

## SHA, CI и доказательства

- [Backend push / development-deploy 39083503869](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39083503869):
  completed/success, source/build SHA `35fec3ae6ddd3cbe7c3d0f9072db3c0a5f61ccb1`,
  attempt 1. Quality job и Deploy development завершились success.
  Development deploy подтвердил новую runtime-версию в 00:40:26 UTC.
- [Development API probe 39083503895](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39083503895):
  completed/success для того же merge SHA. Этот push-probe мог выполниться до deploy;
  доказательство новой версии после deploy — следующий реальный цикл.
- [Verify approved development rollback 39083783546](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39083783546):
  completed/success, source проверки
  `e4f7600051468d678626393e49416517ff8b609d`, attempt 1.
  Этот operational SHA отличается от deployed product SHA и не меняет приложение.
- [JSON artifact](https://github.com/romankenig/PrettyLisaVPN/actions/runs/39083783546/artifacts/12119823173):
  `development-rollback-verification-39083783546-1`,
  digest `sha256:d4c71e1ae18e908d3c1d6d63e05d65013c6e84ce1dfbeb95738d7a54e5b7e9da`.
  Содержимое отчёта также сохранено в [evidence JSON](evidence/runtime-rollback-2026-10-18.json).

После merge прошли Ruff formatting/lint, mypy, 322 unit tests, 64 integration tests,
все 17 миграций на изолированной CI PostgreSQL, alembic check без новых операций,
сборка образа и 8 Docker tests. Один real-SMTP integration test намеренно skipped;
реальные письма не отправлялись. Верификатор прошёл три standard-library теста
обязательного restore, включая неуспешный rollback и неуспешное восстановление.

Для merge SHA получен общий список Actions runs: ровно два, одна страница per_page=100;
оба completed/success. Checks API: Quality, Deploy development, Public API probe —
все success. Обе check suites success, commit statuses пусты.
Для operational SHA проверяется отдельный одноразовый workflow. Документирующий
commit после проверки не меняет verified operational/product source и по path filters
не запускает повторный rollback.

## Организация проверки и оставшиеся ограничения

Workflow опубликован только в операционной ветке `cloud/verify-runtime-rollback`;
он сериализуется с Backend/develop и ограничен явно разрешённым VPS, ED25519
host key и точным deployed source SHA. Перед изменением проверяет оба retained
image ID, точный env и совпадение Compose файлов. После начала отката всегда
пытается вернуть новую версию; ошибка rollback не маскируется успешным restore.

SSH и Docker-команды выполнены на VPS через существующие secrets GitHub Actions.
Ключи не переносились в Cloud или чат. Ограничение прямой сети и Docker socket
в самом Cloud остаётся отдельной проблемой среды; оно не препятствовало этому
реальному development deploy/rollback через Actions.
