#!/usr/bin/env bash
set -euo pipefail

backup_dir="${REACHPATH_BACKUP_DIR:-./backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"

docker compose exec -T postgres pg_dump \
  -U "${REACHPATH_POSTGRES_USER:-reachpath}" \
  -d "${REACHPATH_POSTGRES_DB:-reachpath}" \
  --no-owner --no-privileges \
  > "$backup_dir/reachpath-$timestamp.sql"

find "$backup_dir" -maxdepth 1 -type f -name 'reachpath-*.sql' -mtime +14 -delete
echo "Backup written to $backup_dir/reachpath-$timestamp.sql"
