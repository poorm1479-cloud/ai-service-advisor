#!/usr/bin/env bash
# Backup restore drill — restores latest dump into a temporary database and writes evidence JSON.
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
EVIDENCE_DIR="${EVIDENCE_DIR:-./backups/evidence}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-asa}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-asa}"
SOURCE_DB="${POSTGRES_DB:-ai_service_advisor}"
DRILL_DB="${DRILL_DB:-asa_restore_drill_${STAMP}}"

mkdir -p "$BACKUP_DIR" "$EVIDENCE_DIR"

LATEST="$(ls -1t "$BACKUP_DIR"/asa_*.sql.gz 2>/dev/null | head -n 1 || true)"
if [[ -z "$LATEST" ]]; then
  echo "[drill] no backup found in $BACKUP_DIR — creating one first"
  BACKUP_DIR="$BACKUP_DIR" POSTGRES_HOST="$POSTGRES_HOST" POSTGRES_PORT="$POSTGRES_PORT" \
    POSTGRES_USER="$POSTGRES_USER" POSTGRES_PASSWORD="$POSTGRES_PASSWORD" POSTGRES_DB="$SOURCE_DB" \
    bash "$(dirname "$0")/backup.sh"
  LATEST="$(ls -1t "$BACKUP_DIR"/asa_*.sql.gz | head -n 1)"
fi

echo "[drill] using backup: $LATEST"
echo "[drill] creating temp db: $DRILL_DB"

export PGPASSWORD="$POSTGRES_PASSWORD"
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres \
  -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DRILL_DB\";" \
  -c "CREATE DATABASE \"$DRILL_DB\";"

gunzip -c "$LATEST" | psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$DRILL_DB" -v ON_ERROR_STOP=1 >/dev/null

TABLE_COUNT="$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$DRILL_DB" -Atc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"

EVIDENCE_FILE="${EVIDENCE_DIR}/restore_drill_${STAMP}.json"
cat > "$EVIDENCE_FILE" <<EOF
{
  "drill_id": "${STAMP}",
  "performed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "backup_file": "$(basename "$LATEST")",
  "source_database": "${SOURCE_DB}",
  "restore_database": "${DRILL_DB}",
  "public_table_count": ${TABLE_COUNT},
  "result": "pass",
  "operator": "${DRILL_OPERATOR:-unknown}",
  "notes": "Automated restore drill. Drop temp DB after evidence capture."
}
EOF

echo "[drill] evidence written: $EVIDENCE_FILE"
echo "[drill] cleaning temp db"
psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS \"$DRILL_DB\";"

echo "[drill] done"
cat "$EVIDENCE_FILE"
