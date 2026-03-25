# ---- Stage 1: Build frontend ----
FROM node:22-alpine AS frontend-build

RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

WORKDIR /app

# Copy .git metadata (heavy dirs excluded via .dockerignore) for commit hash
COPY .git .git

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

# Resolve git hash from .git metadata (no git binary needed).
# Reads HEAD, follows ref pointer, checks refs/ then packed-refs.
RUN GIT_HEAD=$(cat /app/.git/HEAD); \
    if echo "$GIT_HEAD" | grep -q "^ref: "; then \
      REF=$(echo "$GIT_HEAD" | sed 's/^ref: //'); \
      if [ -f "/app/.git/$REF" ]; then \
        HASH=$(cat "/app/.git/$REF"); \
      elif [ -f "/app/.git/packed-refs" ]; then \
        HASH=$(grep "$REF" /app/.git/packed-refs | head -1 | cut -d' ' -f1); \
      fi; \
    else \
      HASH=$GIT_HEAD; \
    fi; \
    export VITE_GIT_HASH=$(echo "${HASH:-unknown}" | cut -c1-7); \
    echo "Building frontend with git hash: $VITE_GIT_HASH"; \
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

# Runtime config -- all secrets provided via env_file (secrets.env), not baked into image
ENV MONTH_THRESHOLD="24"

ENTRYPOINT ["uv", "run", "media-cleanup-server"]
