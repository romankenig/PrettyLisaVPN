<p align="center">
  <img src="docs/assets/prettylisavpn-logo.svg" alt="PrettyLisaVPN logo" width="320">
</p>

# PrettyLisaVPN

PrettyLisaVPN is a multi-platform commercial VPN service. This repository is a monorepo for the client applications, Backend control plane, infrastructure, and product documentation.

## Repository Layout

```text
apps/
  desktop/          Desktop client shared by Windows, macOS, and Linux
  android/          Android mobile client
  ios/              iOS client
  android-tv/       Android TV client
  chrome-extension/ Browser-only, proxy-based Chrome Extension
backend/             Python 3.13 and FastAPI modular monolith
infra/
  terraform/        Infrastructure provisioning
  ansible/          Host configuration and deployment automation
  docker/           Local-development and deployment packaging
  monitoring/       Metrics, logs, dashboards, and alerting configuration
  environments/     Environment-specific infrastructure configuration
docs/                Product, architecture, operations, and security documentation
```

## Architecture Principles

- The Backend begins as a modular monolith.
- PostgreSQL is the source of truth for persistent business data; Redis holds ephemeral data.
- WireGuard is the primary system-wide VPN protocol.
- The VPN control plane and data plane remain separate. User VPN traffic never passes through the Backend API.
- The Chrome Extension uses a browser proxy rather than a system-wide WireGuard tunnel.
- External services are integrated through replaceable provider interfaces.
- User browsing history, destinations, DNS queries, URLs, and packet contents must not be collected or logged.

See [AGENTS.md](AGENTS.md) for the complete product, architecture, security, and engineering rules.

## Development Status

The backend skeleton provides liveness, dependency readiness, and version endpoints.
See [backend setup and verification](backend/README.md) for local Python and Docker workflows.

Start the Docker development stack from this directory:

```sh
docker compose -f infra/docker/compose.yaml up --build -d --wait
```

The [backend Docker guide](backend/README.md#build-and-run-the-image) includes standalone
`docker build` / `docker run` commands and a production Compose deployment using external
PostgreSQL and Valkey services.
