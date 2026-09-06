# Обновление кода и перезапуск на удалённом VPS

Инструкция предназначена для уже настроенного сервера. Для первого запуска используйте [развёртывание Backend](backend-deployment.md). Основной сценарий здесь — Backend + Caddy из `infra/deployment/compose.yaml`, каталог `/opt/prettylisavpn/repository`, настройки `/etc/prettylisavpn/deployment.env`, Compose-проект `prettylisavpn`.

Все команды после подключения по SSH выполняются **на VPS в Bash**. Значения `SSH_USER`, `VPS_IP_ADDRESS`, `RELEASE_TAG_OR_COMMIT` и `api.example.com` замените своими. Выполняйте блоки по очереди: если команда завершилась ошибкой, сначала разберитесь с ней, а не переходите к остановке приложения.

## Что именно нужно обновлять

| Действие | Что меняет | Чего недостаточно для обновления приложения |
| --- | --- | --- |
| `git fetch` / `git pull` | Исходники и файлы настройки в рабочей копии VPS. | Контейнер продолжает исполнять код старого образа. |
| `docker build` либо загрузка образа | Создаёт либо скачивает новую сборку приложения. | Уже работающий контейнер сам не переключается на неё. |
| `docker compose up -d` | Создаёт контейнеры и пересоздаёт их при изменении образа/конфигурации. | Нужно предварительно указать правильный образ и настройки. |
| `docker compose restart` | Останавливает и запускает существующие контейнеры. | Не применяет изменённые переменные окружения и не заменяет образ. |
| `sudo reboot` | Перезагружает весь VPS, включая Docker. | Не обновляет код и не собирает приложение. |

Поведение `restart` описано в [документации Docker](https://docs.docker.com/reference/cli/docker/compose/restart/). После изменения кода нужен новый образ и замена контейнера; после изменения env-файла — пересоздание контейнера через `up`, а не только `restart`.

## 1. Подготовьте проверенную версию

На компьютере разработчика завершите изменения, выполните проверки из [Backend README](../backend/README.md), создайте коммит и отправьте текущую ветку в `origin`. Ориентируйтесь на успешный CI нужного коммита. Изменения, которые остались только на компьютере и не отправлены в Git, VPS получить не сможет.

Выберите конкретный тег/коммит. Для production предпочтителен фиксированный релиз; тестовый VPS может намеренно следовать `develop`. CI автоматически передаёт проверенный development-образ на настроенный VPS без реестра. Для ручного или production-варианта с реестром образ нужно отдельно собрать и опубликовать по [инструкции развёртывания](backend-deployment.md).

На VPS работает один экземпляр Backend, поэтому запланируйте короткий перерыв при замене. Alembic подключён с пустой начальной ревизией; `deploy.sh` применяет миграции до замены контейнеров. Перед будущими изменениями схемы нужно изучать инструкции релиза, делать резервную копию PostgreSQL и проверять совместимость миграций с откатом.

## 2. Подключитесь и сохраните точку возврата

На своём компьютере:

```sh
ssh SSH_USER@VPS_IP_ADDRESS
```

На VPS:

```bash
cd /opt/prettylisavpn/repository
git status --short
git rev-parse HEAD
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml ps
curl --fail --show-error https://api.example.com/ready
curl --fail --show-error https://api.example.com/version
```

`git status --short` должен быть пустым. Если есть локальные изменения, выясните их назначение и сохраните отдельно; не используйте `reset --hard` для обхода проблемы. Если сервис уже неисправен, зафиксируйте исходное состояние, чтобы не принять старую неисправность за результат обновления.

Сохраните кодовую ревизию и секретные настройки **до** перехода к новой версии:

```bash
previous_commit=$(git rev-parse HEAD)
backup_dir="/etc/prettylisavpn/backups/$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 0700 "$backup_dir"
printf '%s\n' "$previous_commit" | sudo tee "$backup_dir/git-commit" >/dev/null
sudo cp --preserve=mode,ownership /etc/prettylisavpn/deployment.env "$backup_dir/deployment.env"
printf 'Каталог для отката: %s\n' "$backup_dir"
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml images backend
```

Запишите путь резервного каталога в журнал обновления. Копия env-файла содержит пароли и доступна только root. Она не является резервной копией PostgreSQL. Сохраните предыдущий образ локально и в реестре; не запускайте очистку Docker до завершения проверки и периода возможного отката.

Переменные `previous_commit` и `backup_dir` живут только в текущем SSH-сеансе. При повторном подключении используйте записанный путь, а не создавайте новую резервную копию поверх неисправного состояния.

## 3. Обновите рабочую копию Git

Выберите **один** вариант.

### Фиксированный production-релиз

```bash
git fetch --tags origin
git checkout --detach RELEASE_TAG_OR_COMMIT
git log -1 --oneline
```

`fetch` получает новые коммиты и теги, не меняя текущие файлы. `checkout --detach` переводит рабочую копию на выбранную ревизию. Сравните последнюю строку с релизом, который намеревались установить.

### Тестовый сервер, который следует develop

```bash
git fetch origin
git switch develop
git pull --ff-only origin develop
git log -1 --oneline
```

`--ff-only` разрешает только продвижение ветки без merge-коммита. При расхождении история не будет автоматически объединена. Не выполняйте merge на рабочем сервере: сначала разберите расхождение в среде разработки. Если локальной `develop` ещё нет, создайте её командой `git switch --track origin/develop` вместо `git switch develop`.

После любого варианта исходники обновлены, **но работающее приложение пока старое**. Теперь выберите вариант образа из следующего раздела.

## 4. Подготовьте и запустите новый образ

### Вариант А: образ из реестра

Вариант подходит для обычной поставки готового проверенного релиза. Образ должен быть заранее опубликован из того же коммита, на который переведён VPS.

```bash
sudoedit /etc/prettylisavpn/deployment.env
```

Измените `BACKEND_IMAGE` на новый digest или уникальный тег, а `APPLICATION_VERSION` — на соответствующую версию. Не меняйте реквизиты баз без необходимости. Уникальный тег нельзя повторно использовать для другого содержимого; digest надёжнее фиксирует сборку.

Запустите из `/opt/prettylisavpn/repository`:

```bash
sudo bash ./infra/deployment/deploy.sh /etc/prettylisavpn/deployment.env
```

Скрипт проверит конфигурацию, скачает образы, применит миграции, заменит контейнеры и проверит `/health`, `/ready` и `/version`. Он не выполняет `git pull` или сборку. После его завершения переходите к шагу 5 для независимой проверки.

<a id="local-build"></a>

### Вариант Б: сборка прямо на VPS без реестра

Подходит, если релизный реестр ещё не настроен. У VPS должны быть свободные память и диск для сборки; пока она выполняется, старый контейнер продолжает обслуживать запросы.

```bash
cd /opt/prettylisavpn/repository
release_commit=$(git rev-parse HEAD)
sudo docker build --pull --tag "prettylisavpn-backend:$release_commit" backend
sudo docker image inspect "prettylisavpn-backend:$release_commit" --format '{{.Id}}'
```

Полный хеш коммита используется как уникальный тег. Сборка должна закончиться успешно **до** замены контейнера. Обновите настройки:

```bash
printf 'Новая версия: %s\n' "$release_commit"
sudoedit /etc/prettylisavpn/deployment.env
```

Укажите `BACKEND_IMAGE=prettylisavpn-backend:ПОЛНЫЙ_ХЕШ` и `APPLICATION_VERSION=ПОЛНЫЙ_ХЕШ`, подставив напечатанное значение без кавычек-заполнителей. Не вводите строку `$release_commit` в env-файл: это переменная текущего терминала, а не сохранённая версия.

Проверьте конфигурацию и скачайте только Caddy, если его образ изменился:

```bash
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml config --quiet
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml pull caddy
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml up -d --pull never --remove-orphans --wait --wait-timeout 120
```

`--pull never` использует локальные образы. В этом варианте не запускайте `deploy.sh`: он попытается скачать также локальный Backend из реестра. Если Docker сообщает, что образ отсутствует, проверьте точное совпадение тега в env-файле и команде сборки.

При изменении содержимого `Caddyfile` дополнительно пересоздайте Caddy, чтобы он перечитал файл при запуске:

```bash
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml up -d --no-deps --force-recreate --pull never caddy
```

Это также относится к варианту А: изменение файла, подключённого как том, не гарантирует автоматическую перезагрузку его содержимого приложением.

## 5. Подтвердите успешное обновление

```bash
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml ps
curl --fail --show-error https://api.example.com/health
curl --fail --show-error https://api.example.com/ready
curl --fail --show-error https://api.example.com/version
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml logs --tail 100 backend caddy
```

Убедитесь, что:

- оба контейнера запущены, Backend имеет статус `healthy`;
- `/health` возвращает 200 — процесс работает;
- `/ready` возвращает 200 — доступны PostgreSQL и Valkey;
- `/version` показывает ожидаемый `application_version` и окружение;
- в логах нет повторяющихся ошибок запуска или подключения.

`APPLICATION_VERSION` — заданная вами метка, а не вычисляемый хеш кода. Поэтому дополнительно сопоставляйте реальный образ из `docker compose images backend` с нужной сборкой. Успешный `/health` при `/ready` 503 не считается успешным обновлением.

Запишите коммит, образ/digest, время обновления в UTC, результат проверок и каталог отката. Не прикладывайте env-файл или полный вывод `docker inspect`: они могут содержать секреты.

## Перезапуск без обновления

Если требуется только перезапустить текущий Backend, выполните на VPS:

```bash
cd /opt/prettylisavpn/repository
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml restart backend
curl --fail --show-error https://api.example.com/ready
```

Первый запрос сразу после перезапуска может не успеть подключиться: дождитесь запуска и повторите проверку. Для перезапуска обоих сервисов уберите `backend` в конце команды `restart`. Новые настройки env таким способом не применяются — используйте `up -d --wait` с теми же параметрами проекта.

Перезагрузка **всего VPS** нужна, например, после некоторых обновлений ОС:

```bash
sudo reboot
```

SSH-соединение прервётся. Через некоторое время снова подключитесь, проверьте `sudo systemctl is-active docker`, контейнеры и все три API-метода. Если контейнеры были явно остановлены, выполните `up -d --wait`. Перезагружать VPS после каждого обновления приложения не требуется.

## Откат к предыдущей версии

Откат нужен, если новая версия не запускается или не проходит проверки. Восстановите **согласованный набор**: коммит с конфигурацией, env-файл и образ. Пример для резервной копии из шага 2:

```bash
cd /opt/prettylisavpn/repository
backup_dir=/etc/prettylisavpn/backups/REPLACE_BACKUP_TIMESTAMP
previous_commit=$(sudo cat "$backup_dir/git-commit")
git status --short
git checkout --detach "$previous_commit"
sudo cp --preserve=mode,ownership "$backup_dir/deployment.env" /etc/prettylisavpn/deployment.env
```

Подставьте записанный каталог. Если рабочая копия изменилась, сначала разберите изменения. Копирование восстанавливает все старые настройки, включая секреты: если после обновления их уже сменили у провайдера, согласуйте актуальные значения через `sudoedit` перед запуском.

Для образа из реестра повторите:

```bash
sudo bash ./infra/deployment/deploy.sh /etc/prettylisavpn/deployment.env
```

Для сохранившегося локального образа:

```bash
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml config --quiet
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml up -d --pull never --remove-orphans --wait --wait-timeout 120
```

Если менялся `Caddyfile`, пересоздайте Caddy командой из шага 4. Снова выполните **все проверки шага 5**, ожидая старую версию. Не удаляйте Docker-тома и не используйте `down -v` или `docker system prune --volumes` как часть обновления/отката.

Будущий откат кода не откатывает автоматически схему и данные PostgreSQL. При появлении миграций совместимость старой версии с новой схемой нужно проверять отдельно.

## Если сервер запускается через другой файл или docker run

Не применяйте команды основного сценария к другому Compose-проекту: это может создать второй стек вместо обновления первого.

**Отдельный production Compose без Caddy** (`infra/docker/compose.production.yaml`): используйте прежнее имя проекта (в Backend README это `prettylisa-production`) и прежний env-файл. Сохраните ревизию и настройки, обновите Git, подготовьте образ, поменяйте `BACKEND_IMAGE`/`APPLICATION_VERSION`. Пример для конфигурации в `infra/docker/.env.production`:

```bash
docker compose -p prettylisa-production --env-file infra/docker/.env.production -f infra/docker/compose.production.yaml config --quiet
docker compose -p prettylisa-production --env-file infra/docker/.env.production -f infra/docker/compose.production.yaml up -d --wait
```

Для образа из реестра перед `up` выполните `pull`, для локального добавьте к `up` `--pull never`. На VPS при необходимости используйте `sudo` и расположенный вне Git env-файл. Проверяйте API по `http://127.0.0.1:8000`; значение `BACKEND_PORT` может отличаться.

<a id="docker-run-update"></a>

**Тестовый Timeweb с `docker run`** использует `/opt/prettylisavpn/source`, `/etc/prettylisavpn/backend.env` и контейнер `prettylisa-backend`:

1. Сохраните текущий коммит, образ и env-файл в защищённый резервный каталог по образцу шага 2. Образ посмотрите без вывода окружения: `sudo docker inspect --format '{{.Config.Image}}' prettylisa-backend`.
2. В `/opt/prettylisavpn/source` проверьте чистоту Git, выполните выбранное обновление из шага 3 и соберите образ **до остановки старого**:

   ```bash
   cd /opt/prettylisavpn/source
   release_commit=$(git rev-parse HEAD)
   sudo docker build --pull -t "prettylisavpn-backend:$release_commit" backend
   printf 'Новая версия: %s\n' "$release_commit"
   sudoedit /etc/prettylisavpn/backend.env
   ```

   Установите напечатанный хеш как `APPLICATION_VERSION`, сохранив `ENVIRONMENT=development`.

3. Замените только контейнер приложения:

   ```bash
   sudo docker stop --time 30 prettylisa-backend
   sudo docker rm prettylisa-backend
   sudo docker run --detach --name prettylisa-backend --restart unless-stopped --init --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges:true --stop-timeout 30 --publish 127.0.0.1:8000:8000 --env-file /etc/prettylisavpn/backend.env "prettylisavpn-backend:$release_commit"
   ```

   Здесь перерыв начинается со `stop`. Удаляется контейнер Backend, а не внешние базы и не образ.

4. Проверьте `/health`, `/ready`, `/version` через `curl --fail --show-error http://127.0.0.1:8000/ИМЯ_МЕТОДА` и `sudo docker logs --tail 100 prettylisa-backend`.
5. Для отката восстановите сохранённый env-файл, при необходимости старый коммит, повторите `stop`/`rm` и ту же команду `docker run`, указав **предыдущий образ** вместо нового. Повторите проверки. Для простого перезапуска без изменения настроек используйте `sudo docker restart --time 30 prettylisa-backend`.

## Частые проблемы

| Симптом | Что проверить и сделать |
| --- | --- |
| `git pull --ff-only` завершился ошибкой | Чистоту рабочей копии, локальные коммиты, выбранную ветку. Не создавайте merge на VPS. |
| Отказ доступа к образу | Правильность имени/digest, наличие публикации и авторизацию `sudo docker login` на VPS. |
| После `git pull` версия не изменилась | Собран/скачан ли новый образ и пересоздан ли контейнер. |
| `/ready` возвращает 503 | Приватную сеть, DNS баз, правила доступа, TLS и строки подключения. Перезапуск не исправит неверный пароль. |
| Caddy отвечает 502 | Запуск Backend, его логи, адрес `backend:8000` и общую Docker-сеть. |
| Не выпускается TLS-сертификат | DNS `A`/`AAAA`, доступность 80/443, домен в env-файле и сообщения Caddy. |
| Ошибка прав env-файла | Владелец root и режим 600; запускайте скрипт через `sudo`. |
| Docker сообщает нехватку диска | `df -h` и `sudo docker system df`. Разбирайте состав данных; не удаляйте тома и образы отката вслепую. |
