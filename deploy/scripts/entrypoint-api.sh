#!/usr/bin/env sh
set -eu

echo "[api] waiting for postgres..."
python - <<'PY'
import os, time, sys
import psycopg

url = os.environ.get("DATABASE_URL_SYNC") or os.environ.get("database_url_sync")
if not url:
    # fallback from async URL
    async_url = os.environ.get("DATABASE_URL") or os.environ.get("database_url", "")
    url = async_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )
if not url:
    print("No database URL configured", file=sys.stderr)
    sys.exit(1)

for i in range(60):
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        print("[api] postgres ready")
        break
    except Exception as exc:
        print(f"[api] postgres not ready ({i}): {exc}")
        time.sleep(2)
else:
    sys.exit(1)
PY

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[api] running alembic migrations..."
  alembic upgrade head
fi

WORKERS="${UVICORN_WORKERS:-2}"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers "$WORKERS"
