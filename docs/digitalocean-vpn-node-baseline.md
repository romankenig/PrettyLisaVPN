# Базовая защита VPN-узла в DigitalOcean

Инструкция подготавливает первый выделенный узел контура передачи данных PrettyLisaVPN на Ubuntu 24.04 LTS. Она **не настраивает WireGuard**, маршрутизацию, NAT или будущий node agent. На узле не должны запускаться Backend, PostgreSQL, Valkey, Caddy и другие прикладные сервисы. Docker также не устанавливается.

Команды рассчитаны на новый Droplet из официального образа Ubuntu 24.04, созданный с SSH-ключом. Все команды в блоках `bash` выполняются **на Droplet**, если явно не указано обратное. Команды `ssh` выполняются на рабочем компьютере администратора.

Перед началом:

- добавьте SSH-ключ администратора при создании Droplet;
- назначьте Droplet постоянный понятный hostname и запишите его IPv4/IPv6;
- сохраните в менеджере секретов имя административного пользователя;
- откройте страницу Droplet в панели DigitalOcean, чтобы при ошибке воспользоваться Recovery Console;
- не закрывайте исходный root-сеанс до проверки отдельного входа новым пользователем.

В примерах используются заполнители `DROPLET_IP`, `ADMIN_PUBLIC_IP` и пользователь `vpnadmin`. Замените их реальными значениями. `ADMIN_PUBLIC_IP` должен быть одиночным публичным адресом в формате `203.0.113.10/32`; если адрес администратора непостоянный, используйте более узкую доверенную сеть либо временно разрешите SSH отовсюду, как описано ниже.

## 1. Настройте DigitalOcean Cloud Firewall

До изменения host firewall создайте в **Networking → Firewalls** отдельный Cloud Firewall, например `prettylisavpn-vpn-nodes`, и прикрепите его к Droplet напрямую или по отдельному тегу VPN-узлов.

Начальное состояние правил:

| Направление | Протокол | Порт | Источник/назначение | Назначение |
| --- | --- | --- | --- | --- |
| Inbound | TCP | 22 | `ADMIN_PUBLIC_IP` | SSH администрирование |
| Outbound | ICMP | все | все IPv4 и IPv6 | диагностика и служебная сеть |
| Outbound | TCP | все | все IPv4 и IPv6 | обновления, DNS по TCP и будущие исходящие соединения |
| Outbound | UDP | все | все IPv4 и IPv6 | DNS, NTP и будущий VPN-трафик |

Других inbound allow-правил пока быть не должно. Правило WireGuard UDP добавляется одновременно с настройкой WireGuard, не сейчас. Если к Droplet прикреплено несколько Cloud Firewalls, проверьте их все: разрешения объединяются, и более широкое правило другого firewall может открыть порт.

Если доверенного стабильного адреса нет, временно укажите для SSH `All IPv4` и при необходимости `All IPv6`. После появления стабильного адреса сузьте источник одновременно в Cloud Firewall и UFW. Никогда не удаляйте единственное работающее SSH-правило до проверки заменяющего правила.

## 2. Первый вход и фиксация исходного состояния

На рабочем компьютере:

```sh
ssh root@DROPLET_IP
```

На Droplet убедитесь, что это ожидаемый образ, и сохраните сведения для журнала работ:

```bash
cat /etc/os-release
uname -a
ip -brief address
ss -lntup
systemctl --failed
systemctl list-unit-files --state=enabled
```

Ожидается Ubuntu 24.04 LTS. Разберите неожиданные слушающие порты, failed units и сторонние enabled services до продолжения. Не публикуйте полный вывод команд, если позднее в нём появятся внутренние адреса или другая чувствительная информация.

## 3. Создайте административного пользователя

Создайте отдельного пользователя с локальным паролем. Этот пароль не будет разрешён для SSH, но пригодится для `sudo` и входа через Recovery Console:

```bash
adduser vpnadmin
usermod --append --groups sudo vpnadmin
id vpnadmin
```

Если baseline применяется автоматизированно и локальный пароль нельзя безопасно передать оператору, вместо `adduser` используйте пользователя с заблокированным паролем и passwordless sudo. Именно этот вариант не требует создания, вывода или сохранения секрета:

```bash
useradd --create-home --shell /bin/bash vpnadmin
passwd --lock vpnadmin
usermod --append --groups sudo vpnadmin
printf '%s\n' 'vpnadmin ALL=(ALL:ALL) NOPASSWD: ALL' > /etc/sudoers.d/90-vpnadmin
chmod 0440 /etc/sudoers.d/90-vpnadmin
visudo -cf /etc/sudoers.d/90-vpnadmin
```

Используйте только один вариант. Во втором варианте Recovery Console login через `vpnadmin` невозможен: для аварийного доступа сбросьте root password через панель DigitalOcean, как описано ниже. Компрометация административного SSH-ключа в этом варианте сразу даёт root через sudo, поэтому ключ должен храниться и ротироваться как привилегированный секрет.

Скопируйте уже проверенный публичный ключ из root-аккаунта, сохранив безопасные права:

```bash
install -d -m 0700 -o vpnadmin -g vpnadmin /home/vpnadmin/.ssh
install -m 0600 -o vpnadmin -g vpnadmin /root/.ssh/authorized_keys /home/vpnadmin/.ssh/authorized_keys
namei -l /home/vpnadmin/.ssh/authorized_keys
```

Если `/root/.ssh/authorized_keys` отсутствует, остановитесь и добавьте **публичный**, не приватный, ключ вручную:

```bash
install -d -m 0700 -o vpnadmin -g vpnadmin /home/vpnadmin/.ssh
sudo -u vpnadmin nano /home/vpnadmin/.ssh/authorized_keys
chmod 0600 /home/vpnadmin/.ssh/authorized_keys
chown vpnadmin:vpnadmin /home/vpnadmin/.ssh/authorized_keys
```

Не закрывая первый сеанс, откройте **второй терминал** на рабочем компьютере:

```sh
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no vpnadmin@DROPLET_IP
sudo -v
whoami
```

Вход должен пройти без пароля SSH-аккаунта; `sudo -v` должен принять локальный пароль `vpnadmin`; `whoami` должен вывести `vpnadmin`. Для варианта с passwordless sudo вместо `sudo -v` выполните `sudo -n id` и ожидайте `uid=0(root)`. Не продолжайте, если эта проверка не прошла.

Если официальный образ уже создал подходящего не-root пользователя с рабочим ключом и членством в `sudo`, можно использовать его вместо `vpnadmin`. Тогда во всех последующих командах и проверках замените имя пользователя, а новый аккаунт не создавайте.

## 4. Обновите систему

Войдите как `vpnadmin` и выполните:

```bash
sudo apt-get update
sudo apt-get full-upgrade --yes
sudo apt-get install --yes ufw unattended-upgrades
sudo apt-get autoremove --purge --yes
sudo apt-get clean
```

Включите ежедневную проверку обновлений и автоматическую установку security updates через штатную конфигурацию Ubuntu:

```bash
printf '%s\n' \
  'APT::Periodic::Update-Package-Lists "1";' \
  'APT::Periodic::Unattended-Upgrade "1";' \
  | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
sudo unattended-upgrade --dry-run --debug
systemctl status apt-daily.timer apt-daily-upgrade.timer --no-pager
```

Dry run должен завершиться без ошибки, оба timer unit должны быть загружены. Автоматическую перезагрузку намеренно не включаем: перезапуск VPN-узла должен происходить в контролируемое окно. Наличие требуемой перезагрузки проверяется так:

```bash
if test -f /var/run/reboot-required; then cat /var/run/reboot-required.pkgs; fi
```

## 5. Настройте минимальный host firewall

Сначала задайте безопасные политики и правило SSH, затем включите UFW. Вариант со стабильным адресом администратора:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw default deny routed
sudo ufw logging off
sudo ufw limit proto tcp from ADMIN_PUBLIC_IP to any port 22 comment 'SSH administration'
sudo ufw --force enable
sudo ufw status verbose
sudo ufw status numbered
```

Если адрес администратора непостоянный, временное правило выглядит так:

```bash
sudo ufw limit 22/tcp comment 'SSH administration temporary'
```

Используйте только один из двух вариантов. `limit` уменьшает эффективность перебора, но не заменяет ограничение по адресу и ключевую аутентификацию. UFW logging выключен, чтобы узел не создавал журналы пакетов или адресов пользовательского трафика. Системные authentication/service logs остаются включёнными; они нужны для защиты и эксплуатации, но не должны содержать browsing destinations, DNS queries, URL или packet contents.

Снова проверьте новый SSH-вход из отдельного терминала **после** включения UFW:

```sh
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no vpnadmin@DROPLET_IP
```

Ожидаемое состояние `ufw status verbose` до WireGuard:

```text
Status: active
Logging: off
Default: deny (incoming), allow (outgoing), disabled (routed)

To                         Action      From
--                         ------      ----
22/tcp                     LIMIT IN    ADMIN_PUBLIC_IP
```

На Ubuntu 24.04 при выключенном IP forwarding UFW показывает `disabled (routed)`, даже если задан `ufw default deny routed`; подтвердите фактический безопасный policy командой `grep '^DEFAULT_FORWARD_POLICY=' /etc/default/ufw`, ожидая `DROP`. UFW может показать отдельные IPv6-правила в варианте с доступом отовсюду. Никакие HTTP, HTTPS, database, cache, Docker API или VPN-порты открыты быть не должны.

## 6. Усильте SSH только после проверки ключа

Ubuntu читает snippets в лексикографическом порядке, а OpenSSH для большинства параметров использует первое найденное значение. Поэтому имя `00-prettylisavpn-hardening.conf` намеренно должно предшествовать создаваемому cloud-init файлу `50-cloud-init.conf`.

Создайте конфигурацию:

```bash
test ! -e /etc/ssh/sshd_config.d/00-prettylisavpn-hardening.conf
sudo install -m 0644 -o root -g root /dev/null /etc/ssh/sshd_config.d/00-prettylisavpn-hardening.conf
printf '%s\n' \
  'PubkeyAuthentication yes' \
  'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' \
  'PermitRootLogin no' \
  'PermitEmptyPasswords no' \
  'AuthenticationMethods publickey' \
  'MaxAuthTries 3' \
  'LoginGraceTime 30' \
  'X11Forwarding no' \
  'AllowAgentForwarding no' \
  'AllowTcpForwarding no' \
  'PermitTunnel no' \
  | sudo tee /etc/ssh/sshd_config.d/00-prettylisavpn-hardening.conf >/dev/null
sudo sshd -t
sudo sshd -T -C user=vpnadmin,host="$(hostname -f)",addr=ADMIN_PUBLIC_IP_WITHOUT_CIDR \
  | grep -E '^(pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitrootlogin|authenticationmethods|maxauthtries|x11forwarding|allowagentforwarding|allowtcpforwarding|permittunnel) '
```

Замените `ADMIN_PUBLIC_IP_WITHOUT_CIDR` адресом без `/32`. В effective output должны быть `pubkeyauthentication yes`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `permitrootlogin no`, `authenticationmethods publickey` и отключённые forwarding/tunnel options. Если `sshd -t` сообщает ошибку или effective output отличается, **не перезагружайте SSH**; исправьте конфигурацию из текущего открытого сеанса.

Примените проверенную конфигурацию без разрыва текущих соединений:

```bash
sudo systemctl reload ssh
sudo systemctl is-active ssh
```

В третьем терминале проверьте ключевой вход и убедитесь, что password-only и root SSH отвергаются:

```sh
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no vpnadmin@DROPLET_IP
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive vpnadmin@DROPLET_IP
ssh root@DROPLET_IP
```

Первая команда должна открыть сеанс. Вторая должна завершиться `Permission denied` без предложения рабочего password login. Третья не должна разрешить root login даже при наличии root key. Текущие открытые сеансы не доказывают, что новая политика работает, поэтому нужен именно новый вход.

## 7. Отключите только действительно ненужные службы

Сначала повторите аудит:

```bash
sudo ss -lntup
systemctl --type=service --state=running --no-pager
systemctl list-unit-files --state=enabled --no-pager
```

На dedicated headless Droplet не нужны службы печати, локального service discovery, desktop crash reporting и управления мобильными модемами. Следующая команда отключает их, только если соответствующий unit установлен; отсутствие unit не считается ошибкой:

```bash
for unit in avahi-daemon.service cups.service cups-browsed.service ModemManager.service whoopsie.service; do
  if systemctl list-unit-files "$unit" --no-legend 2>/dev/null | grep -q "^$unit"; then
    sudo systemctl disable --now "$unit"
  fi
done
```

Стандартный cloud image также может запустить `udisks2` и `multipathd`. Отключайте их только после подтверждения, что узел использует обычный virtio-диск и не имеет multipath storage:

```bash
lsblk -o NAME,TYPE,PKNAME,MOUNTPOINTS
sudo multipath -ll
sudo systemctl stop udisks2.service
sudo systemctl mask udisks2.service
sudo systemctl disable --now multipathd.service multipathd.socket
sudo systemctl mask multipathd.service multipathd.socket
```

Для `ModemManager` на виртуальном сервере можно дополнительно запретить повторную D-Bus активацию:

```bash
sudo systemctl mask ModemManager.service
```

Не отключайте `ssh`, `systemd-networkd`, `systemd-resolved`, `systemd-timesyncd`, `cloud-init`, `cloud-final`, `cron`, `dbus`, `polkit`, `unattended-upgrades` или DigitalOcean guest/monitoring agents, если они были сознательно установлены. Не удаляйте `snapd` вслепую: сначала выясните, использует ли его образ. Не устанавливайте Docker, PostgreSQL, Valkey, Caddy или Backend.

Повторите команды аудита и расследуйте любой процесс, слушающий публичный адрес. До WireGuard ожидается только SSH на TCP/22; локальные DNS stub и DHCP-клиенты не являются публичными сервисами.

## 8. Итоговая проверка и перезагрузка

На Droplet:

```bash
sudo sshd -t
sudo systemctl is-active ssh
sudo ufw status verbose
sudo ss -lntup
systemctl --failed
sudo apt-get update
apt list --upgradable
test ! -e /usr/bin/docker && echo 'Docker is not installed'
dpkg-query -W docker-ce docker.io postgresql valkey caddy 2>/dev/null || true
```

Ожидается:

- `ssh` active, а новый key-only login работает;
- UFW active с logging off и единственным inbound разрешением TCP/22;
- Cloud Firewall имеет только SSH inbound;
- нет публичных listeners, кроме TCP/22;
- нет failed units;
- список обновлений пуст либо содержит только отложенные/phased updates;
- Docker, PostgreSQL, Valkey, Caddy и Backend отсутствуют;
- IP forwarding не включался, WireGuard interfaces и правила NAT отсутствуют.

Если `/var/run/reboot-required` существует, перезагрузите узел из проверенного key-based сеанса:

```bash
sudo reboot
```

После возврата Droplet повторите:

```sh
ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no vpnadmin@DROPLET_IP
```

```bash
uptime
sudo systemctl is-active ssh
sudo ufw status verbose
sudo ss -lntup
systemctl --failed
```

Только после этой проверки закройте первоначальный root-сеанс, если он ещё существует.

## Откат обычных изменений

### UFW заблокировал нужный административный адрес

Из ещё открытого SSH-сеанса добавьте правильный адрес, проверьте новый вход и только затем удалите старое правило:

```bash
sudo ufw allow proto tcp from CORRECT_ADMIN_PUBLIC_IP to any port 22 comment 'SSH recovery'
sudo ufw status numbered
```

Для полного временного отключения host firewall из Recovery Console:

```bash
ufw disable
```

После восстановления SSH исправьте правила и снова выполните `ufw --force enable`. Cloud Firewall продолжает действовать независимо от UFW; при неверном cloud rule его нужно исправить в панели DigitalOcean.

### Ошибка SSH-конфигурации

Из ещё открытого сеанса или Recovery Console:

```bash
rm -f /etc/ssh/sshd_config.d/00-prettylisavpn-hardening.conf
sshd -t
systemctl restart ssh
```

Это возвращает политику официального образа/cloud-init, которая может разрешать root или password login. После восстановления доступа снова установите исправленный snippet и повторите все проверки раздела 6.

### Ненужная служба оказалась необходимой

```bash
systemctl unmask UNIT_NAME.service
systemctl enable --now UNIT_NAME.service
systemctl status UNIT_NAME.service --no-pager
```

## Восстановление через DigitalOcean Recovery Console

Recovery Console работает вне сетевого пути Droplet и доступна даже при сломанной сети или `sshd`, но требует локальный пароль. Используйте её только для восстановления:

1. В DigitalOcean Control Panel откройте Droplet → **Settings** → **Recovery Console** → **Launch Console**.
2. Войдите как `vpnadmin` с сохранённым локальным паролем и выполните `sudo -i`.
3. Если пароль недоступен, в **Settings** используйте **Reset Root Password**, получите временный пароль по email, затем войдите как `root` через Recovery Console и смените временный пароль.
4. Проверьте `ip -brief address`, `systemctl status ssh`, `sshd -t`, `ufw status verbose` и `journalctl -u ssh -b --no-pager`.
5. Примените подходящий откат из предыдущего раздела. Сначала восстановите SSH, затем снова включите ограничивающий firewall.
6. Из обычного терминала подтвердите новый key-only SSH-вход. После этого заново примените hardening и удалите временные широкие firewall rules.

Если система не загружается или файловая система недоступна, в Settings переключите Droplet на загрузку с **Recovery ISO**, запустите Recovery Console, смонтируйте диск по инструкциям DigitalOcean и исправьте файлы на смонтированной системе. После ремонта верните обычный boot disk и перезагрузите Droplet.

Сброс root password является аварийной мерой. После восстановления убедитесь, что `PermitRootLogin no` снова эффективно для SSH, и сохраните новый recovery password в менеджере секретов либо снова заблокируйте локальный root password только после проверки доступности Recovery Console через `vpnadmin`.

## Что сознательно осталось за рамками

- WireGuard packages, keys, interface, UDP port, forwarding, routing и NAT;
- node agent и его runtime;
- Docker и контейнеры;
- Backend, PostgreSQL, Valkey, Caddy и любые control-plane services;
- traffic/content/DNS logging и deep packet inspection;
- monitoring agent, поскольку требования к телеметрии узла ещё не определены.

При следующем этапе правила обоих firewalls, forwarding и telemetry нужно менять согласованно. Никогда не включайте журналирование browsing destinations, DNS queries, URL или packet contents.

## Официальные источники

- [Ubuntu Server: firewall и UFW](https://documentation.ubuntu.com/server/how-to/security/firewalls/)
- [Ubuntu Security: автоматические security updates](https://documentation.ubuntu.com/security/security-updates/)
- [Ubuntu 24.04 release notes: OpenSSH socket activation](https://documentation.ubuntu.com/release-notes/24.04/)
- [OpenSSH `sshd_config(5)`: порядок обработки Include](https://man.openbsd.org/sshd_config)
- [DigitalOcean: настройка Cloud Firewall rules](https://docs.digitalocean.com/products/networking/firewalls/how-to/configure-rules/)
- [DigitalOcean: восстановление доступа через Recovery Console](https://docs.digitalocean.com/products/droplets/how-to/recovery/recovery-console/)
