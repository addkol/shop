# Production-деплой на Render

Dashboard и SMS-исключение FIXED_OTP_CODE описаны в [DASHBOARD.md](DASHBOARD.md).
Если настройку используют временно, её значение должно совпадать в web/worker/beat.
Без неё снова обязательны реальные SMS credentials; остальные production checks не отключаются.

`render.yaml` описывает полноценную схему: Django web, PostgreSQL, Render Key Value/Redis, Celery worker, Celery Beat и S3-совместимое media-хранилище. SQLite и локальные загруженные файлы в production Blueprint не используются.

Blueprint намеренно использует платные persistent-компоненты: PostgreSQL `1c-2g`/20 ГБ, Key Value `256mb`, web/worker `1c-2g` и Beat `0.5c-512mb`. Перед созданием проверьте текущую стоимость в Render Dashboard; это production-схема, а не бесплатный MVP.

## Адрес без собственного домена

Render автоматически выдаёт HTTPS-адрес вида `https://onlineshop.onrender.com`. Укажите его одинаково:

```env
ALLOWED_HOSTS=onlineshop.onrender.com
CSRF_TRUSTED_ORIGINS=https://onlineshop.onrender.com
SITE_URL=https://onlineshop.onrender.com
```

Позже собственный домен можно подключить без изменения архитектуры. После подключения обновите все три переменные и Finik webhook.

## Создание Blueprint

1. Отправьте актуальный код в приватный GitHub-репозиторий.
2. В Render выберите **New → Blueprint** и подключите репозиторий.
3. Render прочитает `render.yaml` и запросит значения с `sync: false`.
4. Заполните S3, SMTP, Twilio, Finik и Sentry secrets.
5. Создайте Blueprint и дождитесь успешного pre-deploy шага.

Web service не запустится с опасной production-конфигурацией: `preDeployCommand` и `startCommand` выполняют `python manage.py check --deploy`, а затем миграции/запуск Gunicorn.

## Обязательные secrets

- `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`.
- `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, endpoint/region поставщика.
- `DEFAULT_FROM_EMAIL`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`.
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`.
- `FINIK_API_KEY`, `FINIK_ACCOUNT_ID`, `FINIK_PRIVATE_KEY`, `FINIK_WEBHOOK_PUBLIC_KEY`.
- `FINIK_STATUS_API_URL` и reconciliation-параметры worker.
- `SENTRY_DSN` рекомендуется для централизованных ошибок.

Render генерирует `SECRET_KEY`, создаёт PostgreSQL/Key Value и передаёт их connection strings сервисам автоматически.

## Media/S3

Веб-сервис и worker имеют эфемерную файловую систему, поэтому загруженные изображения и видео должны идти в S3-compatible storage. Бакет должен быть закрыт на запись извне; загрузку выполняет только приложение. Если файлы публичны через CDN/custom domain, используйте `S3_QUERYSTRING_AUTH=False`. Если media приватные, потребуется отдельная модель выдачи подписанных URL.

Hetzner-команда `import_initial_data --restore-media` намеренно работает только с локальным `MEDIA_ROOT` и не загружает архив в S3. Для первого переноса на Render сначала используйте `export_initial_data` для fixture/manifest, затем отдельным контролируемым шагом загрузите media в S3 с сохранением относительных ключей и SHA-256, после чего загрузите fixture в пустой PostgreSQL и выполните `verify_media_references`. Не запускайте Hetzner import script в Render Shell.

## Администратор

После первого успешного deploy откройте Render Shell у web service:

```bash
python manage.py createsuperuser
```

Готовых production-логинов и паролей в проекте нет.

## Проверка

```bash
python manage.py check --deploy
python manage.py showmigrations --plan
python manage.py purge_payment_payloads --dry-run
```

Через браузер проверьте:

- `/health/`, `/admin/`, главную и страницу товара;
- загрузку нескольких фотографий и видео;
- OTP-вход, корзину, оптовый порог, checkout и профиль;
- создание/отмену неоплаченного заказа;
- production-платёж Finik и повторную доставку webhook.
- reconciliation `PENDING → SUCCEEDED/FAILED`, timeout и позднюю оплату.

## Обновления и rollback

Каждый push запускает новый build, затем pre-deploy migration. Перед изменениями схемы создавайте backup PostgreSQL/S3. Render rollback возвращает код/образ, но не откатывает базу автоматически; миграции проектируйте обратно совместимыми и сначала проверяйте на staging.
