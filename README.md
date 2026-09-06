# Элит Маркет

Полноценный интернет-магазин на Django 5.2: каталог, адаптивные карточки и галерея товаров, несколько фотографий и видео, диапазоны оптовых цен, корзина, оформление и резервирование товара, личный кабинет, история заказов, отмена с причиной, отзывы после покупки, администрирование и интеграция оплаты Finik.

## Стек

- Python 3.12, Django 5.2, Django ORM
- SQLite для локальной разработки; PostgreSQL через `DATABASE_URL` для production
- Vanilla HTML/CSS/JavaScript без внешних CDN
- Celery и Redis для фоновых задач и освобождения просроченного резерва
- Pillow и Django storage API для изображений; локальное или S3-совместимое media-хранилище
- Finik QR с RSA-SHA256 подписью запросов и webhook
- Gunicorn и WhiteNoise для production-запуска и статических файлов
- Sentry подключается опционально через переменную окружения

## Архитектура

- `accounts` — пользователь, клиентский OTP-вход, администраторы, профили и ограничения попыток.
- `shop` — каталог, цены, корзина, адреса, заказы, позиции заказа, отзывы и жизненный цикл резерва.
- `payment` — создание Finik-платежа, тестовая оплата, проверка подписи webhook и журнал событий.
- `project` — настройки, маршруты, Celery, health-check, раздача локальных media и security headers.
- `templates`, `static`, `media` — русский адаптивный интерфейс и загруженные файлы.

## База данных

Основные связи:

- `User` → один `ClientProfile` или `AdminProfile`.
- `Category` → много `Product`.
- `Product` → много `ProductImage` и `WholesalePrice`.
- `User` → одна `Cart`; `Cart` → много `CartItem`.
- `User` → много `Address` и `Order`.
- `Order` → много `OrderItem` и `PaymentEvent`.
- `OrderItem` → не более одного `Review`; отзыв разрешён только после статуса заказа «Доставлен».

Цена каждой позиции повторно вычисляется внутри транзакции с блокировкой товара. Остаток уменьшается при создании заказа и возвращается один раз при отмене или истечении срока оплаты. Цена и название сохраняются в `OrderItem`, поэтому история заказа не меняется после редактирования товара.

## Локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --require-hashes -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py loaddata shop/fixtures/sample_catalog.json
python manage.py runserver 0.0.0.0:8000
```

Адреса:

- магазин: `http://127.0.0.1:8000/`
- админка: `http://127.0.0.1:8000/admin/`
- проверка сервиса: `http://127.0.0.1:8000/health/`
- liveness probe: `http://127.0.0.1:8000/health/live/`
- доступ из локальной сети: `http://IP-КОМПЬЮТЕРА:8000/`

Для доступа по локальной сети добавьте IP компьютера в `ALLOWED_HOSTS` и разрешите входящие подключения к порту 8000 в брандмауэре.

## Пользователи и пароли

В репозитории нет общего или скрытого пароля.

### Администратор

```powershell
python manage.py createsuperuser
```

Команда запросит email и пароль. Пароль хранится только в виде стойкого Django-хеша. Публичная регистрация администратора закрыта; нового администратора может создать только суперпользователь.

### Тестовый клиент

```powershell
python manage.py shell -c "from accounts.models import User; User.objects.get_or_create(phone_number='+996700111222', defaults={'is_client': True, 'is_active': True})"
```

При `SMS_PROVIDER=console` откройте страницу входа, введите `+996700111222` и возьмите одноразовый код из терминала сервера. OTP хранится в базе только как хеш, действует ограниченное время и имеет лимиты повторной отправки и попыток.

## Админская часть

Через `/admin/` доступны:

- категории, товары, остатки, основное и дополнительные изображения, видео;
- диапазоны оптовых цен;
- заказы, позиции, адреса, статусы оплаты и причины отмены;
- модерация отзывов;
- пользователи и профили;
- журнал входящих платежных событий.

Для товара загрузите основное фото в inline-блоке «Изображения товара». Поле `Product.image` сохранено для совместимости со старыми данными. На витрине приоритет имеет изображение с отметкой «Основное», затем остальные по полю «Порядок».

## Фотографии и видео

- Локально файлы хранятся в `media/products/` и `media/products/gallery/`.
- На `DEBUG=True` их обслуживает Django.
- `SERVE_MEDIA_FILES=True` допустим только для локальной разработки; в production media отдаёт Nginx или S3.
- Для масштабируемого production включите `USE_S3=True` и заполните S3-переменные из `.env.example`.
- Поддерживаются JPG, PNG, WebP до 10 МБ; видео MP4, WebM, MOV до 100 МБ.

`MEDIA_ROOT` — физическая папка, `MEDIA_URL` — публичный URL. Если запись в БД есть, а файла в storage нет, интерфейс показывает заглушку, а не сломанную картинку.

## Оптовые цены

Для каждого товара диапазоны задаются через `WholesalePrice`: количество, после которого включается опт, и цена за штуку. Значение `9` означает розничную цену до 9 включительно и оптовую цену с 10 штук. Калькулятор обновляет цену и сумму без перезагрузки, а сервер повторно проверяет диапазон при оформлении заказа.

## Заказы

После оформления заказ получает уникальный номер, срок оплаты и статус «Ожидает». Неоплаченные заказы видны в профиле и могут быть отменены с обязательной причиной. Команда обслуживания:

```powershell
python manage.py cancel_expired_orders
```

В production эту же операцию выполняет Celery Beat по расписанию `ORDER_EXPIRY_CHECK_SECONDS`.

## Finik

Локально безопасно используется `FINIK_USE_STUB=True`. Тестовая страница платежа доступна только владельцу заказа.

Для боевого режима нужны выданные Finik значения:

```env
FINIK_USE_STUB=False
FINIK_API_URL=https://api.acquiring.averspay.kg/v1/payment
FINIK_API_KEY=...
FINIK_ACCOUNT_ID=...
FINIK_DISPLAY_NAME=Elit Market
FINIK_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
FINIK_WEBHOOK_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
```

Webhook: `POST /webhook/finik/`. Обработчик проверяет timestamp, RSA-подпись и сумму, блокирует заказ транзакцией и обеспечивает идемпотентность через уникальный `provider_event_id`.

## Celery

Для локальной разработки задачи выполняются сразу (`CELERY_TASK_ALWAYS_EAGER=True`). Для production:

```env
CELERY_TASK_ALWAYS_EAGER=False
CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...
CACHE_URL=redis://...
```

Процессы:

```bash
celery -A project worker -l info
celery -A project beat -l info
```

## Проверка качества

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`check --deploy` нужно запускать с теми же production-переменными, которые будут установлены на сервере.

## Production checklist

Перед приёмом реальных заказов обязательно:

1. Установить `DEBUG=False` и случайный `SECRET_KEY`.
2. Указать точные `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` и `SITE_URL`.
3. Подключить PostgreSQL и настроить резервное копирование.
4. Подключить S3-совместимое media-хранилище либо persistent disk для одного экземпляра.
5. Подключить Redis, Celery worker и Celery Beat.
6. Настроить реальный SMS-провайдер и SMTP; не использовать console backend.
7. Внести реальные ключи Finik и зарегистрировать HTTPS webhook.
8. Настроить Sentry, мониторинг `/health/`, домен и TLS.
9. Выполнить миграции, `collectstatic`, тестовую покупку, отмену и возврат склада.
10. Создать суперпользователя и заменить демонстрационные контакты магазина.

Код поддерживает все перечисленные production-компоненты, но сторонние аккаунты, домен, SMS/SMTP, Finik, PostgreSQL, Redis и S3 должны быть предоставлены владельцем проекта.

## Документация эксплуатации

- `DEPLOY.md` — второй проект на Hetzner, Nginx, TLS, запуск и откат.
- `DEPLOY_RENDER.md` — полноценный Render Blueprint и временный адрес без домена.
- `OPERATIONS.md` — backup/restore, мониторинг и действия при инцидентах.
- `SECURITY.md` — границы доверия, secrets и порядок сообщения об уязвимости.
