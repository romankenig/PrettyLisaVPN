# Android 0.6.4: OTP и симметрия знака

Android 0.6.3/code9 → 0.6.4/code10 (PATCH). Исходный product HEAD:
`4bab0f27eec9315c0e78846b44b8d85ac8b3e24b`; продолжение PR #25.
Windows 0.12.0/backend 0.10.0/schema0026 и API unchanged.

## OTP

Внутренняя группа code/error/links/submit использует spacing 4dp вместо 16dp;
между пояснением и группой остаются прежние 16dp. Строка ссылок сохраняет 48dp
нажатия: область между полем и sign in сокращена с 80dp до 56dp (примерно в 1.43
раза). При переносе или ошибке высота растёт по содержимому. Размер bodySmall
сохранён; Rubik Medium, тёмный Christalle и подчёркивание используют существующие
токены. Disabled countdown остаётся DustyGray без подчёркивания. FlowRow, busy,
30-секундный монотонный deadline, обработчики и навигация unchanged.

## Знак

Старая трассировка имела смещённую ось дужки относительно сердечка/скважины;
launcher дополнительно смещал знак вправо. По прямому запросу владельца выполнена
геометрическая коррекция Android знака с сохранением мотива замка-сердца.
Это узкое исключение из запрета самостоятельной перерисовки в design-system.md.
Три части симметричны относительно x=90 в viewport 180. Launcher использует
scale 0.65 вокруг (90,90) и прежний Viking фон. Header mark и знак в полном
Android логотипе используют те же pathData; буквенные пути не меняются.
Windows SVG и палитра не изменены. Логотип не создаётся из emoji/системной иконки.

## Проверка

Catalog gate и build/lint/JVM выполняются в Android debug. Native API26/35/36
проверяют приложение на прежних шести viewport/fontScale/IME конфигурациях.
PresentationUiTest проверяет бюджет secondary area и сохранённые cooldown/code,
снимает cooldown и ready состояния. Сборки/PNG должны соответствовать текущему
HEAD; metadata в UI instrumentation отключены. Автотесты не отправляют настоящие
OTP/support письма, платежи и не подключают VPN. Backend follow-up отсутствует.
Финальные product/build SHA, run/attempt, артефакты и результаты фиксируются в
описании PR #25 после завершения всех jobs без нового documentation-only push.
