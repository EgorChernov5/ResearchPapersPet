# syntax=docker/dockerfile:1

FROM python:3.12-slim

# Install uv without adding another system package manager layer.
COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

WORKDIR /app

# Cache locked third-party dependencies independently from documentation and source changes.
ENV UV_LINK_MODE=copy
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

# Copy the backend only after dependencies to preserve the build cache.
COPY backend ./backend
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/backend"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
