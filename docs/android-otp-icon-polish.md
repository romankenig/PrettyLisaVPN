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

## Фиолетовый значок APK — Android 0.6.5

Отдельное уточнение владельца после проверки 0.6.4: фон launcher должен быть
фиолетовым из палитры. Android 0.6.4/code10 → 0.6.5/code11 (PATCH), исходный HEAD
`e5f3e8ded9bfab720af8cf7789c7b417cdbbcf0c`. Только ic_launcher.xml меняет цвета:
фон Purple Heart #5f22d9, знак Mercury #e4e4e4, контраст 6.08:1. Геометрия,
центровка и 0.65 scale прежние. Header/full logo и Windows/backend unchanged;
API/навигация не затронуты, backend follow-up отсутствует. Новый APK и native
app-info-icon.png проверяются по текущему SHA; итоговые build SHA/run/attempt и
артефакты фиксируются в PR #25 после всех push/PR jobs. Результаты 0.6.4 не
считаются проверкой 0.6.5. Реальные письма, платежи и VPN не запускаются.
