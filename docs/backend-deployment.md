# PrettyLisaVPN backend deployment on Ubuntu LTS

This guide deploys the backend and Caddy on one Ubuntu LTS VPS. PostgreSQL and
Valkey remain managed external services. Caddy is the only public container: it
listens on ports 80 and 443, obtains and renews the TLS certificate, and proxies
requests to FastAPI over a private Docker network.

The procedure does not create or change DNS records. Create the DNS records in
your DNS provider before running the deployment script.

## Prerequisites

Prepare these values before connecting to the server:

- a public Ubuntu LTS VPS with a static public IP address;
- a domain such as `api.example.com`;
- an `A` record for the domain pointing to the VPS IPv4 address and, if used, an
  `AAAA` record pointing to its IPv6 address;
- a managed PostgreSQL endpoint reachable from the VPS;
- a managed Valkey endpoint reachable from the VPS;
- an immutable backend image reference, preferably a registry digest such as
  `registry.example.com/prettylisavpn/backend@sha256:...`;
- an email address for ACME certificate notices.

Allow inbound TCP 22 from trusted administration addresses and TCP 80 and 443
from the internet. Allow inbound UDP 443 if HTTP/3 is desired. The backend port
8000 must not be opened in the VPS firewall or cloud firewall. Configure the
managed PostgreSQL and Valkey firewalls to accept their service ports from the
VPS private IP when private networking is available, or from its static public
IP otherwise.

Verify DNS manually before deployment:

```bash
getent ahosts api.example.com
```

The returned addresses must include the VPS address. Caddy's automatic HTTPS
also requires the public DNS record and inbound access to ports 80 and 443.

## Bootstrap a clean Ubuntu VPS

Connect with the administrative SSH user created by the VPS provider:

```bash
ssh ubuntu@VPS_IP_ADDRESS
```

Update the host and install the basic tools:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y ca-certificates curl git
```

Install Docker Engine and the Docker Compose plugin from Docker's official APT
repository:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc" | \
  sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker run --rm hello-world
sudo docker compose version
```

These commands follow Docker's official Ubuntu installation instructions. Keep
Docker Engine and the host security updates current through normal maintenance.

If UFW is used, allow SSH before enabling it:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

Docker-published ports can bypass some UFW forwarding rules. The Compose file
publishes only Caddy's 80/443 ports; it never publishes FastAPI port 8000.

## Deployment layout

Use this layout on the VPS:

```text
/opt/prettylisavpn/repository/       checked-out application release
  infra/deployment/
    Caddyfile
    compose.yaml
    deploy.sh
/etc/prettylisavpn/deployment.env    root-readable deployment secrets
Docker named volume caddy_data       TLS certificates and Caddy state
Docker named volume caddy_config     Caddy runtime configuration state
```

The backend container has a read-only filesystem and no application data
volume. Persistent business data belongs in managed PostgreSQL; ephemeral
service data belongs in managed Valkey. Caddy certificate state is retained in
named Docker volumes when containers are replaced.

Create the directories and check out an exact release tag or commit:

```bash
sudo install -d -o "$USER" -g "$USER" /opt/prettylisavpn
git clone REPOSITORY_URL /opt/prettylisavpn/repository
git -C /opt/prettylisavpn/repository checkout --detach RELEASE_TAG_OR_COMMIT
sudo install -d -m 0700 /etc/prettylisavpn
```

For a private container registry, authenticate without putting a token on the
command line or in the repository:

```bash
printf '%s' "$REGISTRY_ACCESS_TOKEN" | \
  sudo docker login registry.example.com --username REGISTRY_USER --password-stdin
unset REGISTRY_ACCESS_TOKEN
```

## Configure the deployment

Copy the safe template to the host-only secrets directory:

```bash
sudo install -m 0600 \
  /opt/prettylisavpn/repository/infra/deployment/.env.example \
  /etc/prettylisavpn/deployment.env
sudoedit /etc/prettylisavpn/deployment.env
```

Replace every placeholder. Do not copy this populated file into the repository.
The backend expects these environment variables:

| Variable | Required | Purpose |
| --- | --- | --- |
| `APPLICATION_NAME` | No | Name returned by `/version`; defaults to `PrettyLisaVPN`. |
| `APPLICATION_VERSION` | Yes | Deployed release version returned by `/version`. |
| `ENVIRONMENT` | No | Environment name; use `production`. |
| `LOG_LEVEL` | No | Structured application log level, for example `INFO`. |
| `POSTGRES_URL` | Yes | SQLAlchemy async URL beginning with `postgresql+asyncpg://`. |
| `VALKEY_URL` | Yes | Valkey URL beginning with `redis://` or `rediss://`. |
| `DEPENDENCY_TIMEOUT_SECONDS` | No | Timeout used by `/ready`; defaults to `2`. |
| `POSTGRES_POOL_SIZE` | No | SQLAlchemy connection pool size; defaults to `5`. |
| `POSTGRES_MAX_OVERFLOW` | No | Additional transient PostgreSQL connections; defaults to `5`. |

The deployment layer also requires `API_DOMAIN`, `ACME_EMAIL`, and
`BACKEND_IMAGE`. `HTTP_BIND_ADDRESS`, `HTTPS_BIND_ADDRESS`, `HTTP_PORT`, and
`HTTPS_PORT` normally retain their template values.

Use provider-issued TLS settings in the URLs when the managed services require
them. Percent-encode reserved characters in usernames and passwords. Example
shapes only:

```dotenv
POSTGRES_URL=postgresql+asyncpg://APP_USER:URL_ENCODED_PASSWORD@POSTGRES_HOST:5432/APP_DATABASE?ssl=require
VALKEY_URL=rediss://:URL_ENCODED_PASSWORD@VALKEY_HOST:6379/0
```

Store the PostgreSQL password, Valkey password, registry token, and populated
connection URLs as secrets. Never commit them. Confirm the final permissions:

```bash
sudo chown root:root /etc/prettylisavpn/deployment.env
sudo chmod 600 /etc/prettylisavpn/deployment.env
sudo stat -c '%a %U:%G %n' /etc/prettylisavpn/deployment.env
```

## Deploy and verify

Run the deployment script as root because the environment file is root-only:

```bash
cd /opt/prettylisavpn/repository
sudo ./infra/deployment/deploy.sh /etc/prettylisavpn/deployment.env
```

The script validates the rendered Compose configuration, checks that the domain
resolves, pulls the configured image, replaces the containers, waits for the
FastAPI liveness check, and verifies `https://API_DOMAIN/health`. It never makes
DNS changes.

Check liveness through Caddy:

```bash
curl --fail --show-error https://api.example.com/health
```

Check both external dependencies through the readiness endpoint:

```bash
curl --fail --show-error https://api.example.com/ready
```

`/health` proves that the application process is alive. `/ready` returns a
non-success status if managed PostgreSQL or Valkey cannot be reached. If it
fails, inspect container logs and the managed-service network allowlists, DNS,
TLS mode, credentials, and connection URLs.

View logs without printing the environment file:

```bash
sudo docker compose --project-name prettylisavpn \
  --env-file /etc/prettylisavpn/deployment.env \
  --file /opt/prettylisavpn/repository/infra/deployment/compose.yaml \
  logs --follow --tail 200 backend caddy
```

Restart the deployment:

```bash
sudo docker compose --project-name prettylisavpn \
  --env-file /etc/prettylisavpn/deployment.env \
  --file /opt/prettylisavpn/repository/infra/deployment/compose.yaml \
  restart
```

Both services use `restart: unless-stopped`, and Docker is enabled at boot, so
they start again after a VPS reboot. Verify this once during provisioning by
rebooting in a maintenance window and repeating both curl checks.

## Update and rollback

Before an update, record the working Git revision and backend image and save a
root-only copy of the environment file:

```bash
git -C /opt/prettylisavpn/repository rev-parse HEAD
sudo grep '^BACKEND_IMAGE=' /etc/prettylisavpn/deployment.env
sudo cp --preserve=mode,ownership \
  /etc/prettylisavpn/deployment.env \
  /etc/prettylisavpn/deployment.env.rollback
```

Fetch and check out the new immutable release, update `BACKEND_IMAGE` and
`APPLICATION_VERSION`, then run `deploy.sh` again. Avoid mutable tags such as
`latest`; an image digest gives an exact rollback target.

To roll back the application image, restore the previous `BACKEND_IMAGE` and
`APPLICATION_VERSION` in `/etc/prettylisavpn/deployment.env`, then rerun the
deploy script. To roll back deployment configuration as well, check out the
previous known-good tag or commit first:

```bash
git -C /opt/prettylisavpn/repository checkout --detach KNOWN_GOOD_TAG_OR_COMMIT
sudo /opt/prettylisavpn/repository/infra/deployment/deploy.sh \
  /etc/prettylisavpn/deployment.env
```

The named Caddy volumes survive application and configuration rollback. Do not
delete them during routine deployment. If a future release adds database
migrations, review that release's migration compatibility before rolling the
application image back; this initial backend skeleton has no schema migrations.

Official references: [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/),
[Docker Compose plugin](https://docs.docker.com/compose/install/linux/), and
[Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
