# История изменений

Версии клиентов и backend независимы. Правила повышения и выпуска:
[docs/versioning.md](docs/versioning.md). Наличие записи под Unreleased не означает
опубликованный релиз, production deploy или проверку реального VPN.

## Unreleased

### Windows — переходная поставка, план 0.2.0

При принятии правил 2026-10-16 манифесты и проверенный UI exe ещё имеют версию
0.1.0. Следующая задача с Windows-кодом должна синхронизировать версию на 0.2.0
и собрать новый артефакт. Эта запись не переименовывает прежние сборки.

- Added: кастомные оконные кнопки, общий заголовок с исходным замком, навигация
  иконками, настройки с устройствами и выходом из аккаунта.
- Changed: фиксированное окно 960 × 640 со скруглением, отдельная прокрутка списков,
  две колонки на Home, локально включённый Rubik.
- Added: версии frontend/backend внизу sidebar; backend читается из GET /version,
  ошибка получения не блокирует интерфейс.
- Compatibility: backend API/VPN-логика не менялись; /devices перенаправляется
  в /settings/devices. Проверка версии реального backend остаётся в handoff.
- Validation: 204 теста и native Windows UI capture прошли для product commit
  `629e73aabddca8b13409150155121ade6f596ce5`:
  [Windows run](https://github.com/romankenig/PrettyLisaVPN/actions/runs/38925995304).
  Это UI review с synthetic fixtures, не подтверждение production VPN.

### Документация — без повышения версии приложения

- Added: независимый SemVer, правила build identity, changelog и дальнейших задач,
  закреплённые в docs/versioning.md и AGENTS.md.
- Recorded: текущий legacy runtime-формат backend dev-SHA и отдельная задача
  перехода его CI/deploy/rollback. Развёртывание в этой задаче не менялось.

## Исходная база при принятии правил — 2026-10-16

Windows и backend объявляют 0.1.0 в исходных манифестах. Предыдущая история
релизов здесь не реконструируется и стабильный выпуск задним числом не объявляется.
