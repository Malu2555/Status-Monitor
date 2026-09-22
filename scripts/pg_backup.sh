#!/usr/bin/env bash
# PostgreSQL backup with simple daily rotation (Linux).
#
# Uses standard libpq env vars (PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE)
# or, when set, the app's DATABASE_URL directly.
#
# Schedule daily via cron, e.g.:
#   30 2 * * * /opt/statusmonitor/scripts/pg_backup.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/statusmonitor}"
KEEP_DAILY="${KEEP_DAILY:-7}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
OUTPUT="${BACKUP_DIR}/statusmonitor-${STAMP}.dump"

mkdir -p "${BACKUP_DIR}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  pg_dump --format=custom "${DATABASE_URL}" --file="${OUTPUT}"
else
  pg_dump --format=custom --file="${OUTPUT}"
fi

echo "backup written: ${OUTPUT}"
find "${BACKUP_DIR}" -name 'statusmonitor-*.dump' -mtime "+${KEEP_DAILY}" -delete
echo "rotation done; keeping ${KEEP_DAILY} daily file(s)"
