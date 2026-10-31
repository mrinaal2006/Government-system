#!/usr/bin/env bash
# Encrypted backup of the database and object storage.
#
#   BACKUP_PASSPHRASE=... ./scripts/backup.sh [output-dir]
#
# Produces <output-dir>/dgimews-<UTC timestamp>/ containing:
#   database.dump.enc  - pg_dump custom format, AES-256 (openssl, PBKDF2 600k iterations)
#   objects.tar.enc    - all objects from the private bucket
#   manifest.sha256    - checksums of the encrypted files
# NOT included (back these up separately in the secret store): .env secrets, in
# particular DATA_ENCRYPTION_KEY, without which encrypted citizen data cannot be read.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE (store it in the secret manager, not with the backup)}"
COMPOSE=(docker compose ${COMPOSE_FILES:-})
set -a; . ./.env; set +a
OUT="${1:-backups}/dgimews-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
umask 077

enc() { openssl enc -aes-256-cbc -salt -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -out "$1"; }

echo "Dumping database ${DATABASE_NAME:-dgimews}..."
"${COMPOSE[@]}" exec -T db pg_dump -U postgres -d "${DATABASE_NAME:-dgimews}" -Fc | enc "$OUT/database.dump.enc"
echo "Exporting object storage..."
"${COMPOSE[@]}" exec -T api python -m app.cli export-objects | enc "$OUT/objects.tar.enc"
(cd "$OUT" && sha256sum database.dump.enc objects.tar.enc > manifest.sha256)
echo "Backup written to $OUT"
