# Timeweb Cloud development environment

This runbook describes the manual Timeweb Cloud setup for the PrettyLisaVPN
development environment. It does not create or change any cloud resources. Complete
every action in the Timeweb Cloud control panel and record the resulting values in an
approved secret store.

The guidance was checked against the Timeweb Cloud documentation on 5 September 2026.
Timeweb currently supports PostgreSQL 14–18 and Valkey 7, 8.1, and 9.1. The provider
shows the authoritative connection host, port, username, database name, and any TLS
requirements on each database cluster's **Dashboard** and **Connection** tabs. Always
use those displayed values rather than assuming an endpoint.

## Target layout

Create all three resources in the same Timeweb Cloud project, region, and private BGP
network.

```text
Administrator workstation
        |
        | TCP 22 from ADMIN_PUBLIC_CIDR only
        v
Ubuntu LTS backend VPS (public IP + private IP)
        |                         |
        | private PostgreSQL      | private Valkey protocol
        | endpoint                | endpoint
        v                         v
Managed PostgreSQL          Managed Valkey
(private IP only)           (private IP only)
```

The backend API listens on port 8000 inside its container. Do not expose port 8000 to
the internet. Bind it to `127.0.0.1` on the VPS and place a TLS reverse proxy in front
of it when remote API access is needed. The VPN data plane is outside the scope of this
environment; no user VPN traffic should pass through this backend VPS.

## Recommended MVP sizes

These sizes are a development starting point, not a production capacity guarantee.
Review CPU, memory, disk, connections, and latency after realistic load tests.

| Resource | Recommended development size | Purpose and rationale |
| --- | --- | --- |
| Ubuntu VPS | Ubuntu 24.04 LTS, 2 vCPU, 4 GB RAM, 30 GB Premium NVMe, one instance | Runs Docker, the backend container, and optionally a small reverse proxy. It does not carry VPN user traffic. |
| PostgreSQL | PostgreSQL 17, Premium NVMe, 1 CPU, 2 GB RAM, 20 GB disk, one node, physical backups enabled | Persistent source of truth. This is deliberately above Timeweb's documented 1 CPU / 1 GB / 8 GB minimum, whose database/user and parameter-management capabilities are restricted. Replicas are unnecessary for a disposable development environment. |
| Valkey | Valkey 8.1, 1 CPU, 1 GB RAM, smallest disk offered in the selected region, one node | Stores ephemeral cache, locks, rate limits, OTP state, and short-lived sessions. It is not a source of truth. Keep the provider defaults initially and resize only with evidence. |

Timeweb documents that a database cluster can be increased later but cannot be reduced,
and that changing the selected database engine or version is not supported. Confirm the
current configuration and price in the panel before ordering.

## Values to prepare and record

Use placeholders while following this document. Do not put real secrets in this file,
Git, tickets, chat, terminal history, screenshots, or deployment logs.

| Placeholder | Where it comes from | Secret? |
| --- | --- | --- |
| `TIMEWEB_PROJECT` | Existing or newly selected Timeweb project | No |
| `TIMEWEB_REGION` | One region selected for all resources | No |
| `PRIVATE_NETWORK_NAME` / `PRIVATE_CIDR` | Private BGP network created in the panel | No |
| `VPS_PUBLIC_IP` | VPS Dashboard | No |
| `VPS_PRIVATE_IP` | Private-network assignment | No |
| `SSH_USER` | VPS Dashboard or the selected Ubuntu image/cloud-init configuration | No |
| `LOCAL_PRIVATE_KEY_PATH` | Path on the administrator workstation | **Yes; keep only on the workstation or an approved key store** |
| `POSTGRES_PRIVATE_HOST`, `POSTGRES_PORT`, `POSTGRES_DATABASE`, `POSTGRES_USER` | PostgreSQL Dashboard/Connection tab | No by themselves |
| `POSTGRES_PASSWORD` | Generated or entered during PostgreSQL creation | **Yes** |
| `VALKEY_PRIVATE_HOST`, `VALKEY_PORT`, `VALKEY_USER` | Valkey Dashboard/Connection tab | No by themselves |
| `VALKEY_PASSWORD` | Generated or entered during Valkey creation | **Yes** |
| `POSTGRES_URL` | Constructed from the PostgreSQL connection details | **Yes; contains the password** |
| `VALKEY_URL` | Constructed from the Valkey connection details | **Yes; contains the password** |

The public half of the SSH key is safe to upload to Timeweb. Never upload, email, or
copy the private half to the VPS. A Timeweb API token is not needed for this manual
procedure. If one is created later for automation, treat it as a secret too.

## 1. Create the project and private network

1. Sign in to the Timeweb Cloud control panel.
2. Select or create the project identified as `TIMEWEB_PROJECT`.
3. Open **Networks → Private networks** and create a BGP private network.
4. Select `TIMEWEB_REGION`, enter `PRIVATE_NETWORK_NAME`, and choose `PRIVATE_CIDR`.
5. Record the final network name, region, and CIDR. Timeweb reserves addresses whose
   last octet is 1, 2, or 3; do not assign those manually to services.
6. Use this same network when creating the VPS and both managed database clusters.

Timeweb allows a server and managed database to be attached when the resource is
created or later from the private-network page. When a cloud server is attached to a
BGP network, follow the IP configuration shown by Timeweb and verify that the private
address is configured inside Ubuntu; attaching it in the panel alone may not configure
the guest interface.

## 2. Create the Ubuntu backend VPS

1. Open **Cloud servers** and choose **Create**.
2. Select the regular OS image for **Ubuntu 24.04 LTS**. Do not select a marketplace
   application image.
3. Select `TIMEWEB_REGION`, Premium NVMe, 2 vCPU, 4 GB RAM, and a 30 GB disk.
4. Assign one public IPv4 address. It is needed for SSH and, if required later, the
   HTTPS development API.
5. Attach `PRIVATE_NETWORK_NAME` and assign/record `VPS_PRIVATE_IP` according to the
   panel's network instructions.
6. Under **Authorization**, select or upload the administrator's public SSH key. Prefer
   key authentication over a password.
7. Place the server in `TIMEWEB_PROJECT`, give it a clear development name, review the
   monthly cost, and order it.
8. On the server Dashboard, record `VPS_PUBLIC_IP` and the exact `SSH_USER`. Timeweb's
   generated SSH command is authoritative for the selected image.

### VPS firewall rules

Create a Timeweb Firewall group and attach it to the VPS. Use the narrowest source
ranges available.

| Direction | Protocol/port | Source or destination | Required for |
| --- | --- | --- | --- |
| Inbound | TCP 22 | `ADMIN_PUBLIC_CIDR` only | SSH administration |
| Inbound | TCP 443 | `0.0.0.0/0` and, only if configured, `::/0` | HTTPS API access; omit until a reverse proxy and TLS certificate exist |
| Inbound | TCP 80 | `0.0.0.0/0` and, only if configured, `::/0` | Optional HTTP-to-HTTPS redirect or ACME HTTP challenge |
| Inbound | TCP 8000 | None | Must remain private/loopback; never publish it directly |
| Outbound | TCP 443 | Internet | Ubuntu packages, container registry, and required external APIs |
| Outbound | UDP/TCP 53 | Configured DNS resolvers | DNS resolution |
| Outbound | UDP 123 | Configured NTP service | UTC clock synchronization |
| Outbound | TCP `POSTGRES_PORT` | `POSTGRES_PRIVATE_HOST` | PostgreSQL connectivity over the private network |
| Outbound | TCP `VALKEY_PORT` | `VALKEY_PRIVATE_HOST` | Valkey connectivity over the private network |

Do not add public inbound rules for PostgreSQL or Valkey. If an allow-list firewall is
also attached to a managed database, allow its protocol port only from
`VPS_PRIVATE_IP/32`. Timeweb firewall behavior depends on whether the attached group is
an allow or deny group; review the rendered rules in the panel before applying them.

### Test SSH access

From the administrator workstation, use the exact username and IP shown by Timeweb:

```sh
ssh -i LOCAL_PRIVATE_KEY_PATH SSH_USER@VPS_PUBLIC_IP
```

The first connection should display the host-key fingerprint. Compare it with a trusted
value from the Timeweb console or another trusted channel before accepting it. After
login, run:

```sh
id
hostnamectl
ip address
ip route
```

Confirm the expected user, Ubuntu release, `VPS_PRIVATE_IP`, and route for
`PRIVATE_CIDR`. If SSH fails, use the Timeweb serial/VNC console to inspect networking
and `sshd`; do not open SSH to all sources as a permanent workaround.

### Prepare the VPS for the backend container

Install security updates, Git, Docker Engine, Compose, and the connectivity clients from
the Ubuntu repositories:

```sh
sudo apt-get update
sudo apt-get upgrade --yes
sudo apt-get install --yes ca-certificates curl git docker.io docker-compose-v2 postgresql-client redis-tools netcat-openbsd
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

Keep Docker administration behind `sudo`. Membership in the `docker` group is effectively
root-level access and is unnecessary for this setup. Enable automatic installation of
Ubuntu security updates according to the team's server-management policy, and record who
owns OS patching for this development VPS.

## 3. Create managed PostgreSQL

1. Open **Databases**, click **Add**, and select **PostgreSQL 17**.
2. Select `TIMEWEB_REGION`, Premium NVMe, 1 CPU, 2 GB RAM, and 20 GB disk.
3. Select a single-node cluster without replicas for development.
4. Attach `PRIVATE_NETWORK_NAME`; do not assign a public IPv4 or IPv6 address.
5. Enable physical backups. Choose a maintenance window that does not overlap planned
   development demonstrations. Disk autoscaling is optional for development; if enabled,
   set a budget alert and record its threshold because a scale-up cannot be reversed.
6. Use a generated password or enter a unique strong password in the panel. Do not use
   any placeholder from this document as a password.
7. Select the required database name and user, place the cluster in `TIMEWEB_PROJECT`,
   review the price, and order it.
8. Open the cluster's **Dashboard** or **Connection** tab and record the private host,
   actual port, database, username, TLS mode, and password in the approved secret store.
   Copy the provider-generated connection command for comparison during testing.

### Test PostgreSQL connectivity

Connect to the VPS over SSH, then install only the client tools:

```sh
sudo apt-get update
sudo apt-get install --yes postgresql-client netcat-openbsd
```

First test the private TCP route without disclosing credentials:

```sh
nc -vz POSTGRES_PRIVATE_HOST POSTGRES_PORT
```

Then test authentication. The `-W` option prompts for the password without placing it
in shell history:

```sh
psql -h POSTGRES_PRIVATE_HOST -p POSTGRES_PORT -U POSTGRES_USER -d POSTGRES_DATABASE -W -c 'SELECT 1;'
```

If Timeweb's Connection tab requires TLS or additional parameters, use its generated
command and preserve those settings. Success returns one row containing `1`. A TCP
failure points to the BGP attachment, guest private-IP configuration, route, or firewall;
an authentication failure points to the selected database/user/password.

## 4. Create managed Valkey

1. Open **Databases**, click **Add**, and select **Valkey 8.1**.
2. Select `TIMEWEB_REGION`, 1 CPU, 1 GB RAM, the smallest disk offered, and a single
   node for development.
3. Attach `PRIVATE_NETWORK_NAME`; do not assign a public IPv4 or IPv6 address.
4. Keep the provider database parameters at their defaults initially. PrettyLisaVPN
   uses Valkey only for ephemeral data, so PostgreSQL remains the source of truth.
5. Use a generated password or enter a unique strong password in the panel. Do not reuse
   the PostgreSQL password.
6. Place the cluster in `TIMEWEB_PROJECT`, review the price, and order it.
7. On **Dashboard** or **Connection**, record the private host, actual port, username,
   TLS mode, and password in the approved secret store. Timeweb creates a `default` user,
   but use the username actually shown by the cluster. Grant only the privileges needed
   by the backend as those operations are implemented.

### Test Valkey connectivity

On the VPS, install the Redis-compatible client documented by Timeweb:

```sh
sudo apt-get update
sudo apt-get install --yes redis-tools netcat-openbsd
redis-cli --version
```

Test the network route first:

```sh
nc -vz VALKEY_PRIVATE_HOST VALKEY_PORT
```

For a non-TLS private endpoint, prompt for the password:

```sh
redis-cli -h VALKEY_PRIVATE_HOST -p VALKEY_PORT --user VALKEY_USER --askpass PING
```

For an endpoint that the Timeweb Connection tab marks as TLS, add `--tls`:

```sh
redis-cli --tls -h VALKEY_PRIVATE_HOST -p VALKEY_PORT --user VALKEY_USER --askpass PING
```

Use exactly one of these forms, matching the provider-generated command. Success returns
`PONG`. Do not use `-a PASSWORD`, because that puts a real password in shell history and
may expose it in a process listing.

## Backend environment variables

The table below is derived from `backend/src/prettylisavpn/config.py` and is the actual
application contract. Environment variable names are uppercase. Pydantic also reads a
`.env` file from the current working directory, but deployment secrets should come from
an access-controlled deployment env file or secret manager.

| Variable | Required for this deployment | Default in application | Validation/meaning |
| --- | --- | --- | --- |
| `APPLICATION_NAME` | No | `PrettyLisaVPN` | Non-empty service name returned by `/version` |
| `APPLICATION_VERSION` | Yes | `0.1.0` | Non-empty release identifier returned by `/version`; set it to the deployed build |
| `ENVIRONMENT` | Yes | `development` | Set to `development` for this environment |
| `LOG_LEVEL` | No | `INFO` | One of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `POSTGRES_URL` | **Yes, secret** | Local-only fallback | Must start with `postgresql+asyncpg://` and identify the managed PostgreSQL endpoint |
| `VALKEY_URL` | **Yes, secret** | Local-only fallback | Must start with `redis://` or `rediss://` and identify the managed Valkey endpoint |
| `DEPENDENCY_TIMEOUT_SECONDS` | No | `2` | More than 0 and no more than 30 seconds |
| `POSTGRES_POOL_SIZE` | No | `5` | Integer of at least 1 |
| `POSTGRES_MAX_OVERFLOW` | No | `5` | Integer of at least 0 |

The backend does **not** currently read separate variables such as `POSTGRES_HOST`,
`POSTGRES_PASSWORD`, `VALKEY_HOST`, or `VALKEY_PASSWORD`. Combine the panel values into
the two URL variables. Percent-encode reserved characters in usernames and passwords.
Replace every brace-delimited field below locally; these are placeholders, not credentials:

```dotenv
APPLICATION_NAME=PrettyLisaVPN
APPLICATION_VERSION={DEPLOYED_APPLICATION_VERSION}
ENVIRONMENT=development
LOG_LEVEL=INFO
POSTGRES_URL=postgresql+asyncpg://{POSTGRES_USER}:{URL_ENCODED_POSTGRES_PASSWORD}@{POSTGRES_PRIVATE_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}
VALKEY_URL=redis://{VALKEY_USER}:{URL_ENCODED_VALKEY_PASSWORD}@{VALKEY_PRIVATE_HOST}:{VALKEY_PORT}/0
DEPENDENCY_TIMEOUT_SECONDS=2
POSTGRES_POOL_SIZE=5
POSTGRES_MAX_OVERFLOW=5
```

If Timeweb requires TLS for Valkey, use `rediss://`. Preserve any PostgreSQL TLS/query
parameters required by the provider's connection details when converting its URI to the
required `postgresql+asyncpg://` scheme. Validate both URLs from the VPS before starting
the backend.

The production Compose wrapper additionally requires `BACKEND_IMAGE` and accepts
`BACKEND_PORT`; those configure Compose, not the FastAPI settings object.

### Store deployment secrets on the VPS

Use an approved secrets manager when available. For a small development deployment, an
access-controlled root-owned env file is acceptable:

```sh
sudo install -d -m 0750 -o root -g root /etc/prettylisavpn
sudo install -m 0600 -o root -g root /dev/null /etc/prettylisavpn/backend.env
sudoedit /etc/prettylisavpn/backend.env
```

Enter the real deployment values in that file, never in the repository. Verify metadata
without printing its contents:

```sh
sudo stat -c '%U %G %a %n' /etc/prettylisavpn/backend.env
```

Expected ownership/mode is `root root 600`. Do not run `cat`, `env`, Compose `config`, or
debug logging in a way that prints the URLs. Pass the file to the standalone production
Compose configuration with `--env-file /etc/prettylisavpn/backend.env`.

### Build and run the development backend

Choose an immutable commit or release tag as `RELEASE_REF`. Replace the uppercase tokens
below locally; none of them are credentials. If the repository is private, use the
organization's approved short-lived Git authentication and do not persist a token on the
VPS.

```sh
sudo install -d -m 0755 /opt/prettylisavpn
sudo chown "$USER":"$USER" /opt/prettylisavpn
git clone REPOSITORY_URL /opt/prettylisavpn/source
git -C /opt/prettylisavpn/source checkout --detach RELEASE_REF
sudo docker build --pull --tag prettylisavpn-backend:DEPLOYED_APPLICATION_VERSION /opt/prettylisavpn/source/backend
```

Put only the backend variables from the previous section in
`/etc/prettylisavpn/backend.env`. In particular, set `ENVIRONMENT=development` and make
`APPLICATION_VERSION` match the image tag. Start the container with the same hardening
used by the repository's deployment configuration:

```sh
sudo docker run --detach --name prettylisa-backend --restart unless-stopped --init --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges:true --stop-timeout 30 --publish 127.0.0.1:8000:8000 --env-file /etc/prettylisavpn/backend.env prettylisavpn-backend:DEPLOYED_APPLICATION_VERSION
sudo docker inspect --format '{{.State.Status}} {{.State.Health.Status}}' prettylisa-backend
```

The repository's `infra/docker/compose.production.yaml` is also suitable when
`ENVIRONMENT=production`; it intentionally identifies that deployment as production.
For this development environment, the explicit `docker run` command above preserves the
correct `/version` metadata.

For an update, build a new immutable tag, stop the old container gracefully, remove only
that stopped container, and start the replacement with the same runtime arguments:

```sh
sudo docker stop --time 30 prettylisa-backend
sudo docker rm prettylisa-backend
```

Do not reuse a mutable image tag for a different commit. Retain the previous image tag
until the new container has passed `/health`, `/version`, and `/ready`, so rollback remains
possible.

After deployment, verify the process and both managed dependencies locally on the VPS:

```sh
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/version
curl --fail --silent --show-error http://127.0.0.1:8000/ready
```

`/health` must return HTTP 200 even during a database outage. `/ready` returns HTTP 200
only when both PostgreSQL and Valkey checks succeed; it returns HTTP 503 otherwise.

## Manual setup checklist

- [ ] Select `TIMEWEB_PROJECT` and one `TIMEWEB_REGION` for all resources.
- [ ] Create `PRIVATE_NETWORK_NAME` as a private BGP network and record `PRIVATE_CIDR`.
- [ ] Create the Ubuntu 24.04 LTS VPS with 2 vCPU, 4 GB RAM, and 30 GB Premium NVMe.
- [ ] Attach the VPS to the private network and verify `VPS_PRIVATE_IP` inside Ubuntu.
- [ ] Upload only the public SSH key; keep the private key in the approved local store.
- [ ] Attach a VPS firewall allowing SSH only from `ADMIN_PUBLIC_CIDR`.
- [ ] Leave TCP 8000 closed publicly; add 80/443 only when the TLS reverse proxy exists.
- [ ] Verify SSH access and the server host-key fingerprint.
- [ ] Install OS updates, Docker, Compose, Git, and connectivity clients on the VPS.
- [ ] Confirm Docker Engine is active and record who owns OS security patching.
- [ ] Create single-node managed PostgreSQL 17 with 1 CPU, 2 GB RAM, and 20 GB disk.
- [ ] Attach PostgreSQL to the private network and leave public IPv4/IPv6 disabled.
- [ ] Enable PostgreSQL physical backups and record the maintenance window.
- [ ] Store the PostgreSQL private endpoint, database, user, TLS mode, and password securely.
- [ ] From the VPS, verify the PostgreSQL TCP route and run `SELECT 1` with `psql -W`.
- [ ] Create single-node managed Valkey 8.1 with 1 CPU and 1 GB RAM.
- [ ] Attach Valkey to the private network and leave public IPv4/IPv6 disabled.
- [ ] Store the Valkey private endpoint, user, TLS mode, and password securely.
- [ ] From the VPS, verify the Valkey TCP route and receive `PONG` from `redis-cli`.
- [ ] Construct and securely store `POSTGRES_URL` and `VALKEY_URL` with encoded credentials.
- [ ] Create `/etc/prettylisavpn/backend.env` as `root:root` mode `0600`.
- [ ] Set all required backend variables, including the deployed application version.
- [ ] Check out an immutable `RELEASE_REF` and build a uniquely tagged backend image.
- [ ] Deploy the backend container with port 8000 bound only to VPS loopback.
- [ ] Confirm `/health` and `/version` return HTTP 200.
- [ ] Confirm `/ready` returns HTTP 200 and reports PostgreSQL and Valkey as ready.
- [ ] Confirm no real credential was committed, pasted into a ticket/chat, or left in shell history.
- [ ] Record resource owners, purpose, region, monthly budget, and deletion date for the environment.

## Official references

- [Create a Timeweb Cloud server](https://timeweb.cloud/docs/cloud-servers/manage-servers/create-server)
- [Manage SSH keys](https://timeweb.cloud/docs/cloud-servers/manage-servers/ssh-keys)
- [Timeweb Cloud Firewall](https://timeweb.cloud/docs/firewall)
- [Create a private BGP network](https://timeweb.cloud/docs/vpc/managing-bgp-networks/creating-bgp-networks)
- [Add services to a private BGP network](https://timeweb.cloud/docs/vpc/managing-bgp-networks/adding-services-to-bgp)
- [Create a managed database cluster](https://timeweb.cloud/docs/dbaas/dbaas-create)
- [Connect to a managed database](https://timeweb.cloud/docs/dbaas/dbaas-manage/connect-to-database)
- [Connect to managed Valkey](https://timeweb.cloud/docs/dbaas/valkey/connect-to-database)
- [Valkey users and privileges](https://timeweb.cloud/docs/dbaas/valkey/users-and-privileges)
- [Manage public access to a database](https://timeweb.cloud/docs/dbaas/dbaas-manage/public-ip-access)
