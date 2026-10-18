# Тестовый платёжный адаптер — backend 0.8.0

Windows остаётся 0.10.0. Публичный billing-контракт совместим с backend 0.7.0;
новых HTTP endpoint нет. Никакой банковский сервис, SDK или credentials не нужны.
Адаптер имитирует результат, включая тестовый mandate, и никогда не списывает деньги.
Подтверждение в sandbox выдаёт настоящие локальные Premium-права: используйте
отдельную development/test базу, не production и не реальные коммерческие аккаунты.

## Запуск

1. Применить `uv run alembic upgrade head` (новая миграция `0025_billing_sandbox`).
2. Явно задать `ENVIRONMENT=development` (или `test`) и `BILLING_PROVIDER=sandbox`.
3. Запустить обычный backend: `uv run uvicorn prettylisavpn.main:create_app --factory`.
4. С Bearer-сессией запросить `/billing/overview`, затем отправить существующую
   команду `POST /billing/operations` с её актуальной revision и новым request UUID.

Операция всегда сначала `PENDING`, `redirect_url=null`. Внешняя платёжная страница
не открывается. Цена берётся только из сохранённой quote; сумма в уведомлении
не принимается. Backend worker опрашивает сохранённые операции штатным способом.
Windows UI остаётся read-only; этот шаг проверяется через billing API.

По умолчанию `BILLING_PROVIDER=disabled`: новые операции получают
`503 BILLING_DISABLED`, сохранённые GET/replay остаются доступны. В production,
staging и любом окружении кроме точных `development`/`test` включение sandbox
отклоняется при старте, в том числе при прямом внедрении адаптера.

## Тестовые уведомления

В том же окружении backend, с доступом к его development базе:

```bash
uv run python -m prettylisavpn.billing.sandbox OPERATION_UUID SUCCEEDED --event-id EVENT_UUID
uv run python -m prettylisavpn.billing.sandbox OPERATION_UUID FAILED --event-id EVENT_UUID
uv run python -m prettylisavpn.billing.sandbox OPERATION_UUID CANCELED --event-id EVENT_UUID
```

Выберите один исход для операции. `OPERATION_UUID` — ID из POST; `EVENT_UUID` —
новый UUID уведомления. Для повтора отправьте тот же ID события и тот же исход.
Другой ID с тем же итогом тоже безопасен. Противоречащий итог или повтор event ID
для другой операции отклоняется с rollback. Неизвестная операция не создаётся.
CLI требует явного `BILLING_PROVIDER=sandbox`; публичных управляющих endpoint нет.

`FAILED`/`CANCELED` завершают попытку оплаты без выдачи доступа. Для отмены
автопродления сначала создайте обычную команду `action=CANCEL`, затем подтвердите
её уведомлением `SUCCEEDED`. Адаптер подтверждает остановку recurring и отзыв
тестового mandate; оплаченный срок сохраняется. RENEW продлевает календарный
месяц один раз. CRYPTO/ALIPAY_WECHAT не получают recurring mandate.

## Перезапуск и сбои

`billing_sandbox_payments` хранит исходный provider request и результат, ключ —
неизменный operation UUID. `billing_sandbox_notifications` сохраняет уникальные
event UUID. Запись receipt коммитится независимо от локальной settlement-транзакции.
Для симулятора обе таблицы находятся в той же PostgreSQL, но не в памяти процесса.
Повтор reconcile с изменённой суммой/аккаунтом/командой запрещён.

После notification процесс можно остановить до локального применения. После
перезапуска обычный worker найдёт receipt и применит его ровно один раз. Уведомление
не снимает чужой lease: после падения worker требуется его штатное истечение
(до 30 секунд), затем очередной проход. Повторы и сбои не создают новый платёж.
Если вручную изменена подписка, сохраняется прежнее поведение
`PENDING/SUBSCRIPTION_CHANGED` для закрытой сверки.

Не выключайте/не заменяйте адаптер, пока есть его PENDING-операции: сначала
подтвердите/отклоните тестовые попытки и дождитесь settlement. При временном
отключении receipts остаются в БД; включите то же имя `development-sandbox-v1`
для восстановления. Не удаляйте миграции 0024/0025 и данные идемпотентности при
откате приложения. Тестовые receipts/events удаляются каскадно вместе с аккаунтом.

Проверки: `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`,
`uv run pytest -m 'not integration and not docker'`; с PostgreSQL/Valkey и
применёнными миграциями — `RUN_INTEGRATION_TESTS=1 uv run pytest -m integration`.
Точные SHA, CI run/attempt и артефакты фиксируются в PR. Наличие тестов не означает
успешный прогон или deploy. Настоящий provider, webhooks, банковские mandate,
возвраты, production deploy и native Windows интеграция остаются отдельными задачами.
