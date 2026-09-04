# Backend

Python 3.13 FastAPI modular-monolith skeleton. No business modules or database tables
exist yet, so no Alembic migration is needed at this stage. Add Alembic with the first
schema change. PostgreSQL uses SQLAlchemy 2.x and asyncpg; Valkey uses the Redis-compatible
redis-py async client. Connection pools belong to the application lifespan and connect
lazily. `Postgres.session()` closes sessions and rolls back uncommitted work; callers
must explicitly commit successful writes.

## Run locally

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

Alternatively, run the complete stack without installing Python or uv on the host:

```sh
docker compose -f infra/docker/compose.yaml up --build -d
```

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
CI runs the complete suite against real service containers. To exercise the stack
manually, stop one dependency with `docker compose -f infra/docker/compose.yaml stop valkey`;
`/ready` should become 503 while `/health` remains 200. Start it again to restore readiness.

Stop the stack with `docker compose -f infra/docker/compose.yaml down` from the repository
root. The PostgreSQL named volume retains local data.
