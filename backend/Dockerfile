FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN pip install --no-cache-dir uv==0.12.9 \
    && uv sync --frozen --no-dev \
    && useradd --create-home backend
USER backend
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "prettylisavpn.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
