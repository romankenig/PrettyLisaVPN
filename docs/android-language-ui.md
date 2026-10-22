# Android 0.6.0: языки и общая шапка

Исходная версия Android 0.5.0/code5, целевая 0.6.0/code6: MINOR за новую
возможность выбора языка. Windows 0.12.0 и backend 0.10.0/schema0026 unchanged.
Основание — develop после merge PR #24 (`944be9ffb6734dae86f71aee30ea87d90749b4db`).

## Поведение

- Справа сверху общий selector: флаг, English name и native name. Порядок:
  Chinese/English/French/German/Russian/Spanish, как в Windows.
- Сохраняется только явный выбор пользователя в обычных app preferences: это
  несекретная настройка, изолированная от credential vault и operation journal.
- Без выбора English; однократный публичный HTTPS-запрос ipwho.is может предложить
  Russian для country_code=RU. Системная locale не подменяет эту логику.
  При активном системном VPN запрос не запускается; перед применением результата
  VPN проверяется снова. Поздний ответ никогда не заменяет ручной выбор.
  Невозможность проверить VPN/локацию оставляет English. IP/ответ не сохраняются.
- Compose выбирает Android string resources через отдельный configuration context;
  Activity/LocalContext, font resolver, launcher и IME не подменяются. Это сохраняет nav,
  ViewModel, auth challenge, email/code и монотонный resend deadline. Смена locale
  не пересоздаёт Activity. OTP не сохраняется при настоящем пересоздании Activity.
- Бренд PrettyLisaVPN, протоколы, идентификаторы, валюты и серверные пользовательские
  сообщения/имена устройств/содержимое форм остаются данными, не переводятся.
- Общая шапка с исходной геометрией знака и PrettyLisaVPN присутствует до входа,
  на OTP, восстановлении сессии и остальных экранах. Нижняя строка показывает
  Android frontend version из BuildConfig и backend из публичного GET /version.
  Нет подстановки версии из исходников backend или из клиентской версии.
- Оба публичных запроса изолированы от auth-клиента, без Authorization/cookies,
  redirect/retry; timeout 5s и ограничение ответа 16KiB. Сбой не блокирует вход.
  В автоматических проверках оба внешних запроса отключены до запуска Activity;
  HTTP-контракт metadata проверяется локальным MockWebServer.
- Resend the code/change email — TextButton без заливки, менее контрастный bodySmall,
  touch target не менее 48dp; расположены до основной кнопки sign in.
  Resend недоступен 30 секунд по SystemClock.elapsedRealtime и при busy.
  Смена языка не отправляет OTP и не сбрасывает ограничение. Deadline входит в
  ScreenState: даже мгновенный ответ resend обновляет UI. Обработчик дополнительно
  проверяет текущее монотонное время перед запросом, защищая от двойного клика.
- Удалён live development/VPN banner. Предупреждение no VPN tunnel на аккаунте
  и disabled connect VPN остаются честными. В изолированном fixture-режиме
  сохранён отдельный локализованный Test data/no VPN tunnel, чтобы симуляция
  не выглядела настоящим туннелем. DISABLED/SANDBOX payment gates не меняются.

## Проверка и evidence

JVM PresentationTest проверяет default/RU fallback, ручной приоритет, restart
preferences, ошибки хранения, порядок языков и публичные HTTP metadata.
PresentationUiTest на API26/35/36 проверяет шесть переводов, сохранение email/code,
реальное ожидание 30 секунд, повторный resend, расположение ссылок и recreation.
Native PNG сохраняются в `acceptance/ui-polish/` текущего APK. Прежние auth/account,
Keystore, flow, small-screen/fontScale/IME suites остаются включены.

Локальная среда не содержит SDK/emulator; сетевой proxy недоступен для Gradle.
Поэтому сборка/lint/JVM/native acceptance выполняются GitHub Actions, с APK и
build-identity текущего product SHA. До результатов CI успешная приёмка не заявляется.
Итоговые product/build SHA, run/attempt, артефакты и скриншоты фиксируются в PR,
без нового docs-only push ради перезапуска проверок. Реальные письма/платежи/VPN
автотестами не выполняются. Реальный provider и Android VPN runtime — отдельные задачи.

## Полировка Android 0.6.1

Исходная версия 0.6.0/code6 (`42d5318ba66e505f6ba7501585b16c80197b821d`),
целевая 0.6.1/code7: PATCH для небольших визуальных исправлений по снимку телефона.
Windows 0.12.0, backend 0.10.0/schema0026 и API-контракты unchanged.

- Backend GET /version сохраняет полный runtime SemVer для диагностики и deployments.
  Android принимает только целый корректный SemVer, отображая числовой `MAJOR.MINOR.PATCH`.
  Prerelease/build suffix не отображаются. SHA-цифры не склеиваются с версией.
  Неизвестные/legacy/испорченные ответы дают локализованное «недоступна», без
  подстановки из манифестов. Ответ ограничен 16KiB, version — 256 символами/core20.
- Знак: прежние контуры без уменьшения до 65%, контейнер 44dp вместо 26dp.
  PrettyLisaVPN: Rubik titleLarge 22sp вместо titleSmall 16sp. При нехватке ширины
  selector остаётся справа сверху в отдельной строке; крупный шрифт не отключается.
- Flag и центрированные English/native names — отдельные колонки одинаковой ширины.
  Native name opacity 0.72, как в Windows; меню использует Christalle/Mercury/Viking.
  Порядок/сохранение языка и правила автоматического выбора не меняются.
- email остаётся в русском/английском; Chinese — 电子邮箱, Spanish — correo electrónico,
  French — e-mail, German — E-Mail (начальная подпись e-mail по общей типографике).
  Удалены оставшиеся английские email в заголовках, ошибках и reply-address.
- Начальные строчные задаются в ресурсах, без runtime lowercasing. Бренды/платформы,
  протоколы/аббревиатуры, планы и имена языков сохраняют собственный регистр.
  Письма, имена устройств, пользовательские сообщения, ввод и placeholders неизменны.
- Catalog gate проверяет также строчный старт и email-терминологию. JVM включает
  реальную длинную версию со скриншота и ошибочные SemVer; native suite проверяет
  центры обеих строк, размер знака и сохранение смешанного регистра email.

Проверка новой версии требует новых APK/native PNG и всех push/PR jobs API26/35/36.
Результаты прежнего 0.6.0 не являются приёмкой 0.6.1. Product/build SHA, run/attempt,
результаты и artifact links обновляются в PR #25 после CI без дополнительного push.
Backend follow-up для этой полировки отсутствует; реальный provider/VPN не добавлены.

## Нижняя полоска и компактный selector — Android 0.6.2

Исходная версия 0.6.1/code7 (`9df4e177b2c61a0063ca92628ab930e866b2ef51`),
целевая 0.6.2/code8: PATCH за небольшую перестановку элементов. Windows 0.12.0,
backend 0.10.0/schema0026, auth/billing/API-контракты unchanged.

Версии удалены из AppHeader. AppVersionFooter расположен в общем корневом Column
после всех экранов/нижней навигации: auth, OTP, restore, account и fixture используют
одну полоску Christalle с labelSmall/Viking и вертикальным padding 3dp. Высота
растёт при увеличении шрифта; текст не ограничен одной строкой. Фактическая backend
SemVer и fallback «недоступна» работают по прежним правилам 0.6.1.

Корневой контейнер применяет imePadding ко всему приложению; версии перемещаются
над клавиатурой. Footer владеет нижними safeDrawing/cutout отступами, а область
экранов потребляет эти insets, чтобы вложенные Scaffold/PhoneNavigation не добавляли
их повторно. Top/horizontal insets экранов сохраняются. Переходов/новых действий нет.

В LanguageNames общий gap сокращён с 8dp до 4dp, колонка названий с 88dp до 56dp,
флаг центрирован в своей колонке. Ширины масштабируются с fontScale; центры обоих
названий совпадают, native name остаётся opacity 0.72. Сортировка/выбор/геолокация,
состояние auth и resend deadline не меняются.

Native PresentationUiTest проверяет нижнее положение версий/отсутствие их в шапке
на всех шести языках, близость флага и сохранение центрирования. DesignAcceptance
проверяет footer ниже вкладок и над system bars/IME во всех прежних размерах,
fontScale и клавиатурных сценариях. PNG/identity и полные результаты актуального
HEAD фиксируются в PR #25 после всех push/PR jobs. Прежние APK не считаются
приёмкой 0.6.2. Реальные письма/платежи/VPN не выполняются; backend follow-up нет.

Android 0.6.3/code9 сохраняет эту шапку/footer/выбор языка и уточняет OTP-ссылки и
состав About по Windows: [android-about-otp-ui.md](android-about-otp-ui.md).
