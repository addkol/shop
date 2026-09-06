#!/usr/bin/env sh
set -eu
umask 077

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT_DIR"

ENV_FILE=${ENV_FILE:-.env.production}
case "$ENV_FILE" in
    /*|*..*) echo "ENV_FILE должен быть файлом внутри проекта" >&2; exit 1 ;;
esac
test -f "$ENV_FILE" || { echo "Отсутствует $ENV_FILE" >&2; exit 1; }
export APP_ENV_FILE="$ENV_FILE"

env_value() {
    awk -F= -v key="$1" '
        $1 == key {
            sub(/^[^=]*=/, "")
            value = $0
        }
        END {
            gsub(/\r$/, "", value)
            gsub(/^"|"$/, "", value)
            print value
        }
    ' "$ENV_FILE"
}

POSTGRES_USER=$(env_value POSTGRES_USER)
POSTGRES_DB=$(env_value POSTGRES_DB)
BACKUP_ROOT=$(env_value BACKUP_ROOT)
BACKUP_ROOT=${BACKUP_ROOT:-$ROOT_DIR/backups}
test -n "$POSTGRES_USER" || { echo "POSTGRES_USER не задан." >&2; exit 1; }
test -n "$POSTGRES_DB" || { echo "POSTGRES_DB не задан." >&2; exit 1; }
test -n "$(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps --status running -q db)" || {
    echo "Нельзя создать backup: PostgreSQL container не запущен." >&2
    exit 1
}

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_ROOT"
mkdir "$TARGET"
COMPLETE=0
cleanup() {
    if [ "$COMPLETE" -ne 1 ]; then
        rm -f "$TARGET/database.dump" "$TARGET/media.tar.gz" "$TARGET/SHA256SUMS" "$TARGET/BACKUP_COMPLETE"
        rmdir "$TARGET" 2>/dev/null || true
    fi
}
trap cleanup EXIT HUP INT TERM

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T db \
    pg_dump --format=custom --no-owner --no-acl --username "$POSTGRES_USER" "$POSTGRES_DB" \
    > "$TARGET/database.dump"
test -s "$TARGET/database.dump" || { echo "pg_dump создал пустой файл." >&2; exit 1; }
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T db \
    pg_restore --list < "$TARGET/database.dump" >/dev/null

if [ -d "$ROOT_DIR/data/media" ]; then
    tar -C "$ROOT_DIR/data" -czf "$TARGET/media.tar.gz" media
    tar -tzf "$TARGET/media.tar.gz" >/dev/null
fi

(
    cd "$TARGET"
    sha256sum database.dump > SHA256SUMS
    if [ -f media.tar.gz ]; then
        sha256sum media.tar.gz >> SHA256SUMS
    fi
    sha256sum -c SHA256SUMS >/dev/null
    printf 'created_at=%s\npostgres_database=%s\n' "$STAMP" "$POSTGRES_DB" > BACKUP_COMPLETE
)
COMPLETE=1
echo "Проверенный backup создан: $TARGET"
