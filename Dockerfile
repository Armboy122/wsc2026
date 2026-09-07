# PEA One Agent — local demo image (single service, non-root).
# Demo packaging only: NOT production-ready (see PRD.md release status).
FROM python:3.11.14-slim-bookworm

# Pin uv to the same version that resolved uv.lock (avoid lock-format drift).
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1 \
    # Fixed state location (writable named volume mounted here in compose.yaml)
    DB_PATH=/var/lib/pea/pea.db \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependency layer: only what uv needs to sync the lockfile.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --extra voice --no-install-project

# Runtime source: explicit allowlist copy (see .dockerignore).
COPY llm-settings.yaml ./
COPY app ./app
COPY web ./web
COPY knowledge/source ./knowledge/source
COPY knowledge/aliases ./knowledge/aliases
COPY data/mock ./data/mock

# COPY preserves restrictive host modes (e.g. 0600); normalize so the runtime
# user can read app source, assets and knowledge documents (dirs get r-x).
RUN chmod -R u=rwX,go=rX /app/app /app/web /app/knowledge /app/data \
    && chmod u=rw,go=r /app/llm-settings.yaml

# Non-root runtime account; /var/lib/pea ownership is copied into the named
# volume by Docker on first mount (empty named volumes inherit image dir owner).
RUN groupadd --gid 10001 pea \
    && useradd --uid 10001 --gid pea --no-create-home --shell /usr/sbin/nologin pea \
    && mkdir -p /var/lib/pea \
    && chown pea:pea /var/lib/pea

USER pea

# Use the synced virtualenv for the exec-form entrypoint.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Availability probe: HTTP 200 on /health means the process serves requests.
# "degraded" (provider not ready) still returns 200 and is intentionally NOT
# treated as unhealthy here — degraded is not provider readiness.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

ENTRYPOINT ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
