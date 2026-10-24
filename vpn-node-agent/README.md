# PrettyLisaVPN VPN Node Control Agent

The node agent is a minimal control-plane service that runs directly on each VPN Droplet. It can add, remove, and inspect runtime WireGuard peers and report health plus aggregate operational counts. It never receives client private keys, proxies traffic, inspects packets, calls the DigitalOcean API, or records URLs, DNS queries, destinations, credentials, or packet payloads.

## Security model

Production transport uses mutual TLS directly in Uvicorn with `CERT_REQUIRED`. The Backend must present a certificate signed by the client CA installed on the node. Every `/v1` route also requires `Authorization: Bearer ...`; comparisons are constant-time and the token is never logged. API documentation and Uvicorn access logs are disabled.

The systemd service runs as `prettylisa-agent`, without a login shell or home directory. Its only ambient/bounding capability is `CAP_NET_ADMIN`, required for WireGuard netlink operations. Filesystem, devices, namespaces, kernel settings, process visibility, and address families are restricted. The agent cannot read the WireGuard server private key. It deliberately avoids `wg show ... dump`, whose interface row contains private-key material.

The API is public-address reachable only because the current Backend and Droplet do not share a private network. Both firewalls must allow TCP/8443 exclusively from `BACKEND_PUBLIC_IPV4/32`:

- DigitalOcean Cloud Firewall: inbound TCP/8443 from the Backend public IPv4 `/32` only;
- UFW: the Ansible role creates the equivalent interface-, destination-IP-, source-IP-, and port-scoped rule;
- retain existing TCP/22 administration and UDP/51820 WireGuard rules;
- do not add an Internet-wide TCP/8443 rule.

## API

Version 0.2.0 optionally supports `PUT /v1/managed/{session_id}` (private UUID
credential and fixed deadline) and `DELETE /v1/managed/{session_id}` (confirmed
process removal). Both use the same mTLS/bearer boundary. Without
`NODE_AGENT_MANAGED_CONFIG` they return 503. The optional process receives private
configuration only through stdin. See [managed acceptance](../docs/managed-vpn-acceptance.md)
for the development-only rollout, isolated high-port range and rollback order.

All requests require a trusted client certificate and bearer token.

| Method | Path | Purpose |
| --- | --- | --- |
| `PUT` | `/v1/peers` | Add `{public_key, vpn_ip}` idempotently |
| `DELETE` | `/v1/peers` | Remove `{public_key}` idempotently |
| `GET` | `/v1/peers?public_key=...` | Query existence and latest handshake time |
| `GET` | `/v1/health` | Interface state and listen port |
| `GET` | `/v1/metrics` | Uptime, peer count, recent-handshake count, interface state |

Only a canonical 32-byte base64 WireGuard public key and a single IPv4 address inside the configured client subnet are accepted. Network, broadcast, and gateway addresses are rejected. A key cannot silently change IP, and an IP cannot be assigned to two peers. `wg` and `ip` are invoked with fixed paths and argument arrays with `shell=False`; request values are never interpolated into command strings.

Peers are runtime state. They are intentionally absent from `wg0.conf` and disappear on node reboot; the future Backend orchestration layer must reconcile valid sessions after a restart.

## Build and test

From the repository root, using Python 3.12 or 3.13:

```bash
python -m venv vpn-node-agent/.venv
vpn-node-agent/.venv/bin/python -m pip install -e './vpn-node-agent[dev]'
vpn-node-agent/.venv/bin/ruff check vpn-node-agent
vpn-node-agent/.venv/bin/mypy --config-file vpn-node-agent/pyproject.toml vpn-node-agent/src
vpn-node-agent/.venv/bin/pytest vpn-node-agent/tests -q
vpn-node-agent/.venv/bin/python -m pip wheel vpn-node-agent --no-deps --wheel-dir vpn-node-agent/dist
```

On Windows, use `.venv\Scripts\python.exe` and the corresponding `.exe` commands.

## Provision mTLS credentials

Use an offline/internal PKI; do not commit its CA key, server key, client key, bearer token, certificates, or Ansible vault password. The node needs:

```text
/etc/prettylisavpn-agent/tls/server.crt     server certificate/chain for 204.48.17.50
/etc/prettylisavpn-agent/tls/server.key     matching server private key
/etc/prettylisavpn-agent/tls/client-ca.crt  CA allowed to issue Backend client certificates
```

The Backend host needs its client certificate/key and the CA that issued `server.crt`. Certificates must have appropriate `serverAuth`/IP SAN and `clientAuth` extended key usage. Generate private keys with `umask 077`, use at least RSA-3072 or an organizationally approved modern elliptic curve, keep the CA offline, and establish rotation/expiry monitoring before production sessions.

Generate the bearer token on a trusted administration machine without printing it into shell history, save it in an encrypted `node-agent.vault.yml`, and give the same value to the Backend through its secret manager. The example file documents variable names only:

```bash
cp infra/ansible/inventories/production/node-agent.vault.example.yml infra/ansible/inventories/production/node-agent.vault.yml
ansible-vault encrypt infra/ansible/inventories/production/node-agent.vault.yml
```

## Deploy

Pre-provision the three mTLS files, add the Cloud Firewall rule, build the wheel, and keep a working SSH session open. From `infra/ansible`:

```bash
ansible-playbook playbooks/vpn-node-agent.yml \
  --private-key ../../keys/github-actions-development \
  --ask-vault-pass \
  --extra-vars @inventories/production/node-agent.vault.yml \
  --extra-vars "vpn_node_agent_wheel_local_path=../../vpn-node-agent/dist/prettylisavpn_node_agent-0.1.0-py3-none-any.whl" \
  --check --diff

ansible-playbook playbooks/vpn-node-agent.yml \
  --private-key ../../keys/github-actions-development \
  --ask-vault-pass \
  --extra-vars @inventories/production/node-agent.vault.yml \
  --extra-vars "vpn_node_agent_wheel_local_path=../../vpn-node-agent/dist/prettylisavpn_node_agent-0.1.0-py3-none-any.whl"
```

## Verify

On the node:

```bash
sudo systemctl is-enabled prettylisavpn-node-agent
sudo systemctl is-active prettylisavpn-node-agent
sudo systemctl show prettylisavpn-node-agent -p User -p AmbientCapabilities -p CapabilityBoundingSet -p NoNewPrivileges
sudo ss -lntp 'sport = :8443'
sudo ufw status verbose
sudo wg show wg0 peers
sudo journalctl -u prettylisavpn-node-agent -n 50 --no-pager
```

Expected: enabled/active; user `prettylisa-agent`; only `cap_net_admin`; listener `204.48.17.50:8443`; UFW source restricted to the Backend `/32`; no peers. Logs must contain no tokens, request URLs, peer keys, VPN IPs, or traffic data.

From the Backend host, with credentials supplied from its secret manager rather than shell history or process arguments, create a root-only curl header file containing `Authorization: Bearer ...`, then run:

```bash
curl --fail --silent --show-error \
  --cacert /secure/node-server-ca.crt \
  --cert /secure/backend-client.crt \
  --key /secure/backend-client.key \
  --header @/secure/node-agent-auth-header \
  https://204.48.17.50:8443/v1/health
```

Requests without a client certificate fail during TLS negotiation. Requests with mTLS but without the bearer credential return HTTP 401. Do not place credentials in URLs.

## Rollback

From SSH or Recovery Console, preserving WireGuard and SSH:

```bash
sudo systemctl disable --now prettylisavpn-node-agent
sudo ufw status numbered
sudo ufw delete allow in on eth0 proto tcp from BACKEND_PUBLIC_IPV4/32 to 204.48.17.50 port 8443
sudo rm -f /etc/systemd/system/prettylisavpn-node-agent.service
sudo systemctl daemon-reload
```

Retain `/etc/prettylisavpn-agent` initially for recoverability. After revoking the server certificate, Backend client certificate, and bearer token, remove agent configuration and software with an explicit operator decision. No rollback step changes UDP/51820, `wg0`, NAT, forwarding, or TCP/22.
