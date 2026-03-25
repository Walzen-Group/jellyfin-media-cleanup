# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

# Git hash passed from docker compose build for version display in the UI
ARG GIT_HASH=unknown
ENV VITE_GIT_HASH=$GIT_HASH

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm run build


# ---- Stage 2: Python runtime ----
FROM python:3.11-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python dependencies (cached layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen

# Copy application code
COPY src/ src/

# Copy built frontend
COPY --from=frontend-build /app/frontend/dist frontend/dist

EXPOSE 8000

ENV JELLYFIN_URL="" \
    JELLYFIN_API_KEY="" \
    SONARR_URL="" \
    SONARR_API_KEY="" \
    RADARR_URL="" \
    RADARR_API_KEY="" \
    MONTH_THRESHOLD="24"

ENTRYPOINT ["uv", "run", "media-cleanup-server"]
