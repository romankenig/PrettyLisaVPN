# Android 0.2.0: мобильный дизайн PrettyLisaVPN

> Android 0.3.0/code3: [экраны на изолированных fixtures](android-fixture-screens.md).
> Windows0.12.0/backend0.10.0/schema0026 unchanged. Debug-only, no real VPN/API;
> English base, шесть языков отдельно. Историческое описание 0.2.0 ниже сохранено.
> Source/build SHA, все CI runs и native evidence — в task PR.


Исходный develop: `60fe13bfcbf6cd0e85deb85c7f5104810bf29e13`.
Эталон оформления — Windows **0.12.0** и [общий дизайн](design-system.md).
Android **0.1.0 / code 1 → 0.2.0 / code 2**: существенное обновление UI.
Windows/backend **0.12.0 / 0.10.0** и schema **0026** unchanged.
Точные проверенные HEAD, build SHA, run/attempt, APK digest и PNG фиксируются
в task PR после CI. Наличие этого документа не заменяет успешную приёмку APK.

## Что перенесено

| Windows | Android 0.2.0 |
| --- | --- |
| Полный логотип/замок | Исходные pathData без перерисовки; viewport обрезает только пустые поля, белый lockup на фиолетовом Home |
| Rubik variable/OFL | Локальный TTF и OFL сохранены, явные wght 400/500/600/700, все 15 Material typography roles; размеры в sp |
| Purple Heart / Christalle | Фон приложения / тёмная нижняя навигация |
| Mercury / Black / Scorpion | Светлые карточки, основной / вторичный текст |
| Viking / Heliotrope / Persian Red | Основные действия и selected, outline/focus, ошибка формы |
| Радиусы и спокойные плоские карточки | Shapes 6/8/12/16/24dp, карточки 16dp, кнопки 12dp, поля 8dp; без Material dynamic color |
| Desktop sidebar | Три телефонные вкладки с outline icons, выбранным акцентом и touch target ≥48dp; при fontScale ≥1.5 — полноширинные строки без разрыва слов |
| Две колонки Home | Вертикальный scroll: бренд, подключение, режим трафика; контент ограничен 600dp и центрируется на широкой области |
| Support popup | Отдельный мобильный экран формы, Back, прокрутка и IME; desktop chrome не переносится |

Компоненты: `ui/Theme.kt`, `BrandCard`, `BrandActionButton`, `BrandTextField`.
Button различает enabled/disabled/loading, loading блокирует повторное действие;
в поле есть native input/focus, error border и live error semantics. Все поля,
карточки, кнопки и подписи растут по содержимому вместо фиксированного desktop canvas.
Регистр PrettyLisaVPN сохраняется; прежние английские connect/not connected и
посвящение оставлены. Локализация шести языков — отдельный следующий этап;
0.2.0 по-прежнему использует русские resources.

## Реальные переходы и доступность

- Home/Settings/About доступны из нижней панели; повторные taps не дублируют graph.
  С Settings/About Back возвращает Home. Activity recreation восстанавливает вкладку.
- Home показывает недоступное подключение, Autopilot и выбранный full-traffic режим.
  Два выборочных режима остаются disabled/«скоро». Ни одна кнопка не создаёт туннель.
- Settings: подписка и устройства недоступны до API-интеграции, оформление read-only.
- About: версия Android из BuildConfig и source SHA; backend — «недоступна»,
  не выдуманная версия. Кнопка поддержки открывает локальную форму.
- В форме есть тема, описание, reply email и видимая валидация email. Верхние
  границы 120/4000/254 взяты из существующего support schema; отправки нет.
  Send disabled независимо от правильности ввода: sender/attachments/diagnostics
  ещё не подключены. Нет симуляции успешного обращения или фоновых запросов.
- Форма использует SavedStateHandle собственного navigation entry: state не зависит
  от пересоздания composable при Activity/configuration changes. Поля переживают
  recreation; закрытие destination удаляет черновик. Постоянного draft repository
  нет, секреты/OTP/credentials не сохраняются. Данные в тестовых PNG синтетические.
- Support Back возвращает About; системный Back сначала закрывает IME.
  Нижняя панель в форме скрыта. Scaffold потребляет safeDrawing insets, root
  учитывает IME; adjustResize включён для старых Android. У формы нет фиксированной высоты.

API, auth, VPN runtime, отправка поддержки, языки и платежи не добавлены.
Компонент loading проверяется в test-only composition из реальных production
composables; в продукте нет страницы component gallery или переключателя fixtures.

## Приёмка на эмуляторах

Существующий CI собирает APK/test APK текущего checkout, проходит lint, устанавливает
**тот же APK** на x86_64 API **26/35/36**. Headless runner использует
SwiftShader без Vulkan и 4GiB RAM; framework ANR/IME logs сохраняются при сбое. Android source/version/package/APK digest
проверяются до установки. Старые APK или Windows PNG не используются как результат.

Сначала выполняются прежние 3 NavigationTest, затем 3 DesignAcceptanceTest для
каждой конфигурации (21 instrumented tests на API), после них отдельный cold launcher.

| Case | Логический display (wm size) / density | Логический размер | fontScale |
| --- | --- | --- | --- |
| compact | 720×1280 / 320dpi | 360×640dp | 1.0 |
| small | 640×1136 / 320dpi | 320×568dp | 1.0 |
| scaled-font | 640×1136 / 320dpi | 320×568dp | 1.3 |
| large-font | 720×1280 / 320dpi | 360×640dp | 2.0 |
| roomy | 824×1648 / 320dpi | 412×824dp | 1.0 |
| landscape | 1280×720 / 320dpi | 640×360dp | 1.0 |

Тесты проверяют layout результата текста, touch targets/границы navigation относительно
system bars/cutout, наличие реальной IME и видимость email над ней, недоступность
сетевых действий, validation → corrected input, сохранение трёх полей после recreation,
enabled/disabled/loading semantics. Screenshot helper не создаёт графику программно:
это `UiAutomation.takeScreenshot()` реального Android дисплея после native idle,
lossless PNG без изменения размеров/пикселей; при недоступности UiAutomation
на старом display используется raw shell screencap с явным capture_method в JSON.
Baseline/launcher используют shell screencap. Landscape — реальный поворот display,
не изменение его естественного соотношения сторон.

Для каждого case сохраняются Home/Settings/About, форма с IME/error, заполненная
форма и component states. У PNG есть JSON: source SHA, версия/code/package, fontScale,
density, размеры и IME visibility. CI сверяет размеры логического display с каждым case, native PNG dimensions с
логическим либо исходным физическим дисплеем эмулятора (зависит от API screencap), source
и version/density/fontScale, включая реальную IME в keyboard capture. При ошибке
сохраняется raw failure capture; cleanup не превращает упавший тест в успех.
Отчёты и baseline/cold start evidence остаются в том же emulator artifact.

Эмуляторная проверка не доказывает поддержку всех OEM/клавиатур или handset VPN E2E.
TalkBack semantics подготовлены; ручная проверка произношения/жестов с включённым
TalkBack на устройстве остаётся отдельной приёмкой. Нативные PNG просматриваются
после CI, а итоговые результаты публикуются в PR без нового docs-only rebuild.

## Следующие этапы

Следующая отдельная продуктовая задача — языки (рекомендуемая **0.3.0 / code 3**),
по [контракту локализации](android-localization.md), затем остальные экраны/состояния
на fixtures, auth/API, VPN spike и handset acceptance по
[плану переноса](android-porting-plan.md). Версии Windows не задают Android versionName.
