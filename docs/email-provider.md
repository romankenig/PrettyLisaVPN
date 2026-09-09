# EmailProvider и почта Timeweb

Backend использует SMTP почтового сервиса Timeweb. HTTP API отправки писем не предполагается: официальная документация Timeweb указывает SMTP-сервер `smtp.timeweb.ru`, авторизацию полным адресом ящика и пароль ящика. Для TLS доступны порт 465 с TLS сразу при подключении и порт 587 с STARTTLS:

- [настройки SMTP/POP3/IMAP Timeweb](https://timeweb.com/ru/docs/pochta/osnovnye-voprosy-po-rabote-s-pochtoj/osnovnye-nastrojki-pochtovyh-klientov/);
- [отправка почты через скрипты](https://timeweb.com/ru/docs/pochta/osnovnye-voprosy-po-rabote-s-pochtoj/otpravka-pochty-cherez-skripty/).

Production-конфигурация по умолчанию использует `smtp.timeweb.ru:465`, `implicit_tls`, проверку сертификата и SMTP-auth. Адрес SMTP-пользователя и From должен совпадать: `auth@prettylisavpn.com`. Письмо содержит plain-text и HTML без изображений, трекеров и внешних ресурсов.

## Переменные окружения

```dotenv
EMAIL_PROVIDER=timeweb
EMAIL_SMTP_HOST=smtp.timeweb.ru
EMAIL_SMTP_PORT=465
EMAIL_SMTP_TLS_MODE=implicit_tls
EMAIL_SMTP_USERNAME=auth@prettylisavpn.com
EMAIL_SMTP_PASSWORD=
EMAIL_FROM_ADDRESS=auth@prettylisavpn.com
EMAIL_FROM_NAME=PrettyLisaVPN
EMAIL_CONNECTION_TIMEOUT_SECONDS=5
EMAIL_SEND_TIMEOUT_SECONDS=10
```

`EMAIL_SMTP_PASSWORD` — единственный отсутствующий credential. Это пароль существующего ящика `auth@prettylisavpn.com`; его нельзя добавлять в Git, Dockerfile, Compose-файл или командную строку.

### GitHub Environment development

1. Откройте репозиторий GitHub → **Settings → Environments → development**.
2. В **Environment secrets** нажмите **Add environment secret**.
3. Имя: `DEV_EMAIL_SMTP_PASSWORD`.
4. Значение: пароль ящика `auth@prettylisavpn.com`.

Workflow переносит secret в защищённый `/etc/prettylisavpn/development.env` как `EMAIL_SMTP_PASSWORD`. После появления `POST /auth/request-otp` этот secret обязателен для development deployment.

### Production VPS

Добавьте строку через `sudoedit`, не передавая пароль аргументом команды:

```bash
sudoedit /etc/prettylisavpn/deployment.env
```

```dotenv
EMAIL_SMTP_PASSWORD=REPLACE_WITH_MAILBOX_PASSWORD
```

У файла должны остаться владелец `root:root` и права `0600`.

## Опциональный реальный smoke-тест

Обычные тесты никогда не отправляют почту. Smoke-тест запускается только при явном флаге и отправляет письмо на указанный адрес. В PowerShell из `backend/`:

```powershell
$mailbox = Get-Credential -UserName "auth@prettylisavpn.com" -Message "Timeweb mailbox password"
$env:EMAIL_SMTP_PASSWORD = $mailbox.GetNetworkCredential().Password
$env:EMAIL_SMOKE_RECIPIENT = "your-test-recipient@example.com"
$env:RUN_EMAIL_INTEGRATION_TEST = "1"
..\.tools\bin\uv.exe run pytest tests/test_email_provider_integration.py -q
Remove-Item Env:EMAIL_SMTP_PASSWORD, Env:EMAIL_SMOKE_RECIPIENT, Env:RUN_EMAIL_INTEGRATION_TEST
$mailbox = $null
```

Не включайте автоматический retry после тайм-аута: SMTP-сервер мог принять письмо до обрыва ответа, и повтор создаст дубликат.

## Диагностика

Windows-клиент по умолчанию ждёт ответ Backend 15 секунд: это намеренно больше
серверного `EMAIL_SEND_TIMEOUT_SECONDS=10`. Уменьшение
`VITE_BACKEND_TIMEOUT_MS` до значения не выше SMTP timeout приводит к ложной
ошибке сети, хотя Backend ещё отправляет письмо.

При отказе Backend пишет только безопасную категорию без адреса получателя,
OTP и SMTP-ответа:

- `otp_email_delivery_failed_authentication` — проверьте, что в
  `DEV_EMAIL_SMTP_PASSWORD` указан пароль именно почтового ящика, а не пароль
  аккаунта Timeweb;
- `otp_email_delivery_failed_unavailable` — проверьте DNS и исходящее TCP/TLS
  соединение VPS с `smtp.timeweb.ru:465`;
- `otp_email_delivery_failed_recipient_rejected` — SMTP отклонил получателя;
- `otp_email_delivery_failed_delivery` — прочий отказ SMTP.

После изменения GitHub Environment secret требуется новый deployment: уже
запущенный контейнер не получает обновлённое значение автоматически.
