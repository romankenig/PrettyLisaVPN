# Android 0.7.0: главная, устройства и поддержка

Исходный HEAD `7b0ab53038ec77020a23f85acb7811334b0b67d7`, продолжение PR #25.
Android 0.6.5/code11 → 0.7.0/code12 (MINOR: переработка экранов/вложения/диагностика).
Windows 0.12.0, backend 0.10.0/schema0026 и контракты unchanged.

## Сверка с Windows

Home.tsx/AccountSummary: аккаунт, план и число активных устройств показаны
отдельными подписями/значениями. Лишнего ряда refresh/devices/subscription/
messages/support/logout на Windows Home нет; Android переносит управление в
Settings и About. Повторный большой логотип убран, общий header остаётся.
ConnectionLocationSelector.tsx: автопилот, ручная страна, top/all countries;
Android читает существующий GET /vpn/countries и локализует названия стран.
Выбор — только локальное состояние UI. Connect активен и намеренно ничего не
создаёт/не подключает; подпись прямо сообщает preview. Not connected остаётся.
TrafficMode.tsx: весь трафик выбран, include/exclude пока disabled/скоро.
CurrentLocation.tsx: реальный публичный egress через тот же https://ipwho.is/,
без auth headers, cookies, координат или истории. Страна/город/IP валидируются,
обновляются на Home раз в минуту, не сохраняются. При ошибке — unavailable.
Это адрес текущей сети, не выбранного VPN узла; новый VPN runtime отсутствует.

Settings.tsx/NavigationIcon.tsx: иконки подписки/устройств/выхода перенесены в
Android vector, поясняющий текст, красный выход. Messages доступны отдельным
пунктом Settings, Support — прежним CTA About. Refresh Home выполняется при входе.
Устройства: имя, текущая установка, статус, id, added/last login. Instant UTC
форматируется в язык UI и системную timezone; null не превращается в текущую дату.
Обновление — pull вниз в начале списка или вверх в конце, плюс accessibility
custom action; видимой кнопки refresh нет. Revoke сохраняет прежний confirmation.

## Почему возникали несколько устройств

Раньше стандартная debug-подпись создавалась заново на runner, поэтому очередной
APK часто требовал удаления предыдущего. installation.id лежит в noBackupFilesDir
и удаляется при uninstall: следующий OTP регистрирует новую установку. По одному
названию Samsung нельзя безопасно доказать, что это один физический телефон.
Теперь apps/android/debug.keystore — явно публичный тестовый ключ с обычными
android/androiddebugkey реквизитами, только для debug. Он не является секретом
и никогда не используется в release (release по-прежнему unsigned). Стабильная
подпись позволяет будущие adb install -r/обновления поверх APK.
KeystoreVault сначала сохраняет существующий UUID, затем для новой установки
использует UUID из app package + scoped ANDROID_ID. Сам ANDROID_ID не отправляется.
Это scope signing key/Android user/device; при отсутствии валидного ID fallback
случайный. Logout очищает только credentials. Смена signing key, профиля Android,
сброс устройства остаются новой установкой. Переход со старого случайного CI-ключа
требует однократной переустановки; старые серверные записи не удаляются, не
объединяются и не скрываются. Пользователь может отозвать старые установки через
обычное подтверждение; реальный аккаунт автоматические проверки не изменяют.

## Поддержка

SAF остаётся без storage permission. После выбора проверяются MIME/декодирование,
5 МБ на файл, 10 МБ суммарно и максимум 3. Отдельные строки: display name (не путь),
подготовка/ready/error, размер, крестик удаления. Состояние ready означает готовность
к отправке, не уже выполненную загрузку на сервер. Во время POST прогресс отражает
реальные байты multipart, без логирования содержимого. Transport использует прежние
анонимные screenshot-N имена. Busy блокирует изменения/Back; неопределённый исход
сохраняется в encrypted account journal и восстанавливается по тому же request_id.
URI сохраняются только в navigation draft с persistable grants; при freeze/discard
права отпускаются, receipt сохраняет display names. После process recreation
подготовка повторяется, а принятый запрос не отправляется повторно.

На форме только одна отправка; Done убран также на receipt, возвращает Back.
Status/retry/New request остаются разными recovery действиями прежнего контракта.
Текст пояснения приведён к строчному стилю во всех 6 языках, пользовательский ввод
и бренд не преобразуются.

Diagnostics.platform backend сейчас Literal[WINDOWS]. Android собирает реальный
allowlist: collected UTC, frontend/backend version, Android API, язык/timezone,
план, тип сети и недоступность VPN runtime. Checkbox opt-in и preview видимы.
Без credentials/session/device IDs, email, IP/SSID, путей или browsing history.
Диагностика добавляется к description, structured diagnostics остаётся null:
без backend изменения и без ложного WINDOWS. Общий лимит description 4000 соблюдён;
если текст не помещается, UI просит сократить его. Frozen journal хранит точный
техблок исходного запроса, retry его не пересобирает. Future backend follow-up:
если нужен отдельно типизированный ANDROID diagnostics, расширить schema отдельной
задачей; текущая отправка техданных уже работает через существующий текстовый API.

## Приёмка и продолжение

Локально: 6 catalogs parity/строчный стиль/бренд/термины, XML references, shell syntax.
SDK/emulator локально отсутствуют: GitHub Actions собирает текущий checkout,
JVM/lint/isolation и API26/35/36 native. AccountScreensTest проверяет новый LiveHome,
settings/devices refresh/date/revoke, safe Connect preview, Support file name/cross/
diagnostics/Back без реальных писем. Тестовый ContentProvider находится только в
test APK и создаёт синтетический PNG. Остальные session/payment/idempotency тесты
сохраняются. Keystore test проверяет восстановление installation UUID при удалении
локального identity file с тем же signing scope и logout retention. MockWebServer
проверяет /vpn/countries, public egress и фактический multipart byte progress.
Точные product/build SHA, run/attempt, APK/native artifacts и статусы всех jobs
фиксируются в PR #25 после CI без нового docs-only push. Реальных писем, платежей,
VPN, merge/release/deploy эта задача не выполняет.
