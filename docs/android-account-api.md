# Android 0.5.0: account API

Android **0.4.0/code4 → 0.5.0/code5**, новая самостоятельная задача поверх auth/session
в ещё открытом PR #24. Windows 0.12.0 и backend 0.10.0/schema0026 unchanged.
Base product SHA `abd3d45c90eaa9935c17dd11bf9ed15ebb5f0e79`.
Итоговый product/build SHA, run/attempt, статусы и артефакты — в PR после последнего CI.

Пользователь сообщил, что на сборке 0.4.0 OTP-письмо пришло и вход в аккаунт сработал.
Это ручная проверка владельца; автоматические тесты не выдаются за настоящий вход.

## Реализованные маршруты

| Экран | API и действие |
| --- | --- |
| Home/profile | GET /me: effective plan, email, active_device_count; refresh и foreground проверка сессии |
| Settings/devices | GET /devices, DELETE /devices/{id}; confirmation, UUID/current/created/nullable last_login_at; /me и список после отзыва |
| Account messages | GET /messages?platform=ANDROID&app_version=0.5.0&locale=en&schema_version=1; paragraph/list/fallback; ACK id+revision; internal action после успешного ACK |
| Subscription | GET /billing/overview; серверные RUB/USD offers, current price, даты, auto-renew, payment method, четыре route capabilities |
| Payment operations | POST /billing/operations, GET /billing/operations/{id}; admission через LIVE/availability/actions/routes/currency и свежую revision |
| Support | multipart POST /support/requests, GET /support/requests/{request_id}; diagnostics:null, optional selected PNG/JPEG/WebP |

После авторизации доступны Home/Settings/About с прежними Rubik, палитрой и карточками.
Вложенные экраны имеют Back; при logout/current-device revoke auth guard уничтожает
account navigation/drafts. Отзыв своего устройства очищает secure auth credentials.
Сообщения имеют Later без ACK; navigation action ограничен SUBSCRIPTION/SETTINGS/ABOUT.
Неправильный receipt не считается успешным ACK. Ревизии и nullable last_login_at не
подменяются локальными значениями. Ошибка обновления после подтверждённого действия
показывается отдельно: завершённая мутация не объявляется неудачной для повтора.

## Идемпотентность и восстановление

SessionCoordinator сериализует Bearer/refresh и authenticated API; LiveSessionSource
сериализует projections и действия. Tokens остаются вне UI и account journal.
Общие 401 после истечения bearer допускают один bounded refresh; terminal auth errors
очищают сессию. Ошибки отображаются по закрытым code mappings, без сырых HTTP bodies.

Если encrypted journal недоступен или повреждён, новые support/payment POST запрещены
до успешного восстановления; UI предлагает повтор secure recovery.

AccountJournal — AES-256-GCM, отдельный AndroidKeyStore alias, AtomicFile в
noBackupFilesDir. account user UUID ограничивает восстановление: записи другого
аккаунта удаляются. Logout очищает journal. Поддержка сохраняет immutable UUID,
subject/description/reply_email и bytes выбранных файлов ДО первого запроса. После
restart UI предлагает status/retry того же запроса; изменённый черновик не подменяет
его payload. Только явный 404 status разрешает POST; timeout/503 не считаются absence.
ACCEPTED/RETRYING не показываются как SENT. Новый запрос после terminal receipt —
отдельное явное действие. Диагностика backend пока WINDOWS-only: Android отправляет
null, без изменения backend-контракта и без fake WINDOWS.

SAF OpenMultipleDocuments не требует broad storage permissions. До трёх PNG/JPEG/WebP,
5 MiB каждый, 10 MiB всего, 12 MP/8192px; raw filenames не передаются. На повторе
используются сохранённые bytes, а не изменяемый внешний URI. Backend заново проверяет
и очищает raster metadata. Успех отправки письма определяется только серверным SENT.

Платёжный UUID, expected_revision и payload сохраняются до POST. Потерянный response
не создаёт новый request_id; pending receipt восстанавливается GET и из overview.
Перед новой операцией overview запрашивается заново; смена revision требует повторного
подтверждения. Retry pending intent использует старые условия, а не текущую цену.
Локальные paid dates не начисляются; источник срока — backend overview, включая
сохранение срока при CANCEL/CHANGE_METHOD. Внешний HTTPS provider URL открывается
только явным действием пользователя, не автоматически.

**DISABLED и SANDBOX запрещают все платёжные POST и открытие provider URL**, даже
если ответ ошибочно содержит actions и payment_operations_available=true. Проверки
повторяются в data layer. Отсутствующие capabilities fail closed. Pending status
можно прочитать без нового списания. LIVE дополнительно требует разрешённое действие,
четыре уникальных route capabilities и доступную валюту; реальный provider не настраивался.

## Проверки и ограничения

JVM tests используют local MockWebServer и in-memory API/journal: wire contracts,
Bearer/refresh, ACK/revisions, revoke/profile refresh, frozen support retries/status,
account isolation, price revision, payment gates и immutable intent after restart.
Native API26/35/36 проверяют навигацию, Back/confirmation, ошибки, disabled/sandbox,
receipt/recreation, actual Keystore journal encryption/tamper; сохраняются прежние
OTP/session, process restart и design/IME/fontScale тесты. Native screenshots в CI.
Автоматические проверки не запрашивают настоящие OTP, не вызывают SMTP и не отправляют
обращения/платёжные команды на development. Нет реальных списаний или привязок.

VPN runtime, страна/реальный IP и шесть языков остаются отдельными задачами.
Screen fixtures доступны только debug instrumentation, не смешиваются с real account.
