#!/bin/sh
set -e

echo "QADAM API — NOT A MEDICAL DEVICE, not for clinical use."

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "Applying database migrations…"
  alembic upgrade head
fi

if [ "${SEED_ON_START:-false}" = "true" ]; then
  echo "Seeding demo data…"
  python -m app.seed || echo "seed skipped (already populated)"
fi

exec "$@"
