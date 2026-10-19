# Development deployment

Штатная выкладка выполняется workflow [Backend](../../.github/workflows/backend.yaml).
Job `Deploy development` запускается после успешных quality/tests/migrations/image
на push в `develop`, когда `DEV_DEPLOY_ENABLED=true`. Секреты берутся из GitHub
Environment `development`; SSH проверяет known_hosts. Не переносить секреты в git.

Push-фильтр охватывает `backend/**`, `infra/docker/**`, `infra/deployment/**`
и сам workflow. Изменения только Windows не запускают backend deployment.
Текущий `workflow_dispatch` запускает проверки, но deploy-job ограничен push.

Runtime identity формируется [runtime_version.py](runtime_version.py) из версии
backend, SHA, run и attempt. Проверять фактические health/readiness/version и
результат post-deploy smoke checks; успешное слияние само по себе не доказывает
выкладку. Сведения о run/runtime и конечные результаты сохранять в PR, чтобы
документированием результата не запускать повторный deploy.

Конфигурация: [compose.yaml](compose.yaml), [.env.example](.env.example),
[Caddyfile](Caddyfile), [deploy.sh](deploy.sh).
Общий контекст: [backend handoff](../../docs/backend-cloud-handoff.md).

## Выкладка после Windows acceptance — 2026-10-19

Владелец поручил merge и development deployment PR #17. Merge commit:
`8e9ac69b9bea5ec7ac1c3e35f7eab47e85e232f7`.
Проверенный Windows source HEAD:
`4452327e6904a1cbf520f3088f908f51e453e00d`.

Windows: **0.11.1**, backend: **0.10.0**, schema: **0026**.
Эта запись — docs-only; version unchanged. Backend application code не менялся;
его новая runtime identity после выкладки определяется фактическим workflow run.
Windows binary собирается отдельно в Windows UI review; backend deploy не
устанавливает приложение на пользовательские компьютеры.

До слияния успешно завершены все три workflow, пять jobs/check-runs и три suites.
Прошли 339 frontend tests, 2 native Rust tests, 65 sandbox payment integration
scenarios и 8 native Windows flows против development HTTPS; девять API endpoint
вернули 200. Native screenshots и точные run/artifact IDs приведены в
[PR #17](https://github.com/romankenig/PrettyLisaVPN/pull/17).

OTP остаётся на паузе по решению владельца. Доставка поддержки и WireGuard data
plane не объявляются проверенными. Реальный платёжный провайдер не подключается;
его отдельная будущая задача —
[issue #18](https://github.com/romankenig/PrettyLisaVPN/issues/18).
См. [границы приёмки](../../docs/windows-development-acceptance.md).
