# QADAM on Hugging Face Spaces (Docker SDK) — free, no card, permanent URL.
#
# This is the ROOT Dockerfile because Spaces builds from the repository root.
# `api/Dockerfile` remains the real one, used by docker compose and by any
# container host that can take a build context; this file adapts it to the two
# things Spaces fixes for you: the container runs as uid 1000, and only a few
# paths are writable.
#
# It serves the API *and* the built web app from one origin. On a free Space
# that is not a compromise -- one origin means no CORS and no bearer token
# crossing an origin boundary, which is what the Vercel rewrite was arranging
# anyway.
#
# NOT A MEDICAL DEVICE. Anything reachable at the Space URL is on the public
# internet, and the storage below is EPHEMERAL: every case, image and answer is
# lost when the Space restarts or rebuilds. That is acceptable for a demo and
# for nothing else.

# --- build the web app ------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /app
COPY web/package.json web/package-lock.json* ./
RUN npm ci || npm install
COPY web/tsconfig.json web/vite.config.ts web/index.html ./
COPY web/public ./public
COPY web/src ./src
RUN npm run build

# --- the API ----------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# opencv-python-headless still links libgthread/libglib at import time.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

# Spaces runs the container as uid 1000. Everything this process writes has to
# live somewhere that user owns.
RUN useradd --create-home --uid 1000 qadam
WORKDIR /srv

COPY api/requirements.txt ./
RUN pip install -r requirements.txt

COPY api/alembic.ini ./
COPY api/alembic ./alembic
COPY api/app ./app
COPY api/docker-entrypoint.sh ./
COPY --from=web /app/dist ./web-dist
RUN chmod +x docker-entrypoint.sh && chown -R qadam:qadam /srv

USER 1000
ENV HOME=/home/qadam

# SQLite and the filesystem, both under a path uid 1000 owns. A Space has no
# managed database and no persistent disk on the free tier, so this resets on
# every restart. `SEED_ON_START` refills it with synthetic cases so the demo is
# never empty.
ENV DATABASE_URL="sqlite+aiosqlite:////home/qadam/qadam.db" \
    STORAGE_BACKEND=local \
    LOCAL_STORAGE_DIR=/home/qadam/storage \
    RUN_MIGRATIONS=true \
    AUTO_CREATE_SCHEMA=false \
    SEED_ON_START=true \
    ENVIRONMENT=prod \
    SERVE_WEB_DIR=/srv/web-dist \
    ANALYSIS_RUNNER=inline \
    CORS_ORIGINS=""

# JWT_SECRET, SEED_ADMIN_PASSWORD and SEED_CLINICIAN_PASSWORD are deliberately
# NOT set here. ENVIRONMENT=prod means app/config.py refuses to start until they
# are supplied as Space secrets — see DEPLOY.md. A Space that fails to boot with
# a clear message is the intended outcome; one serving on published defaults is
# not.

EXPOSE 7860
HEALTHCHECK --interval=20s --timeout=4s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:7860/api/v1/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", "--bind", "0.0.0.0:7860", \
     "--timeout", "180", "--access-logfile", "-"]
