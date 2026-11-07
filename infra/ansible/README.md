# Установка и обслуживание VPN-узлов

Для новых серверов на любом хостинге используйте
[инструкцию подключения узла](../../docs/server-enrollment.md).
Текущий fleet worker устанавливает базовые инструменты через
[configure.yml](../../backend/src/prettylisavpn/fleet/ubuntu/configure.yml).

Для Chrome-прокси [browser-proxy-certificate.yml](browser-proxy-certificate.yml)
выпускает и продлевает публичный сертификат после настройки DNS. Он не создаёт
DNS-записей: это отдельный авторизованный вызов API DNS-провайдера домена,
независимо от хостинга VPS. Перед включением proxy_host обязательны проверки
DNS, сертификата, firewall и реального трафика из инструкции.

Без DNS текущий Chrome также поддерживает доверенный сертификат на публичный IP:
[browser-proxy-ip-certificate.yml](browser-proxy-ip-certificate.yml). Этот путь
использует short-lived сертификат и собственный таймер продления; DNS-записи
не нужны, но проверка точного IP SAN, TLS, firewall и прямого трафика обязательна.

## Исторический VPN reset

The previous node-agent, WireGuard, OpenVPN, profile and obfuscator roles/playbooks
have been removed. No replacement VPN server is provisioned in this task.

The pre-reset source is preserved in merge commit
`dc3789904cb903eb100b9e35a3bea436146a753a` (PR #29).
See [the reset handoff](../../docs/vpn-placeholder-reset.md) for decommissioning
evidence and rollback boundaries. SSH and the account backend are separate services.
