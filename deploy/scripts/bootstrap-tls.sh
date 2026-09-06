#!/usr/bin/env sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Запустите скрипт через sudo." >&2
    exit 1
fi

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
DOMAIN=${DOMAIN:-}
LETSENCRYPT_EMAIL=${LETSENCRYPT_EMAIL:-}
PROJECT_ROOT=${PROJECT_ROOT:-/opt/onlineshop}
APP_PORT=${APP_PORT:-8010}
SITE_PATH=${NGINX_SITE_PATH:-/etc/nginx/sites-available/onlineshop}
SITE_LINK=${NGINX_SITE_LINK:-/etc/nginx/sites-enabled/onlineshop}

test -n "$DOMAIN" || { echo "Укажите DOMAIN." >&2; exit 1; }
test -n "$LETSENCRYPT_EMAIL" || { echo "Укажите LETSENCRYPT_EMAIL." >&2; exit 1; }
printf '%s' "$DOMAIN" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]$' || {
    echo "Некорректный DOMAIN." >&2
    exit 1
}
printf '%s' "$PROJECT_ROOT" | grep -Eq '^/[A-Za-z0-9._/-]+$' || {
    echo "Некорректный PROJECT_ROOT." >&2
    exit 1
}
printf '%s' "$APP_PORT" | grep -Eq '^[0-9]+$' || { echo "Некорректный APP_PORT." >&2; exit 1; }
command -v nginx >/dev/null 2>&1 || { echo "Nginx не установлен." >&2; exit 1; }
command -v certbot >/dev/null 2>&1 || { echo "Certbot не установлен." >&2; exit 1; }

TMP_DIR=$(mktemp -d)
cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT HUP INT TERM

render_config() {
    template=$1
    target=$2
    sed \
        -e "s|__DOMAIN__|$DOMAIN|g" \
        -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
        -e "s|__APP_PORT__|$APP_PORT|g" \
        "$template" > "$target"
}

mkdir -p /var/www/certbot "$(dirname "$SITE_PATH")" "$(dirname "$SITE_LINK")"
render_config "$ROOT_DIR/deploy/nginx/onlineshop-http.conf" "$TMP_DIR/onlineshop-http.conf"
install -m 0644 "$TMP_DIR/onlineshop-http.conf" "$SITE_PATH"
ln -sfn "$SITE_PATH" "$SITE_LINK"
nginx -t
systemctl reload nginx

certbot certonly \
    --webroot \
    --webroot-path /var/www/certbot \
    --domain "$DOMAIN" \
    --email "$LETSENCRYPT_EMAIL" \
    --agree-tos \
    --non-interactive \
    --keep-until-expiring

render_config "$ROOT_DIR/deploy/nginx/onlineshop.conf" "$TMP_DIR/onlineshop-https.conf"
install -m 0644 "$TMP_DIR/onlineshop-https.conf" "$SITE_PATH"
if ! nginx -t; then
    install -m 0644 "$TMP_DIR/onlineshop-http.conf" "$SITE_PATH"
    nginx -t
    systemctl reload nginx
    echo "HTTPS-конфигурация не прошла nginx -t; восстановлен безопасный HTTP config." >&2
    exit 1
fi
systemctl reload nginx
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
printf '%s\n' '#!/bin/sh' 'nginx -t && systemctl reload nginx' \
    > /etc/letsencrypt/renewal-hooks/deploy/onlineshop-reload-nginx.sh
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/onlineshop-reload-nginx.sh
echo "TLS выпущен и HTTPS-конфигурация включена для $DOMAIN."
