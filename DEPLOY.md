# 🌍 Гайд по деплою - Онлайн Магазин

Полная инструкция для развертывания проекта на боевом сервере.

## Выбор сервера

### Рекомендуемые варианты

| Провайдер | Цена | Простота | Возможности |
|-----------|------|----------|------------|
| **Render.com** | Бесплатно - $7/мес | ⭐⭐⭐⭐⭐ | PostgreSQL, Redis, Python |
| **Railway.app** | $5/мес | ⭐⭐⭐⭐⭐ | Отличная интеграция с Git |
| **Heroku** | Платно ($7+) | ⭐⭐⭐⭐ | Стабильный, много документации |
| **DigitalOcean** | $4/мес | ⭐⭐⭐ | Полный контроль, VPS |
| **AWS** | Зависит | ⭐⭐ | Сложно, но мощно |
| **PythonAnywhere** | $5/мес | ⭐⭐⭐⭐ | Просто, для Python |

**Рекомендация:** Начните с **Render.com** или **Railway.app** - они бесплатные для тестирования.

---

## 📋 Подготовка кода

### 1. Обновите requirements.txt

Убедитесь, что туда добавлены необходимые пакеты для production:

```
gunicorn==23.0.0
whitenoise==6.12.0
psycopg2-binary==2.9.12
dj-database-url==2.1.0
```

Запустите:
```powershell
pip freeze > requirements.txt
```

### 2. Создайте Procfile (для Heroku/Render/Railway)

**Procfile** (без расширения):
```
web: gunicorn project.wsgi
release: python manage.py migrate
```

### 3. Создайте runtime.txt (версия Python)

```
python-3.11.7
```

### 4. Создайте .gitignore

```
.venv/
*.pyc
__pycache__/
.env
db.sqlite3
*.log
/media/
/static/
.DS_Store
```

### 5. Обновите settings.py

```python
# production/settings.py

DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = [
    'yourdomain.com',
    'www.yourdomain.com',
    'your-app.render.com',  # Render
    # 'your-app.up.railway.app',  # Railway
]

# PostgreSQL для production
if config('USE_POSTGRES', default=False, cast=bool):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }

# Security
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_SECURITY_POLICY = {
    'default-src': ("'self'",),
    'style-src': ("'self'", "'unsafe-inline'"),
    'script-src': ("'self'",),
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
WHITENOISE_AUTOREFRESH = True

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

---

## 🚀 Деплой на Render.com

### Шаг 1: Подготовка GitHub

```powershell
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/OnlineShop.git
git push -u origin main
```

### Шаг 2: Создание на Render

1. Зайдите на [render.com](https://render.com)
2. Нажмите "New" → "Web Service"
3. Выберите GitHub репозиторий
4. Заполните поля:

```
Name: onlineshop
Environment: Python
Build Command: pip install -r requirements.txt
Start Command: gunicorn project.wsgi
```

### Шаг 3: Environment Variables

Добавьте переменные окружения:

```
DEBUG=False
SECRET_KEY=<generate-new-secret>
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
LANGUAGE_CODE=ru
TIME_ZONE=Asia/Bishkek

DB_ENGINE=postgresql
DB_NAME=onlineshop
DB_USER=postgres
DB_PASSWORD=<strong-password>
DB_HOST=<your-postgres-host>
DB_PORT=5432

USE_POSTGRES=True

SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=<your-sid>
TWILIO_AUTH_TOKEN=<your-token>
TWILIO_FROM_NUMBER=+<your-number>

FINIK_USE_STUB=False
FINIK_API_KEY=<your-api-key>
FINIK_API_URL=https://api.finik.kg/v1/payments

CELERY_BROKER_URL=redis://...
CELERY_RESULT_BACKEND=redis://...
```

### Шаг 4: PostgreSQL

1. Создайте PostgreSQL базу на Render
2. Скопируйте connection string
3. Используйте его для `DB_*` переменных

### Шаг 5: Миграции

После первого развертывания запустите в консоли сервера:

```powershell
render exec -n onlineshop "python manage.py migrate"
render exec -n onlineshop "python manage.py createsuperuser"
render exec -n onlineshop "python manage.py loaddata shop/fixtures/sample_catalog.json"
```

---

## 🚂 Деплой на Railway.app

### Шаг 1: Подготовка

```powershell
npm install -g @railway/cli
railway login
railway init
```

### Шаг 2: Конфигурация

**railway.json:**
```json
{
  "build": {
    "builder": "heroku.buildpacks"
  },
  "deploy": {
    "startCommand": "gunicorn project.wsgi",
    "restartPolicyMaxRetries": 5
  }
}
```

### Шаг 3: Переменные

```powershell
railway variables set DEBUG=False
railway variables set SECRET_KEY=<generate-new>
railway variables set DATABASE_URL=postgresql://...
```

### Шаг 4: Деплой

```powershell
git add .
git commit -m "Ready for deployment"
railway up
```

---

## 🐳 Деплой в Docker

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей ОС
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода
COPY . .

# Создание пользователя
RUN useradd -m -u 1000 django && chown -R django:django /app
USER django

# Команды запуска
RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "project.wsgi", "--bind", "0.0.0.0:8000"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      DEBUG: "False"
      DB_ENGINE: postgresql
      DB_HOST: db
      DB_NAME: onlineshop
      DB_USER: postgres
      DB_PASSWORD: password
    depends_on:
      - db
      - redis
    volumes:
      - ./media:/app/media
      - ./staticfiles:/app/staticfiles

  db:
    image: postgres:15
    environment:
      POSTGRES_DB: onlineshop
      POSTGRES_PASSWORD: password
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery:
    build: .
    command: celery -A project worker -l info
    environment:
      DEBUG: "False"
      DB_HOST: db
      CELERY_BROKER_URL: redis://redis:6379/0
    depends_on:
      - db
      - redis

volumes:
  postgres_data:
```

Запуск:
```powershell
docker-compose up -d
```

---

## 🔒 Безопасность для Production

### 1. SECRET_KEY

Генерируйте новый ключ:

```python
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
```

### 2. SSL/TLS

Большинство сервисов автоматически выдают SSL. Убедитесь:

```python
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000  # 1 год
```

### 3. CORS для API

```python
CORS_ALLOWED_ORIGINS = [
    "https://yourdomain.com",
    "https://www.yourdomain.com",
]
```

### 4. Database Backups

Для PostgreSQL:
```bash
pg_dump database_url > backup.sql
psql database_url < backup.sql
```

---

## 📊 Мониторинг

### Logs

На Render:
```powershell
render logs onlineshop
```

На Railway:
```powershell
railway logs
```

### Error Tracking

Добавьте Sentry:

```powershell
pip install sentry-sdk
```

В settings.py:
```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="https://<key>@<id>.ingest.sentry.io/<project>",
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
)
```

---

## 💳 Настройка платежей

### Finik в Production

1. Получите API ключи
2. Установите `FINIK_USE_STUB=False`
3. Добавьте URL вебхука:

```
https://yourdomain.com/webhook/finik/
```

### Twilio для SMS

1. Создайте аккаунт на [twilio.com](https://twilio.com)
2. Получите credentials
3. Установите в `.env`:

```
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=+1...
```

---

## 📈 Оптимизация

### Кэширование

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### CDN для медиафайлов

Используйте CloudFlare или AWS CloudFront для быстрой доставки изображений.

### Database Indexing

```python
class Product(models.Model):
    name = models.CharField(max_length=200, db_index=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        db_index=True
    )
```

---

## 🆘 Troubleshooting

### ❌ "ModuleNotFoundError"
```powershell
pip install -r requirements.txt
```

### ❌ "ProgrammingError: relation doesn't exist"
```powershell
python manage.py migrate
```

### ❌ "Permission denied" для media
```bash
chmod -R 755 media/
chown -R www-data:www-data media/
```

### ❌ "Connection refused" для Redis
Убедитесь, что Redis запущен на сервере.

---

## 📚 Дополнительно

- [Django Production Checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/)
- [Gunicorn Configuration](https://docs.gunicorn.org/en/stable/configure.html)
- [PostgreSQL on Production](https://www.postgresql.org/docs/current/admin.html)
- [Celery Best Practices](https://docs.celeryproject.io/en/stable/getting-started/best-practices.html)

---

**Успешного деплоя!** 🎉
