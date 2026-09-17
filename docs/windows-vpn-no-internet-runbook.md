# PrettyLisaVPN: Windows показывает Connected, но интернет не работает

Этот документ предназначен для диагностики первого VPN-узла `204.48.17.50` и
Windows-клиента. Команды не выводят WireGuard private keys и не перехватывают
пакеты, DNS-запросы или посещаемые адреса.

## Что уже установлено

- Клиент получает адрес `10.77.0.2/32`, MTU 1280 и full-tunnel
  `AllowedIPs = 0.0.0.0/0`.
- Endpoint WireGuard переведён на `204.48.17.50:443/udp` и открыт в UFW и
  DigitalOcean Cloud Firewall.
- На сервере включён `net.ipv4.ip_forward=1`; forwarding из `wg0` в фактический
  публичный интерфейс `eth0` и MASQUERADE для `10.77.0.0/16` настроены.
- В проведённых тестах Windows выбирал адаптер PrettyLisaVPN для публичных IPv4,
  endpoint `/32` шёл через физический Wi-Fi, WireGuard handshake происходил, а
  серверные forward/NAT counters увеличивались.
- Ошибка воспроизводилась и после полного выхода из Kaspersky VPN. Kaspersky/WFP
  может создавать дополнительный конфликт, но не является единственной причиной.

## Возможные причины по текущему коду

### Наиболее вероятные или ещё не исключённые

1. **Ответные пакеты не доходят из WireGuardNT до Windows-сокета.** Handshake
   подтверждает только достижимость endpoint и правильность ключей. Он не доказывает,
   что декодированный IPv4-трафик принимается TCP/IP stack Windows. Причиной могут
   быть WFP-фильтр, endpoint security, Windows Firewall, конфликтующий виртуальный
   адаптер или повреждённое состояние WireGuardNT.
2. **Конфликт маршрутов с другим VPN/виртуальным адаптером.** Клиент создаёт восемь
   маршрутов `/3` через PrettyLisaVPN и `/32` к endpoint через прежний default route.
   WFP callout другого VPN способен перенаправить сокет независимо от видимой
   route table. Маршрут endpoint также может быть привязан к уже нерабочему default
   route.
3. **Существующий конфликтующий маршрут принимается за успешный.** При
   `ERROR_OBJECT_ALREADY_EXISTS` клиент не проверяет interface/next-hop существующей
   записи и не удаляет её при остановке. Старый `/32` или `/3` способен пережить
   неудачный запуск и направлять трафик не туда.
4. **Выбор неправильного underlay для endpoint.** До старта клиент выбирает default
   route по полю route metric. Эффективный выбор Windows также учитывает interface
   metric и состояние интерфейса. При нескольких `0.0.0.0/0` `/32` к endpoint может
   получить неверный gateway.
5. **Состояние Connected со временем становится ложным.** После запуска `status()`
   проверяет только `adapter.is_up()`, но не свежесть handshake, transfer counters и
   возможность передачи данных. Исчезнувший peer, firewall или маршрут не переводят
   поднятый адаптер в Down.
6. **Peer удаляется backend-ом после первоначального handshake.** Возможны expiry,
   reconciliation, конкурирующая сессия устройства, cleanup после client timeout или
   рассинхронизация public key/IP. Адаптер при этом остаётся поднятым.
7. **MTU/PMTUD black hole.** MTU 1280 уменьшает риск, но фильтрация ICMP,
   дополнительная VPN-инкапсуляция или неправильный MTU underlay всё ещё могут
   пропускать handshake и ломать HTTPS.

### Проверки клиента, которые могут давать неполную картину

8. **Data-plane probe зависит от одного внешнего адреса.** До Connected код проверяет
   только TCP `1.1.1.1:443`. Фильтрация именно этого адреса даёт ложный отказ, а его
   доступность не доказывает работу DNS или остальных направлений.
9. **Проверяются только два из восьми `/3` маршрутов.** Валидация смотрит
   `1.1.1.1` и `129.1.1.1`; ошибка в другом диапазоне останется незамеченной.
10. **DNS включается только после TCP probe.** Во время CONNECTING отсутствие DNS на
    PrettyLisaVPN ожидаемо. После Connected DNS задаётся adapter-scoped через `netsh`,
    без NRPT; multi-homed DNS, WFP или другой VPN могут выбрать другой resolver.
11. **IPv6 не туннелируется.** Текущая задача реализует только IPv4. При рабочем IPv6
    приложения могут обходить VPN (leak) или сначала зависать на AAAA/IPv6, создавая
    впечатление отсутствия интернета.
12. **Процесс клиента или сборка устарели.** Hot reload не заменяет уже загруженный
    Rust binary/DLL. Старый процесс мог показывать Connected сразу после `adapter.up`,
    не выполняя актуальные проверки.
13. **WireGuardNT DLL/права.** Отсутствующая, несовместимая или неверной архитектуры
    `wireguard.dll`, а также запуск без elevation ломают создание/настройку адаптера.
    Для текущей машины успешный handshake делает эту причину менее вероятной.

### Сервер и control plane

14. **Несовпадение портов.** Backend, `wg0`, UFW и DigitalOcean Cloud Firewall должны
    одновременно использовать `443/udp`. В репозитории общий Ansible default всё ещё
    `51820`; повторный deploy без host override вернёт сервер на 51820 и создаст drift.
15. **Неверный peer.** На `wg0` должны совпасть client public key и единственный
    `AllowedIPs = 10.77.0.2/32`; дубликат этого IP у другого peer недопустим.
16. **Forwarding/NAT сломаны после reboot/deploy.** Возможны `ip_forward=0`, неверный
    egress interface, отсутствующий обратный ESTABLISHED rule, MASQUERADE не для того
    subnet/interface, UFW reload или `rp_filter=1`.
17. **Provider/сеть блокирует UDP или return traffic.** Cloud Firewall, UFW, локальная
    сеть/ISP или captive portal могут пропускать не все направления. UDP/443 снижает,
    но не исключает риск.
18. **Backend выдаёт устаревший transport config.** Неверные endpoint port, server
    public key, client IP, DNS или `AllowedIPs` ломают разные этапы подключения.

## Ручная проверка: один чистый прогон

Все Windows-команды выполняются в **PowerShell от имени администратора**. Не
публикуйте полный вывод `wg show`: public keys и endpoint не являются private keys,
но это внутренняя инфраструктурная информация.

### 1. Состояние до подключения

Полностью выйдите из Kaspersky VPN, а не только нажмите Disconnect, затем проверьте:

```powershell
Get-Process ksde,ksdeui -ErrorAction SilentlyContinue
Get-NetAdapter -IncludeHidden | Sort-Object Name | Format-Table Name,Status,InterfaceDescription
Get-NetRoute -AddressFamily IPv4 -DestinationPrefix 0.0.0.0/0 |
  Sort-Object RouteMetric | Format-Table InterfaceAlias,NextHop,RouteMetric,State
Test-NetConnection 204.48.17.50 -Port 22 -InformationLevel Detailed
```

Пустой результат `Get-Process` означает полный выход. Недоступность TCP/22 сама по
себе не проверяет UDP/443 и не доказывает неисправность WireGuard.

Закройте все процессы PrettyLisaVPN, затем запустите актуальную сборку один раз от
администратора. Это исключает старый Rust process после hot reload.

### 2. Во время CONNECTING/Connected

Сразу после нажатия CONNECT выполните:

```powershell
Get-NetAdapter -IncludeHidden -Name PrettyLisaVPN |
  Format-List Name,Status,InterfaceIndex,InterfaceDescription
Get-NetIPAddress -InterfaceAlias PrettyLisaVPN -AddressFamily IPv4 |
  Format-Table IPAddress,PrefixLength,AddressState
Get-NetIPInterface -InterfaceAlias PrettyLisaVPN -AddressFamily IPv4 |
  Format-Table InterfaceIndex,NlMtu,InterfaceMetric,ConnectionState
Get-NetRoute -InterfaceAlias PrettyLisaVPN -AddressFamily IPv4 |
  Sort-Object DestinationPrefix | Format-Table DestinationPrefix,NextHop,RouteMetric,State
Find-NetRoute -RemoteIPAddress 204.48.17.50
Find-NetRoute -RemoteIPAddress 1.1.1.1
Find-NetRoute -RemoteIPAddress 129.1.1.1
Get-DnsClientServerAddress -InterfaceAlias PrettyLisaVPN -AddressFamily IPv4
```

Ожидается:

- `10.77.0.2/32`, MTU `1280`, adapter `Up`;
- восемь `/3` через PrettyLisaVPN;
- `204.48.17.50` выбирает физический адаптер/gateway, не PrettyLisaVPN;
- `1.1.1.1` и `129.1.1.1` выбирают PrettyLisaVPN;
- DNS `1.1.1.1, 1.0.0.1` появляется только после успешного data-plane probe.

Проверьте все восемь диапазонов, а не только два, которые валидирует код:

```powershell
'1.1.1.1','33.1.1.1','65.1.1.1','97.1.1.1','129.1.1.1','161.1.1.1','193.1.1.1','225.1.1.1' |
  ForEach-Object {
    $route = Find-NetRoute -RemoteIPAddress $_
    [pscustomobject]@{ Destination = $_; Interface = $route.InterfaceAlias; NextHop = $route.NextHop }
  } | Format-Table
```

Каждая строка, кроме endpoint bypass, должна указывать PrettyLisaVPN.

### 3. Разделить routing, DNS и HTTPS

```powershell
Test-NetConnection 1.1.1.1 -Port 443 -InformationLevel Detailed
curl.exe --noproxy "*" --connect-timeout 10 --resolve example.com:443:104.20.34.220 https://example.com/
Resolve-DnsName example.com -Server 1.0.0.1 -DnsOnly
Resolve-DnsName example.com -DnsOnly
curl.exe --noproxy "*" --connect-timeout 10 https://api.ipify.org
```

Интерпретация:

| Результат | Вывод |
| --- | --- |
| Fixed-IP HTTPS не работает | проблема ниже DNS: route, WireGuard data plane, firewall, NAT или return path |
| Fixed-IP HTTPS работает, explicit DNS нет | DNS-пакеты/UDP-TCP 53 не проходят через tunnel/server |
| Explicit DNS работает, system DNS нет | Windows DNS binding/NRPT/WFP conflict |
| Всё работает, но public IP не `204.48.17.50` | трафик обходит VPN или перехвачен другим VPN/WFP |
| Public IP `204.48.17.50` | end-to-end IPv4 full tunnel работает |

`104.20.34.220` является только тестовым адресом и может измениться; основной
вывод делайте по `Test-NetConnection 1.1.1.1` и серверным counters.

### 4. Одновременно проверить сервер без packet capture

Откройте Recovery Console или отдельную SSH-сессию к Droplet и сохраните её. До
клиентского запроса выполните:

```bash
sudo ss -lunp | grep ':443 '
sudo wg show wg0 latest-handshakes
sudo wg show wg0 transfer
sudo ip route get 1.1.1.1
sudo sysctl net.ipv4.ip_forward net.ipv4.conf.all.rp_filter net.ipv4.conf.eth0.rp_filter
sudo iptables -nvL ufw-user-forward
sudo iptables -nvL ufw-before-forward
sudo iptables -t nat -nvL POSTROUTING
sudo ufw status numbered
```

Затем на Windows один раз запустите:

```powershell
Test-NetConnection 1.1.1.1 -Port 443 -InformationLevel Detailed
```

И немедленно повторите на сервере:

```bash
sudo wg show wg0 latest-handshakes
sudo wg show wg0 transfer
sudo iptables -nvL ufw-user-forward
sudo iptables -nvL ufw-before-forward
sudo iptables -t nat -nvL POSTROUTING
```

Диагностическая матрица:

| Изменение counters | Где неисправность |
| --- | --- |
| Нет свежего handshake | endpoint/UDP firewall/ключи/peer |
| Handshake есть, peer RX не растёт | Windows route/WFP/WireGuardNT не отправляет data packets |
| Peer RX растёт, forward/NAT нет | серверный firewall/rule ordering/subnet/interface |
| NAT растёт, peer TX не растёт | публичный egress или return path на сервере |
| Peer RX и TX растут, Windows TCP timeout | Windows WireGuardNT/WFP/firewall/route delivery |

Это ключевой тест: он локализует поломку без записи содержимого трафика.

### 5. Проверить peer и конфигурационный drift

На сервере:

```bash
sudo wg show wg0 listen-port
sudo wg show wg0 public-key
sudo wg show wg0 allowed-ips
sudo systemctl is-active wg-quick@wg0
sudo systemctl is-active prettylisavpn-node-agent
sudo grep -E '^(Address|ListenPort|SaveConfig)' /etc/wireguard/wg0.conf
```

Ожидаются port `443`, gateway `10.77.0.1/16`, сервисы `active`, а активный client
peer должен иметь только выделенный `/32`. Никогда не выполняйте и не пересылайте
`wg show wg0 private-key`.

В backend проверьте, что запись этого узла также содержит port 443. Перед следующим
Ansible deploy задайте host-specific `wireguard_listen_port: 443`; общий default
`51820` оставлен как документированный default и не должен молча переопределять live
node.

### 6. Изолировать Windows Firewall/WFP

Сначала только просмотрите состояние — не отключайте firewall целиком:

```powershell
Get-NetFirewallProfile | Format-Table Name,Enabled,DefaultInboundAction,DefaultOutboundAction
Get-NetFirewallRule -PolicyStore ActiveStore |
  Where-Object DisplayName -Match 'PrettyLisa|WireGuard|Kaspersky' |
  Format-Table DisplayName,Enabled,Direction,Action,Profile
Get-NetAdapterBinding -Name PrettyLisaVPN | Format-Table DisplayName,ComponentID,Enabled
```

Если серверная матрица показывает `peer RX и TX растут`, но Windows всё равно получает
timeout, можно временно добавить узкое диагностическое разрешение только для tunnel
interface:

```powershell
New-NetFirewallRule -DisplayName 'PrettyLisaVPN diagnostic inbound' `
  -Direction Inbound -Action Allow -InterfaceAlias PrettyLisaVPN -Profile Any
```

Повторите один тест и обязательно удалите правило:

```powershell
Remove-NetFirewallRule -DisplayName 'PrettyLisaVPN diagnostic inbound'
```

Если это меняет результат, нужна постоянная ограниченная firewall policy. Если нет —
причина вероятнее в стороннем WFP callout/driver или WireGuardNT, а не в Defender rule.

### 7. MTU-тест

```powershell
ping.exe -4 -f -l 1200 1.1.1.1
ping.exe -4 -f -l 1000 1.1.1.1
```

ICMP может быть запрещён, поэтому оба timeout не являются доказательством. Если 1000
работает, а 1200 нет, это сильный признак MTU/PMTUD. Подтвердите его HTTPS-запросом,
а не только ping.

### 8. После DISCONNECT

```powershell
Get-NetAdapter -IncludeHidden -Name PrettyLisaVPN -ErrorAction SilentlyContinue
Get-NetRoute -AddressFamily IPv4 |
  Where-Object { $_.InterfaceAlias -eq 'PrettyLisaVPN' -or $_.DestinationPrefix -eq '204.48.17.50/32' } |
  Format-Table DestinationPrefix,InterfaceAlias,NextHop,State
Get-NetRoute -AddressFamily IPv4 -DestinationPrefix 0.0.0.0/0 |
  Format-Table InterfaceAlias,NextHop,RouteMetric,State
```

PrettyLisaVPN может остаться как скрытый/down adapter, но активных `/3` и созданного
клиентом endpoint `/32` быть не должно. Если они остались, перезагрузите Windows перед
следующим чистым тестом и зафиксируйте вывод до перезагрузки.

## Что прислать для следующего исправления

Нужен один синхронный прогон и только эти безопасные сведения:

1. вывод трёх `Find-NetRoute` и список восьми `/3`;
2. успешность fixed-IP HTTPS, explicit DNS и system DNS;
3. до/после численные RX/TX из `wg show wg0 transfer` (public key можно замазать);
4. до/после packet/byte counters нужных forward и MASQUERADE rules;
5. свежесть handshake в секундах;
6. был ли Kaspersky полностью завершён и была ли Windows перезагружена после прошлой
   неудачной сессии.

Не присылайте private keys, access tokens, cookies или полный environment.
