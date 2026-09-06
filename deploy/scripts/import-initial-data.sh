#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT_DIR"

ENV_FILE=${ENV_FILE:-.env.production}
BUNDLE_DIR=${1:-}
test -n "$BUNDLE_DIR" || {
    echo "Использование: sh deploy/scripts/import-initial-data.sh data/imports/<bundle>" >&2
    exit 1
}
case "$ENV_FILE" in
    /*|*..*) echo "ENV_FILE должен быть файлом внутри проекта" >&2; exit 1 ;;
esac
test -f "$ENV_FILE" || { echo "Отсутствует $ENV_FILE" >&2; exit 1; }
export APP_ENV_FILE="$ENV_FILE"

BUNDLE_DIR=$(realpath "$BUNDLE_DIR")
IMPORT_ROOT=$(realpath "$ROOT_DIR/data/imports")
case "$BUNDLE_DIR/" in
    "$IMPORT_ROOT"/*/) ;;
    *) echo "Bundle должен находиться внутри $IMPORT_ROOT" >&2; exit 1 ;;
esac
test -f "$BUNDLE_DIR/manifest.json" || { echo "manifest.json не найден" >&2; exit 1; }

find "$BUNDLE_DIR" -type d -exec setfacl -m u:10001:r-x {} +
find "$BUNDLE_DIR" -type f -exec setfacl -m u:10001:r-- {} +

test -n "$(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps --status running -q db)" || {
    echo "PostgreSQL container не запущен." >&2
    exit 1
}

set -- python manage.py import_initial_data /initial-import --confirm-import --restore-media
if [ "${ACCEPT_CLASSIFIED_DATA:-0}" = "1" ]; then
    set -- "$@" --accept-classified-data
fi
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml run --rm --no-deps \
    -v "$BUNDLE_DIR:/initial-import:ro" web "$@"
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web \
    python manage.py verify_media_references
echo "Первичный перенос SQLite и media завершён и проверен."
