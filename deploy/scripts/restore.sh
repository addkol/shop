#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
BACKUP_DIR=${1:-}
ENV_FILE=${ENV_FILE:-.env.production}

test -n "$BACKUP_DIR" || { echo "Использование: CONFIRM_RESTORE=YES $0 backups/<timestamp>" >&2; exit 1; }
test "${CONFIRM_RESTORE:-}" = "YES" || { echo "Для восстановления установите CONFIRM_RESTORE=YES" >&2; exit 1; }
case "$ENV_FILE" in
    /*|*..*) echo "ENV_FILE должен быть файлом внутри проекта" >&2; exit 1 ;;
esac
test -f "$ROOT_DIR/$ENV_FILE" || { echo "Отсутствует $ENV_FILE" >&2; exit 1; }
export APP_ENV_FILE="$ENV_FILE"

set -a
. "$ROOT_DIR/$ENV_FILE"
set +a

BACKUP_ROOT=${BACKUP_ROOT:-$ROOT_DIR/backups}
ROOT_REAL=$(realpath "$BACKUP_ROOT")
BACKUP_REAL=$(realpath "$BACKUP_DIR")
case "$BACKUP_REAL" in
    "$ROOT_REAL"/*) ;;
    *) echo "Backup должен находиться внутри $ROOT_REAL" >&2; exit 1 ;;
esac

cd "$ROOT_DIR"
test -f "$BACKUP_REAL/database.dump" || { echo "database.dump не найден" >&2; exit 1; }
(cd "$BACKUP_REAL" && sha256sum -c SHA256SUMS)

SERVICES_STOPPED=0
restore_failed() {
    if [ "$SERVICES_STOPPED" = "1" ]; then
        echo "Restore не завершён; web/worker/beat оставлены остановленными для проверки." >&2
    fi
}
trap restore_failed EXIT INT TERM

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml stop web worker beat
SERVICES_STOPPED=1
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T db \
    psql --set ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --command "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T db \
    pg_restore --exit-on-error --single-transaction --no-owner --no-acl --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    < "$BACKUP_REAL/database.dump"

if [ "${RESTORE_MEDIA:-0}" = "1" ] && [ -f "$BACKUP_REAL/media.tar.gz" ]; then
    docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml run --rm --no-deps -T web \
        tar --no-same-owner -C /app -xzf - < "$BACKUP_REAL/media.tar.gz"
fi

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml run --rm --no-deps migrate
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml run --rm --no-deps web \
    python manage.py verify_media_references
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml up -d --no-deps web worker beat
SERVICES_STOPPED=0
trap - EXIT INT TERM
echo "Восстановление завершено. Проверьте /health/ и контрольные заказы."
