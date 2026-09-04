# Backend

Python 3.13 FastAPI modular-monolith skeleton. No business modules or database tables
exist yet, so no Alembic migration is needed at this stage. Add Alembic with the first
schema change. PostgreSQL uses SQLAlchemy 2.x and asyncpg; Valkey uses the Redis-compatible
redis-py async client. Connection pools belong to the application lifespan and connect
lazily. `Postgres.session()` closes sessions and rolls back uncommitted work; callers
must explicitly commit successful writes.

## Docker development

From the repository root, with Docker and Compose installed:

```sh
docker compose -f infra/docker/compose.yaml up --build -d --wait
docker compose -f infra/docker/compose.yaml ps
docker compose -f infra/docker/compose.yaml logs -f backend
docker compose -f infra/docker/compose.yaml down
```

This runs the backend, PostgreSQL, and Valkey. Only loopback ports are published:
8000, 5432, and 6379. PostgreSQL data persists in a named volume. The credentials
in this development file are public, local-only examples. Rebuild with `up --build`
after source changes; the runtime image does not enable auto-reload.

If a host port is occupied, set `POSTGRES_PORT`, `VALKEY_PORT`, or `BACKEND_PORT`
before running Compose. For example, on this Windows workstation:

```powershell
$env:POSTGRES_PORT = "5433"
docker compose -f infra/docker/compose.yaml up --build -d --wait
```

These variables change host ports only; containers still use their standard internal
ports. A host-side Python process should use `127.0.0.1` and the selected host ports
in its `.env`. The earlier local `.tools/compose.local.yaml` override remains compatible.

## Build and run the image

From the repository root:

```sh
docker build -t prettylisavpn-backend:0.1.0 backend
```

Supply `POSTGRES_URL` and `VALKEY_URL` through your shell or deployment secret manager
before running the following command (one line works in PowerShell and POSIX shells):

```sh
docker run -d --name prettylisa-backend --init --read-only --tmpfs /tmp:rw,noexec,nosuid,size=16m --cap-drop ALL --security-opt no-new-privileges:true --stop-timeout 30 -p 127.0.0.1:8000:8000 -e ENVIRONMENT=production -e APPLICATION_VERSION=0.1.0 -e POSTGRES_URL -e VALKEY_URL prettylisavpn-backend:0.1.0
docker stop --time 30 prettylisa-backend
docker rm prettylisa-backend
```

The URLs must be reachable **from the container**. `localhost` inside a container refers
to that container. Use external service DNS names in production, Compose service names
inside the development network, or `host.docker.internal` for host services on Docker
Desktop. PostgreSQL URLs use `postgresql+asyncpg://`; Valkey accepts `redis://` or
`rediss://`. Configure TLS as required by the external providers.

The multi-stage image pins the Python 3.13 base digest and installs runtime dependencies
from `uv.lock` with `--frozen`. uv and its installation cache stay in the builder stage;
pytest, mypy, and other development dependencies are excluded. Application source is
loaded through `PYTHONPATH`, avoiding an editable install and unpinned build dependencies.
Update the base digest and lockfile deliberately when applying dependency/security updates.

The runtime uses UID/GID 10001, exposes only port 8000, and supports a read-only filesystem.
The exec-form Uvicorn command receives SIGTERM, drains requests for up to 20 seconds,
then runs FastAPI shutdown hooks to close pools. Allow 30 seconds before forced termination.
Docker's healthcheck probes `/health`, so a dependency outage does not fail liveness.
Use `/ready` for load-balancer readiness; Docker health status alone does not gate traffic
or automatically restart an unhealthy container.

The build context is an allowlist; environment files and private-key files are excluded,
including when placed under `src/`. Credentials are never build arguments or image
environment defaults. Runtime environment values remain visible to Docker administrators;
restrict daemon access and do not publish rendered Compose configurations containing secrets.

## Production deployment

`infra/docker/compose.production.yaml` is a **standalone** deployment file with just the
backend. PostgreSQL and Valkey must already exist outside this deployment. Do not merge
the development Compose file into it.

Build and tag the release image above, or pull your registry's immutable release image.
Provide `BACKEND_IMAGE`, `APPLICATION_VERSION`, `POSTGRES_URL`, and `VALKEY_URL` through
the deployment environment. Compose rejects missing or empty values. Alternatively,
copy `infra/docker/.env.example` to an untracked `infra/docker/.env.production`, replace
the placeholders locally, and use `--env-file infra/docker/.env.production` before `-f`.
Do not commit the resulting file. The template lists the optional settings as well.

```sh
docker compose -p prettylisa-production -f infra/docker/compose.production.yaml up -d --wait
docker compose -p prettylisa-production -f infra/docker/compose.production.yaml ps
docker compose -p prettylisa-production -f infra/docker/compose.production.yaml down
```

The deployment binds to loopback port 8000 by default (override `BACKEND_PORT`), drops
Linux capabilities, prevents privilege escalation, and rotates JSON container logs.
Provide a host reverse proxy/TLS endpoint for public access and route traffic only after
`/ready` succeeds. The image has no database servers and does not create database schemas.

## Run locally with Python

Install Docker with Compose, Python 3.13, and uv. From the repository root:

```powershell
docker compose -f infra/docker/compose.yaml up -d postgres valkey
cd backend
Copy-Item .env.example .env
uv sync --frozen
uv run uvicorn prettylisavpn.main:create_app --factory --reload --no-access-log
```

On macOS/Linux use `cp .env.example .env` instead of `Copy-Item`.
Run uv from `backend/` so settings load that directory's `.env` file.
Environment variables override `.env`; the example lists all supported settings.
Connection strings are secrets and should never be logged. Example credentials are
for local development only; shared deployments require dedicated credentials and
appropriate transport security.

The API listens at `http://127.0.0.1:8000`:

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Always 200 while the application can serve requests; no dependency access. |
| `GET /ready` | Executes PostgreSQL `SELECT 1` and Valkey `PING` on every call; 200 only when both succeed, otherwise 503 with `dependencies_unavailable`. |
| `GET /version` | Returns `application_name`, `application_version`, and `environment`. |

Default version metadata is `PrettyLisaVPN`, `0.1.0`, `development`. Release packaging
can override `APPLICATION_VERSION`. Each readiness probe is bounded by
`DEPENDENCY_TIMEOUT_SECONDS`. Readiness failure does not stop the process. Pools are
disposed on shutdown. Unexpected HTTP errors return a generic `internal_error` code;
validation errors do not echo request inputs. Application logs are JSON with UTC
timestamps. Raw exception messages, SQL parameters, and HTTP access URLs are not logged.

## Verify

From `backend/`:

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
```

The default suite requires no external services. With PostgreSQL and Valkey running,
also run the real integration tests (including individual dependency failures):

```powershell
$env:RUN_INTEGRATION_TESTS = "1"
uv run pytest
```

On macOS/Linux: `RUN_INTEGRATION_TESTS=1 uv run pytest`.
For the opt-in runtime-image tests, build `prettylisavpn-backend:test` from the repository
root with `docker build -t prettylisavpn-backend:test backend`, then from `backend/` run:

```powershell
$env:RUN_DOCKER_TESTS = "1"
uv run pytest -m docker
```

On macOS/Linux: `RUN_DOCKER_TESTS=1 uv run pytest -m docker`.
Use `DOCKER_TEST_IMAGE` to test another tag. These tests check non-root operation, image
contents, liveness without dependencies, graceful SIGTERM shutdown, and production Compose
configuration. They create and remove a temporary container; they do not stop your stack.

CI runs the complete suite against real service containers. To exercise the stack
manually, stop one dependency with `docker compose -f infra/docker/compose.yaml stop valkey`;
`/ready` should become 503 while `/health` remains 200. Start it again to restore readiness.

Stop the stack with `docker compose -f infra/docker/compose.yaml down` from the repository
root. The PostgreSQL named volume retains local data.
