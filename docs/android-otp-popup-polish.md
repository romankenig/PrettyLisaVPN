# Android 0.7.2: OTP, метка устройства и popup

Версия: Android 0.7.1/code13 → 0.7.2/code14 (PATCH доработки UI).
Windows 0.12.0/backend 0.10.0/schema0026 unchanged; API обратно совместим.
Ветка feat/android-language-header, PR #25 → develop.

OTP: monotonic resend deadline увеличен с 30 до 60 секунд, верхний предел
отображаемого счётчика также 60. Поворот/язык/change email сохраняют deadline.
Новый отсчёт запускается только после успешного request OTP. Автотест использует
изолированный AuthApi и ждёт реальный monotonic deadline, писем нет.

Current-device badge: Heliotrope #ac73ff с текстом Christalle #2c016d,
нет click semantics, сохраняются крупный текст/первое место/ACTIVE-only.
Бирюзовый Viking остаётся у действий.

Сверено с apps/windows/src/ui/AccountMessages.tsx: после авторизации GET /messages,
очередь popup без отдельного экрана/пункта настроек. Список успешно загружается
один раз за текущий вход; сбои чтения повторяются не чаще 10 секунд в foreground.
При pause/stop новые popup скрыты, при возврате восстанавливаются. На сервер
не отправляются новые настройки/предпочтения; источник истины — прежний API.

MessageVisit хранит только временные UUID/revision в памяти ViewModel: rotation
сохраняет «позже», завершение сессии сбрасывает, перезапуск приложения получает
неподтверждённые заново. Дискового архива/истории нет; серверные read receipts
существующего контракта сохраняются. «Позже»/Back без ACK; confirm/action ACK
с UUID/revision, переход только после успеха. Ошибки оставляют popup с retry,
повторные клики блокируются busy. Expired сообщения пропускаются/исчезают;
после истечения срока запоздалый ACK не вызывает переход.

ConfirmDialog регистрирует модальное окно в SessionApp; popup уступает
logout/revoke/billing/discard, не накладываясь на подтверждение.
Длинный текст popup прокручивается, действия остаются снаружи scroll.
Содержимое сервера/бренды не приводятся к нижнему регистру автоматически.

Проверки: каталоги/placeholder parity и shell syntax локально. SDK/эмулятора в
workspace нет: debug/release builds/lint/JVM и native API26/35/36 — Actions.
Добавлены pure visit expiry/revision/reset тесты, HTTP expiry projection;
native popup ACK failure/retry/action, later/rotation/no-inbox, modal priority;
существующий native OTP тест теперь проверяет полный 60s deadline.
Писем OTP/поддержки, реальных платежей и VPN в автоматизации нет.

Проверенный product HEAD, merge/build SHA, run/attempt, APK, реальные native
снимки и аудит всех проверок фиксируются в PR #25 после CI; этот документ
не заявляет успешную приёмку до появления этих результатов.
Backend follow-up отсутствует; native VPN/настоящие платежи — отдельные задачи.
