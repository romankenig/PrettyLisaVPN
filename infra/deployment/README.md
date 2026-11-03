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

## Public draft website

The owner authorized publishing the website on https://prettylisavpn.com and then
requested the minimalist 0.2.0 revision. The current prelaunch site has one launch
notice, six languages, four documents and public downloads. Commercial payment
activation remains separate; noindex is retained. Backend/client versions do not
change and this publication does not imply provider approval.

Caddy serves allowlisted static routes from `/srv/public-website/current`, mounted
read-only from `PUBLIC_WEBSITE_DIR` (default `/opt/prettylisavpn/public-website`).
The host directory contains `releases/<source SHA>-<run>-<attempt>` and a **relative**
`current` symlink, so atomic selection works inside the container. Never place
credentials in this directory. Only verified CI website artifacts belong here.

`/payment/success`, `/payment/failure` and their existing assets still proxy to the
backend. `/support` redirects to `/#help`, `/setup` to `/#download`. Checkout POST returns
503 / `WEB_CHECKOUT_DISABLED`; unknown and private API/dashboard paths remain 404
on the apex domain. API-domain dashboard authentication is unchanged. Public-host
access logs stay disabled, and security/no-store/noindex headers cover the website.

Public GET/HEAD `/downloads/{android.apk,windows.exe,android-sources.tar.gz,
windows-sources.tar.gz,windows-licenses.txt,index.json}` reads the existing verified
client publisher's `downloads/current` snapshot through the read-only dashboard
mount. This is an exact file allowlist, not a public dashboard root. No other paths
or methods expose it; API-host dashboard authentication remains unchanged. Client
updates through `publish_client.py` update both download channels automatically.
The browser ignores URL fields in `index.json` and uses fixed public file paths.

Before first activation, validate the candidate Caddyfile and run
`python3 sites/public-website/tests/test_caddy.py` against the built artifact.
The test uses a disposable container with `--network=none`, checking all pages,
assets, payment denial, removed-provider/private paths and preserved return routes.
It never binds host ports or touches the production container.

For the initial publication, retain the active Caddyfile/compose pair and container
identity in `/opt/prettylisavpn/website-deployments/<deployment id>`, install the
verified artifact under the separate website root, add the read-only mount, validate
Compose/Caddy and recreate **only Caddy** with `--no-deps --pull never`. Preserve the
existing deployment env, dashboard directory, ACME volumes and backend containers.
Record source/build SHA/run/attempt, URL, verification results and backup directory
in PR50. Build metadata's `deployment` value is a build-time fact, not a live status.

Rollback of the initial proxy change: restore the backed-up Caddyfile and compose,
then recreate only Caddy using the same project/env/dashboard settings. Rollback
of later static revisions: atomically point `current` at a retained relative
release path. No database rollback or payment activation is involved.

Website files survive backend releases. Until this PR's proxy configuration is
merged, deployment of an older backend branch can restore the former apex routing;
review that config before another deployment. This publication does not authorize
merging PR50. Its tested HEAD and actual deployment evidence remain separate.

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
