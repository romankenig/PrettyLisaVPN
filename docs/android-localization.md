# Android: требования локализации после Windows 0.12.0

Статус: **план следующего UI-этапа, не реализованная Android-функция**.
Android 0.3.0/code 3 реализует [экраны на fixtures](android-fixture-screens.md)
с English base и без выбора языка/гео. Следующая рекомендуемая задача локализации
**0.4.0 / code 4** — отдельная реализация; шесть языков не считаются готовыми.

Эталон: Windows **0.12.0**, [PR #21](https://github.com/romankenig/PrettyLisaVPN/pull/21),
develop `78f59991761b93bd176326c901829ee49cbdd9a4`.
Первоначальный Android-аудит Windows 0.11.1 на `69ab8d1` — исторический.
Backend **0.10.0 / schema 0026** заморожен: новых endpoints/полей/платёжных
провайдеров для локализации не требуется.

## Дельта и границы паритета

| Область | Windows 0.12.0 | Требование Android |
| --- | --- | --- |
| Язык | 6 языков, локальный явный выбор | Тот же список/порядок/политика, Android string/plural resources |
| Выбор | SVG-флаг + English/native имена внизу sidebar | Мобильная строка настроек + sheet; независимый доступ до auth |
| Default | English; подтверждённая RU-локация до VPN → Russian | Не язык ОС; offline/ошибка/UNKNOWN остаются English |
| Хранение | localStorage, ручной выбор выше гео | App-scoped preference/controller, rotation/process restart/logout не сбрасывают |
| Live UI | Формы, ошибки, title/aria, даты/цены/страны | Compose UI/семантика, ошибки, dialogs и собственные notifications, форматирование |
| API/native | Добавлен read-only local tunnel probe; backend unchanged | Android runtime status port; Windows/Tauri метод не переносится буквально |
| Исключения | Бренд, протоколы, прежний English, ввод и авторский контент | Те же исключения; системные Android/VPN/SAF окна принадлежат ОС |

UI-каталог Windows содержит **257 сообщений × 6 языков**. Это источник формулировок
и coverage map, а не требование ровно 257 Android resource IDs: desktop chrome
не переносится, Android добавляет собственные consent/help/notification тексты.
Числа сообщений и APK-готовность нельзя отождествлять.

## Список и отображение

| English name / порядок | Native name | Флаг | App code | Android / API locale |
| --- | --- | --- | --- | --- |
| Chinese | 中文 | CN | zh | Simplified Chinese: zh-Hans; messages locale zh-CN |
| English | English | GB | en | en; messages locale en-GB |
| French | Français | FR | fr | fr / fr-FR |
| German | Deutsch | DE | de | de / de-DE |
| Russian | Русский | RU | ru | ru / ru-RU |
| Spanish | Español | ES | es | es / es-ES |

Порядок фиксирован по английскому имени и не меняется вместе с выбранной локалью.
Показывать **оба** имени, включая English / English; не заменять English names
переводом на текущий язык. Сохранять регистр English/native имён, даже если основная
тема использует lowercase. Флаги — существующие лицензированные векторные assets,
адаптированные под Android drawable; не emoji, не новый сетевой сервис.

Compact UI: строка языка в настройках открывает ModalBottomSheet со всеми шестью
пунктами, текущим выбором и флагами. До входа — компактный language control на
auth/startup shell, доступный также при offline/retry; доступ не должен зависеть
от токена или успешного backend-запроса. Desktop sidebar не нужно втискивать в
нижнюю навигацию телефона. На wide layout допустим тот же control внизу rail.
Back закрывает sheet, выбранная вкладка/форма сохраняется. Touch targets не меньше
48dp; scroll при landscape/fontScale, TalkBack name/state/focus и возврат фокуса.

## Политика выбора и безопасный origin

1. До показа первого UI загрузить app preference. Сохранённый явный язык имеет
   приоритет при любой стране, аккаунте, языке ОС и доступности сети.
2. Без явного выбора effective language = **English**, включая русскую ОС,
   отсутствие сети, storage failure, неизвестную страну и неизвестный tunnel state.
3. Только свежая локация **до VPN**, при достоверном DOWN до и после запроса,
   позволяет автоматически выбрать Russian для RU; другие страны → English.
   Не определять страну по языку ОС, выбранному VPN-серверу, часовому поясу или GPS.
4. Generation/cancellation guard отклоняет ответ, если началось подключение,
   runtime уже UP/UNKNOWN, появился новый запрос или пользователь выбрал язык.
   VPN exit location не должна менять язык. Не использовать VpnService.prepare()
   как проверку статуса: это consent API, а не доказательство DOWN.
5. Явный выбор, даже совпадающий с текущим автоматическим языком, фиксирует
   приоритет. Сбой сохранения допускает работу в памяти и должен быть обработан.
   Logout/смена аккаунта не удаляют язык; credentials при этом не переносятся.
6. Нет скрытого follow-system, GPS permission, истории IP или новой geo-службы.
   Public-location adapter использует существующий безопасный HTTPS контракт
   без Bearer/cookies; InternetVerifier остаётся отдельной VPN-проверкой.

Ручной выбор/offline English реализуются на UI-этапе 2A. До готовых public-location
и достоверного Android runtime status автовыбор RU проверяется **на fixtures**.
Реальный origin integration относится к этапам API/native; документация/тестовый
ответ RU не доказывают работающую Android геолокацию. Не отключать блокировку
CONNECT ради получения статуса и не запускать настоящий туннель в UI-тесте.

## Resources, состояние и Android-интеграция

- Полный English fallback в `res/values/strings.xml`; переводы ru/fr/de/es и
  Simplified Chinese (например, `values-b+zh+Hans`). Стабильные semantic IDs,
  форматные параметры и Android plurals; не собирать предложения из фрагментов
  и не переводить произвольный rendered text через DOM/строковый lookup.
- App name PrettyLisaVPN и согласованные неизменяемые английские/технические
  подписи помечать `translatable=false`, либо сохранять параметром/кодом;
  не переводить токены API/state/protocol/route/currency, email, ID, пользовательский
  ввод и авторские сообщения сервера. Город из geo-provider остаётся авторским
  значением; страны отображать средствами выбранной locale.
- Переводятся все принадлежащие приложению подписи и состояния: loading/error/
  retry/stale/disabled, validation, подтверждения, quota/countdown, accessibility/
  contentDescription, help, собственные service notifications. Биллинг форматирует
  сумму/дату выбранной locale, но не меняет валюту/цену/период договора.
- `LanguageRepository` и `LocaleController` — отдельная граница, независимая от
  SessionCoordinator и ConnectionCoordinator. В AndroidX-пути использовать
  per-app locales/AppCompatDelegate с совместимой Activity/темой; нынешняя
  ComponentActivity сама по себе не означает готовую интеграцию AppCompat.
  Конкретную зависимость и Activity adaptation закрепить в реализации 2A.
- Persisted explicit selection и auto-origin marker app-scoped, без секретов.
  Не создавать конкурирующие источники истины DataStore/AppCompat/platform locale:
  определить единый controller и порядок записи/восстановления.
  Для API 33+ зарегистрированный `localeConfig` требует двусторонней синхронизации:
  системный выбор считать явным, reset возвращать к продуктовому default.
  Пустая locale list с обычным Follow OS не соответствует English/RU origin policy.
- Activity recreation при смене языка допустима, но не новый login, POST billing/
  support, VPN start/stop или сброс графа/формы. Native session/service не принадлежит
  Activity; OTP/ключи/refresh не добавлять в SavedStateHandle ради locale change.
- Rubik остаётся основным шрифтом, CJK font fallback проверяется на минимальном API
  и целевых устройствах: без пустых квадратов и сетевой загрузки шрифта. Не делать
  перевод только через ручной нижний регистр; не ломать диакритику и TalkBack.
- Messages API получает locale приложения из таблицы, platform=ANDROID и Android
  app_version. Авторский текст локализует сервер/автор; реальная OTP-почта, payment
  provider/браузер и Android consent/system picker не становятся переводимыми
  нашим каталогом. Backend из-за этого не меняем.

## Проверяемые результаты следующей задачи

| Проверка | Ожидаемый результат |
| --- | --- |
| Чистая установка на ОС ru/de/zh, offline | English UI, ни одного требования войти для выбора языка |
| RU до VPN / другая страна / error / UNKNOWN | Russian только для подтверждённого свежего RU/DOWN; остальные English |
| Поздний RU после CONNECT/UP/нового запроса/ручного выбора | Не меняет effective language |
| Явный en при авто-en; geo RU; logout/новый аккаунт | Остаётся en; язык не account-scoped |
| Rotation, Activity recreation, настоящий process cold start | Выбор восстановлен, формы/навигация согласованы; нет повторных внешних операций |
| Хранилище недоступно/испорчено | Без crash; English default или текущий явный выбор в памяти |
| Перевод уже показанной ошибки/открытого dialog | Новый язык сразу, без повторного сетевого запроса или очистки формы |
| API 33+ system app-language change/reset (если localeConfig опубликован) | Согласован с controller/explicit marker; без циклов recreation и Follow OS вместо default |
| Шесть resource sets/parameters/plurals | Нет пропущенных app-owned строк; exceptions и API-коды неизменны |
| 320/360/412dp, landscape, fontScale 1.0/1.3/2.0, TalkBack | Все пункты доступны, нет обрезания, корректные focus/semantics/CJK |

Unit-тесты политики/гонок, resource/contract tests и Compose tests обязательны
для этой функции. Native evidence: **API 26/35/36**, шесть Home и открытый language
sheet, auth/retry, настройки и хотя бы одна ошибка/форма; плюс cold start и
recreation. Снимать текущий Android APK, сохранять source/build SHA, run/attempt,
API/ABI/locale/fontScale и digest. Windows PNG, Activity recreate и одинаковый
versionName сами по себе не доказывают process persistence или Android-паритет.
Release/profile APK не должен включать fixture transport.

Каркас PR #20 остаётся bootstrap: его успешный CI не означает, что перечисленная
локализация уже реализована. Реальный Android API/VPN E2E, handset acceptance и
подключение платёжного провайдера — последующие отдельные задачи.

## Источники

- [Windows localization contract](windows-localization.md).
- [Windows catalog](../apps/windows/src/i18n/catalog.json),
  [preference policy](../apps/windows/src/i18n/language.ts),
  [UI selector](../apps/windows/src/ui/LanguageSelector.tsx),
  [safe country observer](../apps/windows/src/ui/HomeCountryObserver.tsx).
- [Android architecture](android-architecture.md), [roadmap/prompts](android-porting-plan.md),
  [bootstrap README](../apps/android/README.md), [versioning](versioning.md).
