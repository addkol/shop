# Деплой проекта в интернет через Render

Проект уже подготовлен для production-запуска: `gunicorn`, `collectstatic`, миграции, HTTPS-настройки, SQLite на persistent disk и media-файлы на persistent disk.

## 1. Загрузите проект в GitHub

Создайте пустой репозиторий на GitHub и выполните в папке проекта:

```powershell
git add .
git commit -m "Prepare Django shop for deployment"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

## 2. Создайте сервис на Render

1. Откройте Render.
2. Создайте новый `Blueprint`.
3. Подключите GitHub-репозиторий проекта.
4. Render прочитает `render.yaml` и создаст web-service с persistent disk.

## 3. После первого деплоя

В Render замените переменную:

```env
SITE_URL=https://ВАШ-СЕРВИС.onrender.com
```

Если подключаете свой домен, добавьте:

```env
ALLOWED_HOSTS=ваш-домен.com,www.ваш-домен.com,.onrender.com
CSRF_TRUSTED_ORIGINS=https://ваш-домен.com,https://www.ваш-домен.com,https://*.onrender.com
SITE_URL=https://ваш-домен.com
```

## 4. Важные production-переменные

Для настоящих платежей и SMS замените заглушки:

```env
FINIK_USE_STUB=False
FINIK_API_KEY=...
FINIK_SECRET=...
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_FROM_NUMBER=...
```

## 5. Проверка

После деплоя откройте:

```text
https://ВАШ-СЕРВИС.onrender.com/
https://ВАШ-СЕРВИС.onrender.com/admin/
```

Для создания администратора выполните команду в Shell сервиса Render:

```bash
python manage.py createsuperuser
```
