#!/usr/bin/env sh
set -eu

# Postgres logical backup — intended to run in the backup sidecar / cron job.
# Requires: pg_dump, gzip, POSTGRES_* env vars.

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
FILE="${BACKUP_DIR}/asa_${POSTGRES_DB:-ai_service_advisor}_${STAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[backup] writing ${FILE}"
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
  -h "${POSTGRES_HOST:-postgres}" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "${POSTGRES_USER:-asa}" \
  -d "${POSTGRES_DB:-ai_service_advisor}" \
  --no-owner --no-acl \
  | gzip -c > "$FILE"

# Optional Redis RDB copy if mounted
if [ -f /data/dump.rdb ]; then
  cp /data/dump.rdb "${BACKUP_DIR}/redis_${STAMP}.rdb"
fi

# Retention
find "$BACKUP_DIR" -type f -name 'asa_*.sql.gz' -mtime +"${KEEP_DAYS}" -delete || true
find "$BACKUP_DIR" -type f -name 'redis_*.rdb' -mtime +"${KEEP_DAYS}" -delete || true

ls -lah "$BACKUP_DIR" | tail -n 20
echo "[backup] done"
