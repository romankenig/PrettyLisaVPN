# Развёртывание Backend на Ubuntu VPS

Эта инструкция запускает Backend и Caddy на одном VPS с Ubuntu LTS. VPS — виртуальный сервер, к которому вы подключаетесь по SSH. PostgreSQL и Valkey размещаются отдельно, как управляемые сервисы: их установкой и обслуживанием занимается облачный провайдер.

Caddy принимает публичные HTTP/HTTPS-соединения, получает и обновляет TLS-сертификат и передаёт запросы Backend по внутренней Docker-сети. Порт Backend 8000 не публикуется. Этот сервер обслуживает API управления, а не пользовательский VPN-трафик.

Для уже работающего сервера перейдите к [обновлению кода, перезапуску и откату](vps-maintenance.md). Для подготовки ресурсов в Timeweb есть [отдельная инструкция](timeweb-development-setup.md).

## 1. Подготовьте доступы и адреса

До начала понадобятся:

- Ubuntu LTS VPS со статическим публичным IP, доступом по SSH и правами `sudo`;
- домен API, например `api.example.com`, и доступ к его DNS;
- внешние PostgreSQL и Valkey, доступные с VPS, с выданными провайдером параметрами подключения;
- URL Git-репозитория и конкретный тег релиза или хеш коммита;
- образ Backend в реестре контейнеров с неизменяемым digest либо уникальным тегом;
- email для уведомлений о TLS-сертификатах.

Все `VPS_IP_ADDRESS`, `SSH_USER`, `REPOSITORY_URL`, `RELEASE_TAG_OR_COMMIT` и адреса `example.com` в командах — заполнители. Заменяйте их своими значениями, не вводите буквально. Команды ниже рассчитаны на Bash в Ubuntu; только `ssh` выполняется на вашем компьютере.

Создайте DNS-запись `A` домена API с публичным IPv4 VPS. Запись `AAAA` добавляйте только при действительно настроенном IPv6. Ошибочная `AAAA` может мешать получению сертификата и доступу части клиентов. Скрипт проекта не создаёт DNS-записи.

В облачном сетевом экране разрешите входящий TCP 22 только с доверенных административных адресов, TCP 80 и 443 — для публичного API. UDP 443 нужен только для HTTP/3. Порт 8000 открывать не нужно. В правилах баз разрешите доступ с приватного IP VPS, если есть общая приватная сеть, иначе — с его статического публичного IP и с требуемой защитой транспорта.

## 2. Подготовьте чистый VPS

На своём компьютере подключитесь с именем пользователя из панели провайдера:

```sh
ssh SSH_USER@VPS_IP_ADDRESS
```

При первом подключении сверьте отпечаток ключа сервера с доверенными данными провайдера. После входа команды выполняются **на VPS**.

Обновите пакеты и установите базовые утилиты:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git
```

`apt update` обновляет список пакетов, `apt upgrade` устанавливает обновления. Если Ubuntu сообщает о необходимости перезагрузки, выполните её в согласованное время и снова подключитесь по SSH.

### Установка Docker

Следующие команды предназначены для чистого Ubuntu без другой установки Docker. Если Docker уже работает, сначала выполните `sudo docker version` и `sudo docker compose version`; не смешивайте пакеты `docker.io` из Ubuntu с `docker-ce` из репозитория Docker.

Добавьте ключ и официальный репозиторий:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
```

Ключ позволяет APT проверять пакеты, а запись `docker.sources` указывает источник для установки и обновлений. Установите движок Docker и Compose:

```bash
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

`enable --now` запускает Docker и включает автозапуск при загрузке VPS. `hello-world` проверяет скачивание и запуск контейнера. Используйте `sudo`: членство в группе `docker` практически даёт административный доступ к серверу. Команды сверены с [официальной инструкцией Docker для Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

Если используете UFW, сначала разрешите свой административный адрес, чтобы не потерять SSH-доступ:

```bash
sudo ufw allow from ADMIN_PUBLIC_IP to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

Замените `ADMIN_PUBLIC_IP` на свой внешний IP; при другом SSH-порте скорректируйте правило. Docker может обходить часть правил UFW для опубликованных портов. Конфигурация проекта публикует только Caddy 80/443; дополнительно проверяйте облачный сетевой экран.

## 3. Получите исходники выбранного релиза

```bash
sudo install -d -o "$USER" -g "$USER" /opt/prettylisavpn
git clone REPOSITORY_URL /opt/prettylisavpn/repository
git -C /opt/prettylisavpn/repository checkout --detach RELEASE_TAG_OR_COMMIT
sudo install -d -m 0700 /etc/prettylisavpn
```

`checkout --detach` фиксирует конкретную версию вместо автоматического следования ветке. Рабочую копию хранит обычный административный пользователь, а секреты — root в отдельном каталоге. Для приватного Git используйте настроенный SSH-ключ или утверждённый механизм доступа; не включайте токен в URL клонирования.

Структура на сервере:

```text
/opt/prettylisavpn/repository/        Исходники и конфигурация выбранного релиза
  infra/deployment/compose.yaml     Backend + Caddy
  infra/deployment/Caddyfile        Маршрутизация HTTPS-запросов
  infra/deployment/deploy.sh        Загрузка образов и запуск
/etc/prettylisavpn/deployment.env    Настройки и секреты, доступ только root
Docker-тома caddy_data/caddy_config  Сертификаты и состояние Caddy
```

Тома получают префикс Compose-проекта `prettylisavpn`. При замене контейнеров они сохраняются. У Backend нет тома с бизнес-данными: постоянная информация должна храниться во внешнем PostgreSQL.

## 4. Подготовьте образ Backend

`deploy.sh` **скачивает** указанный образ из реестра и не собирает его из Git. Существующий CI проверяет код и тестовый образ, но не публикует релиз автоматически.

Сборку и публикацию выполните на машине сборки из проверенного коммита. Пример, где `RELEASE_VERSION` — уникальная версия, а `registry.example.com` нужно заменить адресом вашего реестра:

```bash
docker login registry.example.com
docker build --pull -t registry.example.com/prettylisavpn/backend:RELEASE_VERSION backend
docker push registry.example.com/prettylisavpn/backend:RELEASE_VERSION
```

Выполняйте из корня репозитория. Образ должен соответствовать архитектуре VPS: например, сборка ARM на ARM-компьютере не подойдёт обычному VPS x86_64 без специальной настройки сборки. Сохраните digest из результата публикации: он однозначно определяет содержимое образа. Для локальной сборки прямо на VPS без реестра используйте [отдельный порядок обновления](vps-maintenance.md#local-build).

Если реестр приватный, на VPS выполните `sudo docker login registry.example.com` и введите данные интерактивно. Скрипт запускается от root, поэтому доступ к реестру должен быть у того же пользователя Docker. Используйте токен с минимально необходимым правом чтения; не записывайте его в команду или Git. Защитите сохранённые Docker-учётные данные.

## 5. Заполните настройки

При **первой** настройке скопируйте шаблон:

```bash
sudo install -m 0600 /opt/prettylisavpn/repository/infra/deployment/.env.example /etc/prettylisavpn/deployment.env
sudoedit /etc/prettylisavpn/deployment.env
```

Повторное копирование перезапишет заполненный файл, поэтому для изменений используйте только `sudoedit`. Замените все `REPLACE_*` и адреса `example.invalid`.

| Переменная | Что указать |
| --- | --- |
| `API_DOMAIN` | Реальный публичный домен без `https://`, пути и кавычек. |
| `ACME_EMAIL` | Email для уведомлений о сертификатах. |
| `BACKEND_IMAGE` | Опубликованный образ, желательно `registry.example.com/prettylisavpn/backend@sha256:…`; допускается уникальный тег, но не `latest`. |
| `APPLICATION_VERSION` | Версия именно этого образа; её вернёт `/version`. Переменная сама по себе не меняет исполняемый код. |
| `POSTGRES_URL` | Полная строка `postgresql+asyncpg://` с реквизитами PostgreSQL. |
| `VALKEY_URL` | Полная строка `redis://` либо `rediss://` с реквизитами Valkey. |
| `ENVIRONMENT` | `production` для рабочего сервиса; этот Compose также позволяет явно задать другое окружение. |
| `APPLICATION_NAME`, `LOG_LEVEL` | Обычно `PrettyLisaVPN`, `INFO`. |
| `DEPENDENCY_TIMEOUT_SECONDS` | Обычно `2`; время проверки зависимости в секундах. |
| `POSTGRES_POOL_SIZE`, `POSTGRES_MAX_OVERFLOW` | Обычно `5` и `5`: основные и дополнительные соединения. |
| `HTTP_BIND_ADDRESS`, `HTTPS_BIND_ADDRESS` | Обычно `0.0.0.0`: публикация на сетевых интерфейсах VPS. |
| `HTTP_PORT`, `HTTPS_PORT` | Обычно `80`, `443`: нужны для публичного HTTPS и получения сертификата. |

Примеры формы строк, а не готовые настройки:

```dotenv
POSTGRES_URL=postgresql+asyncpg://APP_USER:URL_ENCODED_PASSWORD@POSTGRES_HOST:5432/APP_DATABASE?ssl=require
VALKEY_URL=rediss://VALKEY_USER:URL_ENCODED_PASSWORD@VALKEY_HOST:6379/0
```

Хосты, порты, TLS и требования к сертификатам берите у провайдера. Кодируйте специальные символы логина и пароля для URL; например, `@` внутри пароля превращается в `%40`. Не отключайте проверку сертификатов как способ исправления ошибки подключения. Пароли и токены не должны попадать в Git, логи и историю команд. Для буквальных `$` и других специальных символов учитывайте правила env-файлов Docker Compose; URL-кодирование реквизитов также предотвращает нежелательную подстановку.

Закрепите владельца и права:

```bash
sudo chown root:root /etc/prettylisavpn/deployment.env
sudo chmod 600 /etc/prettylisavpn/deployment.env
sudo stat -c '%a %U:%G %n' /etc/prettylisavpn/deployment.env
```

Ожидается `600 root:root`. Проверка показывает только метаданные, не секреты. Полный перечень настроек приложения есть в [руководстве Backend](../backend/README.md).

## 6. Запустите и проверьте

Сначала проверьте DNS с VPS:

```bash
getent ahosts api.example.com
```

В ответе должны быть правильные адреса VPS. Для сертификата домен должен разрешаться также из публичного интернета, а порты 80/443 — быть доступны извне.

Запустите развёртывание:

```bash
cd /opt/prettylisavpn/repository
sudo bash ./infra/deployment/deploy.sh /etc/prettylisavpn/deployment.env
```

Скрипт проверяет права env-файла, домен и Compose-конфигурацию, скачивает образы, создаёт/заменяет контейнеры и ожидает liveness Backend. Затем проверяет публичный `/health`. DNS он не изменяет. Замена единственного Backend может вызвать краткий перерыв в обслуживании; бесшовное обновление эта схема не гарантирует.

После успешного выполнения обязательно проверьте все три метода:

```bash
curl --fail --show-error https://api.example.com/health
curl --fail --show-error https://api.example.com/ready
curl --fail --show-error https://api.example.com/version
```

Ожидается HTTP 200 у всех методов. `/ready` подтверждает доступность **обеих** баз; `/version` должен показать ожидаемую версию и окружение. Скрипт сам `/ready` не проверяет; Caddy также использует `/health` и не блокирует трафик автоматически при ошибке readiness.

Посмотрите контейнеры и последние сообщения:

```bash
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml ps
sudo docker compose -p prettylisavpn --env-file /etc/prettylisavpn/deployment.env -f infra/deployment/compose.yaml logs --follow --tail 200 backend caddy
```

`Ctrl+C` завершает просмотр логов. В текущем Caddyfile включён access log API-запросов: не передавайте секреты в URL и учитывайте это при дальнейшем добавлении API. Логи пользовательского VPN-трафика на этом сервере отсутствуют, поскольку сам трафик через него не идёт.

## 7. Дальнейшая эксплуатация

Оба контейнера используют `restart: unless-stopped`: после перезагрузки VPS они запускаются вместе с Docker, если не были явно остановлены. В согласованное окно можно проверить `sudo reboot`, повторно подключиться по SSH и повторить проверки API.

Для [обновления, обычного перезапуска, диагностики и отката](vps-maintenance.md) используйте отдельную инструкцию. Не удаляйте тома Caddy при штатных обновлениях. Автоматическое продление сертификата не заменяет резервные копии и проверку восстановления PostgreSQL.

Дополнительные источники: [установка Compose](https://docs.docker.com/compose/install/linux/) и [автоматический HTTPS Caddy](https://caddyserver.com/docs/automatic-https).
