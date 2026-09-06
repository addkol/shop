#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите скрипт через sudo." >&2
    exit 1
fi

PROJECT_ROOT=${PROJECT_ROOT:-/opt/onlineshop}
DEPLOY_USER=${DEPLOY_USER:-${SUDO_USER:-}}
APP_UID=${APP_UID:-10001}
APP_GID=${APP_GID:-10001}

test -n "$DEPLOY_USER" || { echo "Укажите DEPLOY_USER." >&2; exit 1; }
id "$DEPLOY_USER" >/dev/null 2>&1 || { echo "Пользователь $DEPLOY_USER не найден." >&2; exit 1; }
id www-data >/dev/null 2>&1 || { echo "Пользователь Nginx www-data не найден." >&2; exit 1; }
command -v setfacl >/dev/null 2>&1 || {
    echo "Установите пакет acl: apt-get install acl" >&2
    exit 1
}

DATA_DIR="$PROJECT_ROOT/data"
MEDIA_DIR="$DATA_DIR/media"
IMPORT_DIR="$DATA_DIR/imports"
mkdir -p "$MEDIA_DIR" "$IMPORT_DIR"

chown -R "$APP_UID:$APP_GID" "$MEDIA_DIR"
find "$MEDIA_DIR" -type d -exec chmod 2750 {} +
find "$MEDIA_DIR" -type f -exec chmod 0640 {} +
setfacl -m "u:www-data:--x,u:$DEPLOY_USER:r-x" "$DATA_DIR"
setfacl -R -m "u:www-data:rX,u:$DEPLOY_USER:rX,m::rX" "$MEDIA_DIR"
find "$MEDIA_DIR" -type d -exec setfacl -m \
    "d:u::rwx,d:u:www-data:r-x,d:u:$DEPLOY_USER:r-x,d:g::r-x,d:m::r-x,d:o::---" {} +

chown -R "$DEPLOY_USER:$APP_GID" "$IMPORT_DIR"
find "$IMPORT_DIR" -type d -exec chmod 2750 {} +
find "$IMPORT_DIR" -type f -exec chmod 0640 {} +
setfacl -R -m "u:$APP_UID:rX,m::rX" "$IMPORT_DIR"
find "$IMPORT_DIR" -type d -exec setfacl -m \
    "d:u::rwx,d:u:$APP_UID:r-x,d:g::r-x,d:m::r-x,d:o::---" {} +

runuser -u www-data -- test -r "$MEDIA_DIR"
if command -v setpriv >/dev/null 2>&1; then
    PROBE="$MEDIA_DIR/.appuser-write-test"
    setpriv --reuid="$APP_UID" --regid="$APP_GID" --clear-groups touch "$PROBE"
    rm -f "$PROBE"
fi

echo "Права media настроены: appuser $APP_UID:$APP_GID пишет, www-data читает."
