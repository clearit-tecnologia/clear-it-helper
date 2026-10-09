# syntax=docker/dockerfile:1.7
# Single image for API, worker, migrations and bootstrap (only the command changes).
# Requires uv.lock (generate with `uv lock`). Pin the images by digest in CI.

ARG UV_IMAGE=ghcr.io/astral-sh/uv:python3.12-bookworm-slim
ARG RUNTIME_IMAGE=python:3.12-slim-bookworm

FROM ${UV_IMAGE} AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Dependencies first, for layer caching.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


FROM ${RUNTIME_IMAGE} AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic

USER 10001:10001

EXPOSE 8000

# Worker:     python -m clear_helper.worker
# Migrations: alembic upgrade head
# Bootstrap:  python -m clear_helper.cli bootstrap
CMD ["uvicorn", "clear_helper.main:app", "--host", "0.0.0.0", "--port", "8000"]
