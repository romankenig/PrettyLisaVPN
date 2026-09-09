# PrettyLisaVPN для Windows

Основа desktop-клиента: Tauri 2, Rust, React и TypeScript. Есть окно, главная страница,
экран «О приложении», конфигурация и заменяемые API/native-адаптеры. Главная проверяет
доступность Backend и показывает его версию. Подключение VPN и бизнес-функции ещё не
реализованы.

## Зависимости

- Windows 10/11 x64.
- Node.js 24 LTS и pnpm 11.19.0: `npm install --global pnpm@11.19.0`.
- Rust через [rustup](https://rustup.rs/) с MSVC toolchain. Версия 1.98.1,
  rustfmt и Clippy закреплены в `rust-toolchain.toml`; rustup загрузит их автоматически.
- Microsoft C++ Build Tools с workload **Desktop development with C++**, MSVC x64/x86
  и Windows SDK.
- Microsoft Edge WebView2 Evergreen Runtime.

См. [официальные требования Tauri для Windows](https://v2.tauri.app/start/prerequisites/).
Tauri CLI устанавливается локально из package.json; глобальная установка не нужна.
`pnpm-lock.yaml` и `src-tauri/Cargo.lock` фиксируют зависимости. В pnpm разрешён
только необходимый install-скрипт esbuild.

Установите Rust через rustup до первого запуска:

```powershell
winget install --id Rustlang.Rustup --exact
```

После установки полностью закройте PowerShell и откройте новое окно, чтобы обновился
`PATH`. Убедитесь, что обе команды доступны:

```powershell
rustc --version
cargo --version
```

Если rustup уже установлен, но PowerShell сообщает, что `cargo` не найден, добавьте
стандартный каталог Cargo в текущую сессию и повторите проверку:

```powershell
$env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
cargo --version
```

Это исправляет ошибку Tauri `failed to run 'cargo metadata' ... program not found`.
Чтобы изменение действовало в следующих терминалах, перезапустите Windows Terminal или
выйдите из учётной записи Windows и войдите снова. Не добавляйте этот путь повторно в
пользовательскую переменную `PATH`, если установщик rustup уже сделал это.

## Запуск

Из корня репозитория в PowerShell:

```powershell
cd apps/windows
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm tauri dev
```

Если pnpm запускается через Corepack, используйте те же команды с префиксом
`corepack`, например `corepack pnpm tauri dev`.

Tauri запускает Vite на `127.0.0.1:1420`, компилирует Rust и открывает PrettyLisaVPN.
Порт должен быть свободен. Первая native-сборка скачивает crates и может занять
несколько минут. `Ctrl+C` завершает dev-сессию. Обычные права пользователя достаточны.
Для просмотра только UI в браузере: `pnpm dev`; версия клиента там — `browser-preview`.

## Конфигурация

`src/config/config.ts` — единственная точка проверки настроек. Vite загружает `.env`,
`.env.local`, `.env.[mode]`, `.env.[mode].local`; значения режима имеют приоритет над
общими, а переменные процесса — над файлами. После изменения нужен перезапуск Vite.
В собранном приложении значения встроены в JavaScript: env-файлы с VPS или рядом с exe
не читаются. Для изменения настроек установленного клиента нужно пересобрать его.

| Переменная                        | По умолчанию                    | Назначение                                     |
| --------------------------------- | ------------------------------- | ---------------------------------------------- |
| `VITE_APP_ENVIRONMENT`            | `development`                   | Метка: development, test или production.       |
| `VITE_BACKEND_BASE_URL`           | `https://api.prettylisavpn.com` | База API, допустим префикс пути.               |
| `VITE_BACKEND_TIMEOUT_MS`         | `5000`                          | Тайм-аут каждого запроса, от 1000 до 30000 мс. |
| `VITE_BACKEND_HEALTH_INTERVAL_MS` | `15000`                         | Интервал проверки, от тайм-аута до 60000 мс.   |

`VITE_*` — публичные значения. Никогда не помещайте сюда пароли, ключи или токены.
Для production требуется HTTPS; credentials, query и fragment в base URL запрещены.
Неверная конфигурация показывает безопасное сообщение запуска без её значений.
Vite mode и `VITE_APP_ENVIRONMENT` независимы: `pnpm build` сам по себе не переключает
метку development на production.

API-клиент содержит типизированные `GET /health` и `GET /version`, заменяемый HTTP-слой,
ограничение времени запросов и безопасные коды ошибок. Tauri использует native HTTP plugin,
поэтому удалённый HTTPS Backend не требует CORS-разрешения для WebView. Браузерный preview
использует `fetch`, и для него Backend должен разрешить origin Vite. Capability допускает
HTTPS и локальный `http://127.0.0.1:8000`; другой незашифрованный dev-origin нужно добавить
явно.

Экран `/login` проверяет и нормализует email, затем вызывает типизированный
`POST /auth/request-otp`. Он отдельно показывает ожидание, локальную ошибку валидации,
rate limit, сетевую ошибку и временную недоступность сервера. Успешный общий ответ переводит на
`/auth/verify-otp`; email передаётся только во временном состоянии маршрута.

Экран проверки принимает шестизначный цифровой код и вызывает типизированный
`POST /auth/verify-otp` с email, `installation_id`, платформой `WINDOWS` и нейтральным именем
`Windows device`. Имя компьютера и hardware-идентификаторы не читаются. Повторная отправка
доступна после локального cooldown в 60 секунд; серверные rate limits остаются источником истины.
Ошибочный, истёкший и уже использованный код показывают одинаковое безопасное сообщение.

После успешной проверки credentials передаются через узкий `AuthenticationSession`. Access token
и сведения о текущей сессии хранятся только в памяти процесса. Refresh token сохраняется как
защищённый credential blob в Windows Credential Manager под фиксированным target
`PrettyLisaVPN/auth/refresh-token/v1`; сохранение нового значения атомарно заменяет прежнее.
Поддерживаются чтение для будущей ротации, замена и идемпотентное удаление. `localStorage`,
`sessionStorage`, JSON-файлы и app config для email, OTP или токенов не используются.

## Граница хранения credentials

Windows Credential Manager шифрует credential blob средствами Windows для текущего пользователя.
Rust-модуль `src-tauri/src/refresh_credentials.rs` — единственное место прямого доступа к Win32
Credential API. Он возвращает наружу только стабильную ошибку `credential_storage_unavailable`,
не содержащую token, payload или текст системной ошибки. Rust по возможности обнуляет временные
буферы refresh token после записи и чтения.

TypeScript-адаптер `src/native/credentialStorage.ts` предоставляет auth-слою только операции
`save`, `retrieve`, `replace` и `delete`. Компоненты получают `AuthenticationSession`, чей
`current()` не содержит refresh token. Сам token пересекает IPC только при входе и будущей
ротации. Код, исполняемый внутри встроенного WebView bundle, остаётся доверенной частью этой
границы: поэтому CSP запрещает удалённые scripts, а произвольная навигация и сторонний frontend
код не должны добавляться без отдельного security review.

## Идентификатор установки

При первом native-запуске Rust генерирует случайный UUID v4 и атомарно сохраняет его в
Tauri app config directory в файле `installation-id` (в Windows обычно
`%APPDATA%\com.prettylisavpn.windows\installation-id`). Следующие запуски читают то же значение.
Повреждённое значение не заменяется молча: приложение останавливает запуск, чтобы случайно не
зарегистрировать новую установку.

Идентификатор не выводится из железа и не использует MAC-адреса, серийные номера или другие
fingerprint-данные. TypeScript-код получает его только через типизированный
`InstallationIdProvider`; доступ к файловому пути и записи остаётся внутри Rust. Провайдер уже
доступен в `ApplicationState` для будущего auth-flow, но login UI пока отсутствует.

## Структура

```text
src/
  ui/          Компоненты, экраны, Routes и стили
  config/      Проверка публичных настроек
  api/         HTTP-клиент; никаких импортов React или Tauri
  auth/        In-memory access session и координация secure credential storage
  state/       Контекст приложения и внедрение адаптеров
  native/      Tauri JS API и узкий адаптер Windows Credential Manager
  test/        Тесты конфигурации, API и навигации
  main.tsx     Создание конфигурации и связывание зависимостей
src-tauri/
  src/         Rust: native-окно, event loop и persistent installation ID
  capabilities/ Разрешения чтения версии и HTTP для Backend
```

HashRouter работает как в Vite, так и со встроенными ресурсами exe. React Context
содержит настройки и адаптеры; будущие изменяемые состояния модулей добавляются сюда
по мере необходимости. Rust предоставляет только узкую IPC-команду чтения installation ID;
произвольного доступа к файловой системе или shell нет. OTP никогда не сохраняется; access token
живёт в памяти, а refresh token доступен только через native credential adapter. Версия native-приложения задаётся в
`src-tauri/tauri.conf.json`; поддерживайте её согласованной с Cargo.toml и package.json.

## Проверки и сборка

```powershell
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm native:format
pnpm native:lint
pnpm native:test
pnpm tauri build --no-bundle
```

`pnpm format` форматирует frontend; `cargo fmt --manifest-path src-tauri/Cargo.toml`
форматирует Rust. `pnpm test:watch` запускает тесты в watch-режиме. Native-команды
требуют Windows Build Tools и WebView2 для запуска окна. Сначала выполните `pnpm build`,
чтобы ресурсы frontend были доступны Cargo. Native-тестовая команда пока проверяет
компиляцию пустого bootstrap без Rust unit-тестов; поведение адаптеров проверяет Vitest.

Сборка exe находится в `src-tauri/target/release/prettylisavpn-windows.exe`.
Создание установщика, подпись и автообновления не входят в этот каркас.

Ручной smoke test: задайте доступный Backend в `.env.local`, выполните `pnpm tauri dev`
и убедитесь, что главная показывает `backend: online`, API version и backend environment.
Остановите Backend и подождите до 15 секунд: статус должен стать `offline`. Запустите его
снова и нажмите `retry`: статус должен вернуться в `online`. Проверьте переход на экран
«о приложении» с версией клиента 0.1.0 и возврат на главную.
