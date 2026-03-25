# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

RUN apk add --no-cache git && \
    corepack enable && corepack prepare pnpm@10.33.0 --activate

WORKDIR /app

# Copy minimal .git metadata so we can read the commit hash
COPY .git/HEAD .git/HEAD
COPY .git/refs .git/refs

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# Bake git hash into the frontend build; falls back to 'unknown' if .git is incomplete
ENV VITE_GIT_HASH=""
RUN VITE_GIT_HASH=$(cd /app && git rev-parse --short HEAD 2>/dev/null || echo "unknown") \
    pnpm run build


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
