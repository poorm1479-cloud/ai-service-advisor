#!/usr/bin/env sh
set -eu

# Restore from a gzipped pg_dump. Usage: restore.sh /backups/asa_....sql.gz

DUMP="${1:-}"
if [ -z "$DUMP" ] || [ ! -f "$DUMP" ]; then
  echo "Usage: $0 /backups/asa_<db>_<timestamp>.sql.gz" >&2
  exit 1
fi

echo "[restore] restoring ${DUMP} into ${POSTGRES_DB:-ai_service_advisor}"
gunzip -c "$DUMP" | PGPASSWORD="${POSTGRES_PASSWORD}" psql \
  -h "${POSTGRES_HOST:-postgres}" \
  -p "${POSTGRES_PORT:-5432}" \
  -U "${POSTGRES_USER:-asa}" \
  -d "${POSTGRES_DB:-ai_service_advisor}"

echo "[restore] complete"
