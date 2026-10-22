# Android 0.6.3: OTP-ссылки и About по Windows

Android 0.6.2/code8 → 0.6.3/code9 (PATCH): небольшие уточнения существующих экранов.
Исходный product SHA — `f2239b0ac6b87f268083d935edc8adb2a8395f18`, PR #25.
Windows 0.12.0, backend 0.10.0/schema0026 и API-контракты unchanged.

## OTP

Resend/change email остаются над sign in с прежним bodySmall. Активные ссылки
PurpleHeart с подчёркиванием; disabled/cooldown — DustyGray без подчёркивания.
TextButton сохраняет нативную клавиатурную/доступную семантику и 48dp touch target.
FlowRow группирует действия в одну строку, gap 16dp; при длинном переводе/крупном
шрифте разрешён перенос без дополнительного промежутка между рядами. Horizontal
padding ссылок 4dp, vertical 0dp: устранены отдельные 16dp card gaps между действиями.
Fixture-инструкция с кодом остаётся отдельным предупреждением ниже группы.

Монотонные 30 секунд, атомарная публикация deadline, защита обработчика от раннего
resend, блокировка busy, очистка OTP и переход change email не меняются. Ввод и
challenge не теряются при смене языка; реальные OTP автоматические тесты не посылают.

## About

Референс — `apps/windows/src/ui/About.tsx`, `.about-*` в `styles.css` и Windows
`i18n/catalog.json`, сверенные также с актуальным develop. AboutScreen общий для
live (`live-about`) и fixture (`screen_ABOUT`); различаются только callbacks/tag
существующего перехода SUPPORT.

1. Локализованный заголовок Windows.
2. Две колонки frontend/backend: BuildConfig.VERSION_NAME и фактическая numeric
   SemVer из общей PresentationState либо локализованное «недоступна». Повторных
   запросов нет; footer использует ту же версию. Build SHA/About-only тестовый
   disclaimer удалены из пользовательской информации.
3. FAQ-карточка содержит только `faq`, как Windows. Вопросы, ссылки и функциональность
   не выдуманы. На телефоне пустая карточка имеет minimum 96dp вместо desktop 154px.
4. Карточка помощи: Windows heading/prompt/CTA из шести каталогов. Кнопка открывает
   существующий live Support screen/API либо изолированный fixture Support screen.
5. `inspired by love of my life, Lisa` — исходная английская строка Windows без
   перевода; приглушённая Mercury/0.55 внизу, margin-top 18dp.

Телефон использует вертикальные карточки вместо двух desktop-колонок. Версии
сохраняют две колонки с переносом; общий скролл и minimum viewport height держат
посвящение внизу при достаточной высоте и позволяют прокрутить длинный/крупный текст.
Rubik, Mercury/Scorpion/Christalle/Viking, BrandCard и кнопка переиспользованы.
Не связанные с Windows About действия Messages/Test scenarios перенесены в Settings
fixture shell; live Messages по-прежнему доступны из Home. Build SHA доступен в
fixture Scenarios. Release/live тестовыми инструментами не дополнены.

## Проверка и evidence

Catalog gate проверяет все шесть языков, placeholders и строчный стиль. Windows
копии About-текстов согласованы вручную без runtime зависимости Android от Windows.
PresentationUiTest дополнительно проверяет компактную строку OTP и прежние 30 секунд.
AccountScreensTest проверяет live About, actual frontend/fallback backend, FAQ,
посвящение и переход к поддержке с Back/draft guard без отправки. DesignAcceptance
проверяет About/поддержку/перенос текста во всех viewport/fontScale/IME сценариях.
Прежние тесты навигации, billing gates и session security сохраняются.

Локальный SDK/emulator отсутствует: build/lint/JVM и native API26/35/36 выполняются
GitHub Actions. Проверка требует новых APK/PNG текущего product SHA, всех push/PR
jobs и сверки build identity; 0.6.2 evidence не подменяет результаты 0.6.3. Итоговые
SHA/run/attempt/artifact links фиксируются в PR #25 после CI без дополнительного push.
В UI instrumentation metadata отключены; backend unavailable в PNG ожидаем.
Реальные письма, платежи, VPN и backend/deploy в эту задачу не входят.
