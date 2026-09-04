# Pin the Python 3.13 manifest; update deliberately for security releases.
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285 AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

FROM base AS builder
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.9
COPY pyproject.toml uv.lock ./
# Only install locked third-party dependencies; no editable install or unpinned
# application build dependencies are needed when loading the source via PYTHONPATH.
RUN uv sync --frozen --no-dev --no-install-project --no-cache

FROM base AS runtime
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src
RUN groupadd --gid 10001 backend \
    && useradd --uid 10001 --gid backend --no-create-home --shell /usr/sbin/nologin backend
COPY --from=builder /app/.venv /app/.venv
COPY src /app/src
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).close()"]
CMD ["uvicorn", "prettylisavpn.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "20"]
