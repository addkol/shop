#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT_DIR"

ENV_FILE=${ENV_FILE:-.env.production}
FIRST_DEPLOY=${FIRST_DEPLOY:-0}
case "$ENV_FILE" in
    /*|*..*) echo "ENV_FILE должен быть файлом внутри проекта" >&2; exit 1 ;;
esac
case "$FIRST_DEPLOY" in
    0|1) ;;
    *) echo "FIRST_DEPLOY допускает только 0 или 1." >&2; exit 1 ;;
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

if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
    echo "Рабочее дерево сервера содержит изменения. Deploy остановлен." >&2
    git status --short >&2
    exit 1
fi

MEDIA_DIR="$ROOT_DIR/data/media"
test -d "$MEDIA_DIR" || {
    echo "Нет $MEDIA_DIR. Сначала запустите setup-media-permissions.sh." >&2
    exit 1
}
test "$(stat -c %u "$MEDIA_DIR")" = "10001" || {
    echo "Владелец media должен иметь UID 10001." >&2
    exit 1
}
test "$(stat -c %g "$MEDIA_DIR")" = "10001" || {
    echo "Группа media должна иметь GID 10001." >&2
    exit 1
}
getfacl -cp "$MEDIA_DIR" | grep -Eq '^user:www-data:r-x$' || {
    echo "Для media отсутствует read ACL пользователя www-data." >&2
    exit 1
}

DB_CONTAINER=$(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps -a -q db)
DB_RUNNING=$(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps --status running -q db)
PROJECT_NAME=$(env_value COMPOSE_PROJECT_NAME)
PROJECT_NAME=${PROJECT_NAME:-elit-market}
DB_VOLUME="${PROJECT_NAME}_postgres_data"

if [ "$FIRST_DEPLOY" = "1" ]; then
    if [ -n "$DB_CONTAINER" ] || docker volume inspect "$DB_VOLUME" >/dev/null 2>&1; then
        echo "FIRST_DEPLOY=1 запрещён: контейнер или volume PostgreSQL уже существует." >&2
        echo "Не обходите backup. Проверьте состояние и запускайте обычный deploy." >&2
        exit 1
    fi
    echo "Первый deploy: существующей production БД нет, backup не требуется."
else
    test -n "$DB_RUNNING" || {
        echo "PostgreSQL не запущен. Последующий deploy без backup запрещён." >&2
        exit 1
    }
    ENV_FILE="$ENV_FILE" sh "$ROOT_DIR/deploy/scripts/backup.sh"
fi

git pull --ff-only
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml build --pull
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml up -d --wait --wait-timeout 120 db redis
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml run --rm --no-deps migrate
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml up -d --no-deps \
    --remove-orphans --wait --wait-timeout 120 web worker beat

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web \
    python manage.py check --deploy --database default
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web \
    python manage.py migrate --check
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T web \
    sh -c 'probe=/app/media/.deployment-write-test; : > "$probe"; rm -f "$probe"'
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T redis redis-cli ping | grep -q PONG
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T worker \
    celery -A project inspect ping --timeout=10 | grep -q pong

for service in db redis; do
    container_id=$(docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps -q "$service")
    bindings=$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$container_id")
    case "$bindings" in
        '{}'|'null') ;;
        *) echo "ОШИБКА: $service имеет host port bindings: $bindings" >&2; exit 1 ;;
    esac
done

APP_PORT=$(env_value APP_PORT)
APP_PORT=${APP_PORT:-8010}
python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${APP_PORT}/health/', timeout=10)"
docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml ps
echo "Deployment завершён: migrations, app, Redis, Celery и readiness проверены."
