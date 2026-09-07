# PrettyLisaVPN для Windows

Основа desktop-клиента: Tauri 2, Rust, React и TypeScript. Есть окно, главная страница,
экран «О приложении», конфигурация и заменяемые API/native-адаптеры. Главная работает
без Backend. Подключение VPN и бизнес-функции ещё не реализованы.

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

## Запуск

Из корня репозитория в PowerShell:

```powershell
cd apps/windows
pnpm install --frozen-lockfile
Copy-Item .env.example .env.local
pnpm tauri dev
```

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

| Переменная              | По умолчанию            | Назначение                               |
| ----------------------- | ----------------------- | ---------------------------------------- |
| `VITE_APP_ENVIRONMENT`  | `development`           | Метка: development, test или production. |
| `VITE_BACKEND_BASE_URL` | `http://127.0.0.1:8000` | База API, допустим префикс пути.         |

`VITE_*` — публичные значения. Никогда не помещайте сюда пароли, ключи или токены.
Для production требуется HTTPS; credentials, query и fragment в base URL запрещены.
Неверная конфигурация показывает безопасное сообщение запуска без её значений.
Vite mode и `VITE_APP_ENVIRONMENT` независимы: `pnpm build` сам по себе не переключает
метку development на production.

API-клиент содержит только типизированный `GET /version` с заменяемым fetch и безопасными
кодами ошибок. UI его пока не вызывает. При подключении API к UI потребуется разрешить
точный origin клиента в CORS Backend. CSP допускает HTTPS Backend, локальный
`http://127.0.0.1:8000` и Tauri IPC; для другого HTTP dev-origin нужно явно изменить CSP
в `src-tauri/tauri.conf.json`. Не расширяйте CORS/CSP до произвольных HTTP-адресов.

## Структура

```text
src/
  ui/          Компоненты, экраны, Routes и стили
  config/      Проверка публичных настроек
  api/         HTTP-клиент; никаких импортов React или Tauri
  state/       Контекст приложения и внедрение адаптеров
  native/      Единственное место импорта Tauri JS API
  test/        Тесты конфигурации, API и навигации
  main.tsx     Создание конфигурации и связывание зависимостей
src-tauri/
  src/         Rust: создание native-окна и event loop
  capabilities/ Минимальные разрешения (чтение версии приложения)
```

HashRouter работает как в Vite, так и со встроенными ресурсами exe. React Context
содержит настройки и адаптеры; будущие изменяемые состояния модулей добавляются сюда
по мере необходимости. Rust сейчас не предоставляет пользовательских IPC-команд,
доступа к файловой системе или shell. Версия native-приложения задаётся в
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

Ручной smoke test: выполните `pnpm tauri dev`, убедитесь в заголовке окна PrettyLisaVPN,
метке development, переходе «О приложении» с версией 0.1.0 и возврате на главную.
Backend для этого не требуется.
