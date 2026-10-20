# Android 0.3.0: экраны на изолированных данных

Самостоятельная задача: Android **0.2.0/code 2 → 0.3.0/code 3**.
Эталон — Windows **0.12.0** на develop
`41feac69f92828d450d99d65a634d5400922a97f` (после Android design PR #22).
Windows **0.12.0**, backend **0.10.0**, schema **0026** не меняются.
Точные проверенные source/build SHA, CI run/attempt, APK и native PNG записываются
в описании task PR после CI; наличие этого документа не означает успешную приёмку.

## Что реализовано

| Windows-контракт | Android / поведение |
| --- | --- |
| Login / OTP | Email validation, test-only request, 6 digits, invalid/expired, resend 30s, change email. Код 123456, 000000 показывает expiry. Письмо не отправляется. OTP не сохраняется при recreation; email остаётся только в памяти ViewModel. |
| Home | Аккаунт, план, число активных устройств, страна, карточки, all traffic / disabled split modes. Кнопка **simulate connection**, постоянный **TEST DATA · NO VPN TUNNEL**, активный статус **SIMULATION ACTIVE — NOT A VPN**. |
| Country selector | Autopilot, поиск, качество, disabled unavailable countries; Free выбирает только AUTO. Нет backend/node selection. |
| Public location / connection info | Отдельные loading/error/refresh; документационный IP 192.0.2.10 и synthetic location. Диалог прямо говорит об отсутствии tunnel/handshake/route/verification; реальные runtime counters не выдумываются. |
| Settings / devices | Подписка/устройства/logout; UUID/имя/current/added/nullable last login; revoke confirmation, cancel/Back, ошибка/повтор, обновление Home. Отзыв current завершает только тестовую сессию. |
| Subscription / PaymentChoice | План, оплаченная дата, auto-renew, method, пример RUB/USD, четыре маршрута и recurring. Подписка/продление/замена/отмена **явно симулируются**. CANCEL/CHANGE_METHOD сохраняют дату; RENEW добавляет период один раз; delayed confirmation и failure не начисляют период раньше времени. |
| AccountMessages | Очередь из двух синтетических сообщений; Later/Back не ACK; ACK привязан к id/revision. Ошибка ACK не открывает destination; поддерживаются только внутренние SUBSCRIPTION/ABOUT, без произвольных URL. |
| About / Support | Версия Android/source; Backend unavailable, GET /version не вызывается. Полноэкранный support draft, validation/recreation, synthetic attachments (до 3), discard dialog, local receipt/status. Отправки/SAF/реальных вложений нет; Android diagnostics disabled. |
| Errors/loading/empty/stale | Отдельные состояния read и mutation; retry, disabled duplicate actions, empty lists и stale notice. Debug gallery содержит Standard/Slow/Free/Expired/Platinum/Empty/Device limit/Stale/Offline/Fail next/Payment pending. |

Это перенос смысла действий и структуры Windows, с мобильными экранами и системными
AlertDialog. Desktop chrome и Win32 не переносятся. Брендовая тема/Rubik/logo из
[0.2.0](android-design.md) сохранены; safeDrawing/IME/scroll и крупная навигация сохранены.
Базовые подписи теперь English. **Шесть языков и авто-RU ещё не реализованы**:
эта задача выполняет запрошенный этап экранов до отдельного locale foundation.
[Локализация](android-localization.md) остаётся отдельной задачей, рекомендуемая
следующая версия 0.4.0/code 4. Это явное ограничение паритета Windows 0.12.0.

## Изоляция и жизненный цикл

`ScreenSource` в main — заменяемый UI port; DTO и команды не являются новым API.
`FixtureSource` находится исключительно в **src/debug**. `src/release` содержит
отдельную фабрику disabled source; release показывает unavailable, не тестовый аккаунт.
CI собирает обе variants и проверяет отсутствие FixtureSource в release dex.
Manifest не запрашивает INTERNET/VPN/файловых разрешений; VpnService, HTTP-клиент,
платёжные redirect/реальный sender отсутствуют. Fixture UI не использует development API.

ViewModel владеет состоянием и coroutine scope; повторные mutation clicks блокируются.
Rotation не повторяет команду; epoch отбрасывает устаревшие read results при смене
сессии/сценария. Support draft принадлежит navigation entry; Back/Discard удаляет
его. Receipt и незавершённые debug-операции живут в памяти ViewModel, не на сервере.
После process death возвращается исходный тестовый аккаунт — **это не восстановление
настоящей auth/VPN/payment операции**. Fixture имеет фиксированное время 2026-10-20 UTC.
Все цены/UUID/email/локации синтетические, не коммерческий каталог и не личные данные.

Back сначала закрывает системный диалог/IME, затем вложенный экран, затем возвращает
Home из Settings/About. Уход с Home не означает stop simulation. После logout/auth
back stack очищается; OTP/email не попадают в route URI. Сетевой fake failure не
считается успешным logout/revoke/ACK/send. Закрытие диалога не отменяет уже начатую
команду; ViewModel доводит её до результата без повторного применения.

## Проверки

- 5 JVM tests: once-only renewal, cancel/method paid date, delayed confirmation/failure,
  currencies/Free entitlement, current-device revoke, message revision, support receipt
  idempotency и явный ephemeral restart.
- 3 NavigationTest, 9 ScreenFlowTest (реальный GLOBAL_ACTION_BACK, auth/recreation,
  dialogs/cancel/fail/retry, late response after Back, loading, страны, устройства, billing, support, messages,
  offline/stale/empty), 3 DesignAcceptanceTest × 6 конфигураций.
- Матрица API 26/35/36; 320/360/412dp, 130%/200% fonts, landscape и настоящая IME.
  Native PNG: baseline, flows и design cases; source identity/APK digest, runtime/ANR guards.
- Debug/release build, JVM tests, lint обеих variants, source isolation guard.

Скриншоты и тесты этого этапа не доказывают реальные OTP/VPN/платежи/SMTP, handset
routing, TalkBack или все OEM. Backend/Windows/инфраструктура в diff не меняются.
