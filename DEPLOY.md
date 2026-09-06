# Production-деплой на Hetzner

Рабочая админка находится в /dashboard/. После первой миграции создайте группы командой
setup_dashboard_roles и назначьте сотрудникам is_staff и нужную группу.
Полная инструкция, точные права и временный FIXED_OTP_CODE описаны в [DASHBOARD.md](DASHBOARD.md).
Общий OTP разрешён в production только как явное SMS-исключение с предупреждением;
он не отменяет обязательные Finik/SMTP/HTTPS/DB/Redis проверки.

Проект запускается как отдельный Docker Compose project `elit-market`. Он использует собственные PostgreSQL/Redis volumes и публикует только Django на `127.0.0.1:8010`. PostgreSQL `5432` и Redis `6379` на host не публикуются, поэтому существующий PostgreSQL другого проекта не конфликтует с OnlineShop.

## Адрес и DNS

Используйте отдельный домен или поддомен, например `shop.example.com`, с A/AAAA-записью на Hetzner. Без домена нельзя безопасно включить production cookies, Finik webhook и обычный Let's Encrypt TLS. Шаблоны Nginx содержат placeholders и не должны копироваться напрямую без рендера.

## Требования

- Ubuntu 24.04 LTS или другая поддерживаемая Ubuntu.
- Docker Engine и Docker Compose plugin.
- Host Nginx, Certbot и пакет `acl`.
- Открытые внешние порты только `22`, `80`, `443`.
- Свободный loopback-порт `8010` или другой `APP_PORT`.

```bash
docker ps --format 'table {{.Names}}\t{{.Ports}}'
sudo ss -lntp
sudo apt-get update
sudo apt-get install -y nginx certbot acl
```

## Подготовка проекта

```bash
sudo mkdir -p /opt/onlineshop
sudo chown "$USER":"$USER" /opt/onlineshop
git clone https://github.com/addkol/shop.git /opt/onlineshop
cd /opt/onlineshop
cp .env.production.example .env.production
chmod 600 .env.production
mkdir -p backups
```

Сгенерируйте разные секреты:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Первое значение задайте как `SECRET_KEY`, второе — одинаково как `POSTGRES_PASSWORD` и `DB_PASSWORD`. Заполните точные `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, SMTP, SMS и Finik credentials. `FINIK_STATUS_API_URL` — подписанный endpoint статуса, содержащий `{payment_id}`; его фактический production URL необходимо подтвердить и проверить с Finik до открытия продаж.

## Права media

Контейнер Django работает как UID/GID `10001:10001`, а host Nginx — как `www-data`. Скрипт назначает владельца media и POSIX ACL: Django может создавать файлы, Nginx и deploy-пользователь могут только читать.

```bash
cd /opt/onlineshop
sudo env PROJECT_ROOT=/opt/onlineshop DEPLOY_USER="$USER" \
  sh deploy/scripts/setup-media-permissions.sh
```

Повторный запуск скрипта безопасен. `deploy.sh` остановится, если владелец `data/media` или ACL `www-data` не настроены. После запуска контейнера он дополнительно создаёт и удаляет контрольный файл от имени `appuser`.

## Подготовка SQLite bundle

Эти команды выполняются локально до Hetzner. Остановите изменения каталога и media на время экспорта; исходная SQLite должна иметь все migrations текущего кода (сначала резервная копия, затем `migrate`). Экспорт ничего не удаляет. Сначала выводится классификация test/stub-кандидатов:

```powershell
.\.venv\Scripts\python.exe manage.py export_initial_data --audit-only
```

После ручной проверки создайте новый защищённый каталог bundle вне Git:

```powershell
.\.venv\Scripts\python.exe manage.py export_initial_data `
  --output-dir C:\secure\onlineshop-initial-20260906 `
  --accept-classified-data
```

`--accept-classified-data` нужен только когда отчёт содержит test/stub-кандидаты. Они переносятся без удаления. Bundle содержит:

- `initial-data.json` с пользователями, профилями, категориями, товарами, галереями, оптовыми ценами, корзинами, адресами, заказами, позициями, отзывами и платежными событиями;
- `media.tar.gz` только с файлами, на которые реально ссылаются `FileField/ImageField`;
- `manifest.json` с классификацией, количеством записей и SHA-256 каждого media-файла;
- `SHA256SUMS` для проверки артефактов.

Bundle содержит password hashes и историю заказов: не отправляйте его в Git и передавайте только по SSH. Перед передачей отдельно сохраните показанный SHA-256 файла `SHA256SUMS`.

## Первый deploy

Первый запуск обозначается явно. Он разрешён только когда контейнера и volume OnlineShop PostgreSQL ещё нет:

```bash
cd /opt/onlineshop
FIRST_DEPLOY=1 sh deploy/scripts/deploy.sh
```

Скрипт проверяет чистый Git checkout и media ACL, делает `git pull --ff-only`, собирает image, запускает только собственные `db`/`redis`, применяет migrations отдельным контейнером, запускает web/worker/beat и проверяет Django, migrations, запись media, Redis, Celery и `/health/`. `check --deploy` проверяет конфигурацию, но не действительность внешних ключей: реальные SMS/SMTP/Finik операции проверяются отдельно.

Если первая попытка уже создала PostgreSQL container/volume, не удаляйте volume вслепую и не повторяйте `FIRST_DEPLOY=1`. Поднимите БД, проверьте её состояние и запускайте обычный deploy: он сначала создаст backup, даже если БД ещё пуста.

## Первый import данных и media

На сервере каталог `data/imports` уже подготовлен ACL-скриптом. Передайте bundle, не меняя его содержимое:

```bash
rsync -a --chmod=Du=rwx,Dg=rx,Do=,Fu=rw,Fg=r,Fo= \
  onlineshop-initial-20260906/ user@server:/opt/onlineshop/data/imports/initial/
```

Проверьте сохранённый локально fingerprint, затем запустите import:

```bash
cd /opt/onlineshop
sha256sum data/imports/initial/SHA256SUMS
ACCEPT_CLASSIFIED_DATA=1 sh deploy/scripts/import-initial-data.sh data/imports/initial
```

Без `ACCEPT_CLASSIFIED_DATA=1` import останавливается, если manifest содержит test/stub-кандидаты. Команда разрешена только для PostgreSQL без бизнес-данных. Она допускает лишь категории, автоматически созданные migration seed, удаляет только этот известный seed внутри транзакции, загружает fixture, сверяет количество строк, безопасно распаковывает media и проверяет все ссылки и SHA-256. Простое копирование `db.sqlite3` в production не используется.

Если SQLite-данные переносить не нужно, создайте администратора после первого deploy:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec web \
  python manage.py createsuperuser
```

## TLS bootstrap

DNS уже должен указывать на сервер, а порты `80/443` должны быть доступны. Скрипт сначала устанавливает HTTP-only конфигурацию без ссылок на сертификат, выполняет `nginx -t`, получает сертификат через webroot и только после этого включает HTTPS-конфигурацию. При ошибке финального `nginx -t` остаётся безопасный HTTP bootstrap.

```bash
cd /opt/onlineshop
sudo env DOMAIN=shop.example.com LETSENCRYPT_EMAIL=admin@example.com \
  PROJECT_ROOT=/opt/onlineshop APP_PORT=8010 \
  sh deploy/scripts/bootstrap-tls.sh
```

Проверка:

```bash
curl -fsS http://127.0.0.1:8010/health/live/
curl -fsS https://shop.example.com/health/
sudo nginx -t
sudo certbot renew --dry-run
docker compose --env-file .env.production -f docker-compose.prod.yml ps
```

## Finik перед продажами

Зарегистрируйте `https://shop.example.com/webhook/finik/`. Проверьте beta, затем production: создание QR, `PENDING/PROCESSING`, подтверждённый `SUCCEEDED`, `FAILED/CANCELED`, повторный webhook, timeout API и позднюю оплату отменённого заказа. Redirect браузера никогда не подтверждает оплату; заказ становится оплаченным только после валидного подписанного webhook или явного успешного ответа `check_payment_status()` с совпадающей суммой.

## Последующие deploy

```bash
cd /opt/onlineshop
sh deploy/scripts/deploy.sh
```

Обычный deploy требует уже работающий OnlineShop PostgreSQL и всегда создаёт/проверяет backup до `git pull`, build и migrations. Флага пропуска backup нет. Если БД остановлена или dump невалиден, deploy завершается до изменения кода и схемы.

## Проверка портов

```bash
docker inspect --format '{{json .HostConfig.PortBindings}}' \
  "$(docker compose --env-file .env.production -f docker-compose.prod.yml ps -q db)"
docker inspect --format '{{json .HostConfig.PortBindings}}' \
  "$(docker compose --env-file .env.production -f docker-compose.prod.yml ps -q redis)"
```

Обе команды должны выводить `{}` или `null`. Только `web` должен публиковать `127.0.0.1:8010`. В некоторых версиях Compose команда `port` выводит `:0` для неопубликованного порта, поэтому проверка выполняется через `docker inspect`.

## Перед открытием продаж

- `check --deploy`, migrations, `/health/`, Redis и Celery проходят.
- Внешний URL открывает `/admin/login/`; `/accounts/admin/login/` только перенаправляет на него.
- SMTP и SMS подтверждены реальными сообщениями.
- Finik status endpoint и webhook проверены реальными beta/production сценариями.
- `python manage.py verify_media_references` проходит без missing-файлов.
- Backup скопирован за пределы Hetzner, restore проверен на отдельном стенде.
- Sentry/мониторинг и юридические тексты настроены.

Операции backup/restore и платёжные инциденты описаны в `OPERATIONS.md`.
