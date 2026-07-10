# Онлайн Магазин

Django 5 интернет-магазин с авторизацией по номеру телефона для клиентов, подтверждением email для администраторов, корзиной в сессии и БД, оформлением заказа, интеграцией с платежной системой Finik, генерацией QR-кодов, webhook'ами, настройкой Celery и Bootstrap шаблонами.

**Интерфейс полностью переведен на русский язык** 🇷🇺

## Технологический стек

- Django 5, Django REST Framework, готовые настройки для PostgreSQL
- Кастомная модель пользователя с клиентами по телефону и администраторами по email
- Celery + Redis для фоновых задач отправки SMS и email
- Интеграция с платежной системой Finik (режим заглушки для разработки)
- Bootstrap 5 шаблоны и HTMX

## Полная инструкция по запуску

### Шаг 1: Создание и активация виртуального окружения

```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
.venv\Scripts\activate.bat
```

**Mac/Linux:**
```bash
source .venv/bin/activate
```

### Шаг 2: Установка зависимостей

```powershell
pip install -r requirements.txt
```

Это установит:
- Django 5 и DRF
- PostgreSQL драйвер (psycopg2)
- Celery + Redis
- Twilio для SMS
- QRCode для генерации QR-кодов
- Bootstrap и HTMX

### Шаг 3: Создание файла окружения

```powershell
copy .env.example .env
```

Отредактируйте `.env` файл при необходимости. Основные переменные:

```env
DEBUG=True
SECRET_KEY=your-secret-key-here
LANGUAGE_CODE=ru
TIME_ZONE=Asia/Bishkek

# Для SMS (Twilio)
SMS_PROVIDER=console
TWILIO_ACCOUNT_SID=your-sid
TWILIO_AUTH_TOKEN=your-token
TWILIO_FROM_NUMBER=+1234567890

# Для платежей (Finik)
FINIK_USE_STUB=True
FINIK_API_KEY=your-api-key
```

### Шаг 4: Запуск миграций

```powershell
python manage.py makemigrations
python manage.py migrate
```

### Шаг 5: Загрузка тестовых данных

```powershell
python manage.py loaddata shop/fixtures/sample_catalog.json
```

Это добавит пример товаров и категорий для тестирования.

### Шаг 6: Создание администратора (опционально)

```powershell
python manage.py createsuperuser
```

Следуйте подсказкам для создания учетной записи администратора.

### Шаг 7: Запуск development сервера

```powershell
python manage.py runserver
```

**Сервер откроется по адресу:** `http://127.0.0.1:8000/`

---

## Доступные адреса

- **Главная страница:** `http://127.0.0.1:8000/` - Каталог товаров
- **Корзина:** `http://127.0.0.1:8000/cart/` - Ваша корзина
- **Профиль:** `http://127.0.0.1:8000/accounts/profile/` - Личный кабинет (требует авторизации)
- **Вход клиента:** `http://127.0.0.1:8000/accounts/login/` - Авторизация по телефону
- **Регистрация:** `http://127.0.0.1:8000/accounts/register/` - Новый аккаунт
- **Админ-панель:** `http://127.0.0.1:8000/admin/` - Управление (требует superuser)

---

## Celery и фоновые задачи

По умолчанию все задачи выполняются синхронно благодаря `CELERY_TASK_ALWAYS_EAGER=True`. Это удобно для разработки.

### Для использования асинхронных задач в разработке:

1. **Установите и запустите Redis:**

```powershell
# Windows - через WSL или Docker
wsl redis-server

# Или используйте Docker:
docker run -d -p 6379:6379 redis:latest
```

2. **Отключите синхронный режим в `.env`:**

```env
CELERY_TASK_ALWAYS_EAGER=False
```

3. **Запустите Celery worker (в отдельном терминале):**

```powershell
celery -A project worker -l info
```

---

## Платежи и Finik

### Режим разработки (Stub Mode)

По умолчанию используется режим заглушки `FINIK_USE_STUB=True`. При оформлении заказа:
- Создается фальшивый платежный ID
- Генерируется QR-код
- Нет необходимости в реальном подключении к Finik

### Для боевого режима (Production):

В `.env` установите:

```env
FINIK_USE_STUB=False
FINIK_API_URL=https://api.finik.kg/v1/payments
FINIK_API_KEY=your-api-key
FINIK_SECRET=your-secret
```

И раскройте webhook:

```
POST /webhook/finik/
```

Webhook принимает: `payment_id` и `status` (success/failed)

---

## Структура проекта

```
OnlineShop/
├── project/              # Основные настройки Django
│   ├── settings.py       # Конфигурация (LANGUAGE_CODE=ru)
│   ├── urls.py
│   ├── celery.py         # Настройка Celery
│   └── wsgi.py
│
├── shop/                 # Приложение магазина
│   ├── models.py         # Модели (Товар, Категория, Заказ, Корзина)
│   ├── views.py          # Представления
│   ├── forms.py          # Формы оформления
│   ├── admin.py          # Админ-панель
│   └── fixtures/
│       └── sample_catalog.json  # Тестовые данные
│
├── accounts/             # Приложение учетных записей
│   ├── models.py         # Кастомная модель User
│   ├── forms.py          # Формы регистрации/входа
│   ├── auth_backends.py  # Кастомная аутентификация
│   └── tasks.py          # Celery задачи (SMS)
│
├── payment/              # Приложение платежей
│   ├── views.py          # Webhook обработчик
│   └── services.py       # Интеграция Finik
│
├── templates/            # HTML шаблоны (все на русском)
│   ├── base.html         # Основной шаблон
│   ├── index.html        # Каталог
│   ├── cart.html         # Корзина
│   ├── checkout.html     # Оформление
│   ├── profile.html      # Профиль
│   ├── order_success.html # Успешный заказ
│   └── accounts/
│       ├── login.html
│       ├── register.html
│       └── verify.html
│
├── static/               # CSS, JS, изображения
└── media/                # Загруженные файлы (товары)
```

---

## Функции по ролям

### Для клиентов

✅ Регистрация по номеру телефона +996  
✅ Верификация SMS кодом  
✅ Просмотр каталога товаров с фильтром по категориям  
✅ Добавление товаров в корзину  
✅ Оформление заказа с адресом доставки  
✅ Выбор способа оплаты (QR код, карта, ссылка)  
✅ История заказов в профиле  
✅ Сохранение адресов доставки  

### Для администраторов

✅ Добавление и редактирование товаров  
✅ Управление категориями  
✅ Просмотр и изменение статуса заказов  
✅ Отслеживание платежей  
✅ Управление пользователями  

---

## Переменные окружения (.env)

| Переменная | По умолчанию | Описание |
|-----------|--------|---------|
| `DEBUG` | True | Режим отладки |
| `SECRET_KEY` | change-me-in-production | Секретный ключ Django |
| `LANGUAGE_CODE` | ru | Язык интерфейса (русский) |
| `TIME_ZONE` | Asia/Bishkek | Временная зона |
| `DB_ENGINE` | sqlite3 | Тип БД (sqlite3 или postgres) |
| `SMS_PROVIDER` | console | Провайдер SMS (console, twilio) |
| `CELERY_TASK_ALWAYS_EAGER` | True | Синхронное выполнение задач |
| `FINIK_USE_STUB` | True | Режим тестирования платежей |

---

## Типичные команды

```powershell
# Активация окружения
.venv\Scripts\activate

# Миграции
python manage.py makemigrations
python manage.py migrate

# Создание суперпользователя
python manage.py createsuperuser

# Загрузка тестовых данных
python manage.py loaddata shop/fixtures/sample_catalog.json

# Запуск сервера
python manage.py runserver

# Запуск Celery worker
celery -A project worker -l info

# Очистка кэша
python manage.py clearcache

# Сброс БД (осторожно!)
python manage.py flush
```

---

## Возможные проблемы и решения

### ❌ "Модуль 'redis' не найден"
**Решение:** `pip install redis`

### ❌ "No module named 'psycopg2'"
**Решение:** `pip install psycopg2-binary`

### ❌ Ошибка миграций
**Решение:**
```powershell
python manage.py makemigrations --empty accounts --name fix_models
python manage.py migrate
```

### ❌ SMS не отправляются в режиме разработки
**Это нормально!** В режиме `SMS_PROVIDER=console` SMS печатаются в консоль. Используйте код из консоли для верификации.

### ❌ Порт 8000 занят
**Решение:** `python manage.py runserver 8001`

---

## Требования

- Python 3.10+
- Django 5.0+
- PostgreSQL (или SQLite для разработки)
- Redis (опционально, для Celery)

---

## Деплой

### На Heroku:
```powershell
heroku create your-app-name
heroku config:set DEBUG=False
git push heroku main
```

### На PythonAnywhere:
1. Загрузите код на сервер
2. Создайте виртуальное окружение
3. Установите требования
4. Настройте WSGI
5. Перезагрузите приложение

---

## Поддержка

По вопросам и ошибкам создавайте Issues в репозитории.

**Язык интерфейса:** Русский 🇷🇺  
**Последнее обновление:** 2026-07-08
