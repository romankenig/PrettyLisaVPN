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
- Compose использует Android resources в шести полных каталогах, сохраняя nav,
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
  Смена языка не отправляет OTP и не сбрасывает ограничение.
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
