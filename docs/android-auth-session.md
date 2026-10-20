# Android auth/session — 0.4.0

Android 0.3.0/code3 → **0.4.0/code4**: существующие auth/session API вместо
синтетического входа при обычном запуске. Windows 0.12.0, backend 0.10.0/schema0026
unchanged. Base: develop `454014cb6dc5e0a2d4208622cd06f662d0f5fbaf` (PR #23).
Проверенный product SHA, build SHA/run/attempt, APK и итоговые статусы CI фиксируются
в task PR после последнего push. Это не production release/deploy.

## Контракт и границы

Обычные debug/release используют HTTPS `https://api.prettylisavpn.com/` — существующий
**development** backend. При чистой установке сеть не вызывается до действия пользователя.
Запрос письма происходит только через Continue/Resend; автоматического письма нет.

| API | Android |
| --- | --- |
| POST /auth/request-otp | email; accepted, invalid input, rate limit, unavailable; cooldown 30s |
| POST /auth/verify-otp | email/code, постоянный installation UUID, ANDROID, manufacturer/model |
| POST /auth/refresh | session_id/refresh_token, сериализованная rotation, новая пара до /me |
| GET /me | подтверждённые email, effective plan и active_device_count; дополнительные поля допускаются |
| POST /auth/logout | Bearer; локальная очистка только после receipt либо подтверждённой недействительности сессии |

Один OkHttp client, TLS-проверка штатная, cleartext/redirects/connection retries
запрещены. Deadline 15s, connect 10s, response ≤64KiB. Ошибки из закрытого набора
machine codes; сырые тела/сетевые исключения не показываются. Нет HTTP logging.
Bearer прикрепляется только к запросам /me и logout на фиксированную API-базу.
OTP/verify/refresh автоматически не повторяются. После invalid_access_token возможны
одна rotation и один повтор исходного authenticated запроса.

Реальный режим показывает auth и account shell: профиль, refresh, sign out,
недоступный VPN. Отдельный shell исключает смешение реального аккаунта с вымышленными
Premium, IP, устройствами, сообщениями, платежами и поддержкой. Их API-интеграция —
следующие задачи. VPN/tunnel, реальные платежи/привязки и backend не менялись.
Шесть языков ещё не реализованы; номер будущей локализации следует выбирать от
фактической версии, а не резервировать 0.4.0.

Прежние offline screens остаются debug-only `FixtureSource`. Их включает только
instrumentation runner в процессе тестов. Обычный launcher использует API; release
не содержит FixtureSource или переключателя тестовых сценариев.

## Сессия и безопасность

- Access token и OTP только в памяти; OTP не попадает в SavedStateHandle, preferences,
  bundle или backup. Activity recreation очищает OTP, но сохраняет ViewModel/операцию.
- KeystoreVault: AES-256-GCM, случайный nonce, AAD/version, AndroidKeyStore key.
  session_id/refresh_token/expires_at/pending marker — один encrypted AtomicFile в
  noBackupFilesDir. allowBackup=false, cloud backup и device transfer исключены.
  Installation UUID сохраняется отдельно там же и переживает logout; это не секрет.
- Один process-wide SessionCoordinator, Mutex на login/refresh/me/logout. Параллельные
  запросы с истёкшим bearer выполняют одну rotation. Старая операция не воскресит logout.
  TTL bearer измеряется монотонными часами с 5s запасом; refresh expiry — UTC.
- Новая refresh-пара записывается до публикации авторизации и /me. Offline после
  успешного verify не требует повторно использовать уже потреблённый OTP: UI предлагает
  retry восстановления. Данные аккаунта не публикуются до успешного /me.
- До refresh атомарно сохраняется pending marker. DNS/connect failure и подтверждённый
  service_unavailable снимают marker и допускают retry. Timeout/обрыв/невалидный ответ,
  process death во время rotation или ошибка записи новой пары требуют reauth и не
  повторяют старый token. Backend не обещает recovery после потерянного rotation response.
- invalid_refresh_token/invalid_session/device_revoked/user_blocked очищают память и vault.
  Проверка /me выполняется при возврате Activity на передний план и вручную; push-уведомления
  об отзыве и фоновый polling не добавлялись. Нет обещания немедленного обнаружения offline.
- Offline/неподтверждённый logout не показывается успешным и сохраняет credentials.
  Повтор после фактически исполненного logout распознаёт invalid_session и очищает vault.
- Ошибка/утрата Keystore key, повреждение ciphertext или запрет secure storage приводят
  к закрытому состоянию. Retry либо явное Remove local session → новый OTP; локальное
  удаление не называется server logout.

## Проверка

JVM: HTTP-контракт через MockWebServer, Android platform/installation, Bearer scope,
redirect isolation, ошибки/невалидный ответ; coordinator с управляемыми часами и
заменяемыми API/vault — expiry, concurrent rotation, revoke/block, offline retry,
503, потерянный response, pending restart, secure-write failure, logout races и
OTP, потреблённый до сбоя /me.

На API 26/35/36: actual Keystore encrypt/decrypt, свежий nonce, tamper rejection,
clear/installation; force-stop между двумя instrumentation process для durable marker;
реальный auth shell на подменном AuthApi (restore/offline/revoke/logout/recreation).
Сохраняются прежние navigation/flow/design/IME/fontScale тесты и native screenshots.
CI проверяет debug/release, lint, JVM tests и отсутствие fixtures в release.

Все автоматические сценарии используют синтетические credentials и локальный server/port;
письма реальным людям не отправляются, пользовательские credentials не входят в evidence.
Настоящий email OTP и сквозной вход на development с ручным кодом — отдельная приёмка,
результат автоматических тестов не считается таким входом. Тесты Keystore запускаются
на одноразовом эмуляторе и очищают test-app vault; не запускать их на личной установке.
