FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv

FROM python:3.14.7-slim-trixie@sha256:5b945726c4d7ffe6595dc7498ad17fd0397e373c5181c24819a7028e8b1276dc AS builder

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

COPY apps/backend/pyproject.toml apps/backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/backend/alembic.ini ./alembic.ini
COPY apps/backend/alembic ./alembic
COPY apps/backend/app ./app
COPY apps/backend/scripts ./scripts
RUN uv sync --frozen --no-dev

FROM python:3.14.7-slim-trixie@sha256:5b945726c4d7ffe6595dc7498ad17fd0397e373c5181c24819a7028e8b1276dc AS runtime

RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends \
        libssl3t64=3.5.7-1~deb13u2 \
        openssl=3.5.7-1~deb13u2 \
        openssl-provider-legacy=3.5.7-1~deb13u2 \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip uninstall --yes pip

WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app/storage/uploads /app/storage/settings-media \
    && chown -R app:app /app/storage

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/alembic.ini /app/alembic.ini
COPY --from=builder --chown=app:app /app/alembic /app/alembic
COPY --from=builder --chown=app:app /app/app /app/app
COPY --from=builder --chown=app:app /app/scripts /app/scripts

USER app
VOLUME ["/app/storage"]
EXPOSE 18168
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18168/health/ready', timeout=2)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "18168"]
