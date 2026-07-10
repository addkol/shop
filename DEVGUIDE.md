# 👨‍💻 Справка для разработчиков

Полное описание структуры и архитектуры проекта для быстрого погружения.

## 📦 Структура проекта

```
OnlineShop/
├── project/                  # Основные настройки Django
│   ├── __init__.py
│   ├── settings.py          # Конфигурация (DATABASE, INSTALLED_APPS, etc.)
│   ├── urls.py              # Главные роуты приложения
│   ├── asgi.py              # ASGI для Daphne/Uvicorn
│   ├── wsgi.py              # WSGI для Gunicorn
│   └── celery.py            # Конфигурация Celery
│
├── shop/                     # E-commerce приложение
│   ├── __init__.py
│   ├── models.py            # Models: Product, Category, Cart, Order
│   ├── views.py             # Views: список, деталь, оформление
│   ├── forms.py             # Forms: CheckoutForm, AddressForm
│   ├── urls.py              # Роуты shop приложения
│   ├── admin.py             # Админ-панель
│   ├── apps.py              # Конфигурация приложения
│   ├── cart.py              # Логика корзины (сессия + БД)
│   ├── context_processors.py # Контекстные процессоры
│   ├── tests.py             # Тесты
│   ├── fixtures/
│   │   └── sample_catalog.json  # Тестовые товары и категории
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── 0001_initial.py   # Начальная миграция
│   │   └── 0002_alter...     # Миграция meta options (русский язык)
│   └── templates/
│       └── (используются глобальные templates/)
│
├── accounts/                # Приложение учетных записей
│   ├── __init__.py
│   ├── models.py            # Custom User, ClientProfile, AdminProfile
│   ├── forms.py             # RegistrationForm, LoginForm, VerificationForm
│   ├── views.py             # Views: регистрация, вход, верификация
│   ├── urls.py              # Роуты accounts
│   ├── admin.py             # Админ-панель
│   ├── auth_backends.py     # Кастомная аутентификация (по телефону/email)
│   ├── managers.py          # Custom User Manager
│   ├── signals.py           # Сигналы Django (создание профилей)
│   ├── tasks.py             # Celery: отправка SMS
│   ├── tests.py             # Тесты
│   ├── migrations/
│   │   ├── __init__.py
│   │   ├── 0001_initial.py
│   │   └── 0002_alter...     # Миграция meta options
│   └── templates/accounts/
│       ├── login.html
│       ├── register.html
│       ├── verify.html
│       ├── admin_login.html
│       └── admin_register.html
│
├── payment/                 # Приложение платежей
│   ├── __init__.py
│   ├── views.py             # Webhook обработчик (/webhook/finik/)
│   ├── services.py          # FinikService для интеграции
│   ├── urls.py              # Роуты payment
│   ├── apps.py
│   ├── migrations/
│   │   └── __init__.py
│   └── tests.py
│
├── templates/               # HTML шаблоны (все на русском)
│   ├── base.html            # Основной шаблон с навигацией
│   ├── index.html           # Главная страница, каталог товаров
│   ├── product_detail.html  # Страница товара
│   ├── cart.html            # Корзина
│   ├── checkout.html        # Оформление заказа
│   ├── profile.html         # Профиль пользователя
│   ├── order_success.html   # Подтверждение заказа
│   └── accounts/            # Шаблоны accounts
│       ├── login.html
│       ├── register.html
│       ├── verify.html
│       ├── admin_login.html
│       └── admin_register.html
│
├── static/                  # Статические файлы
│   ├── css/
│   │   └── style.css        # Bootstrap + кастомные стили
│   ├── js/
│   └── images/
│
├── media/                   # Пользовательские загруженные файлы
│   ├── products/            # Изображения товаров
│   └── qrcodes/             # QR-коды платежей
│
├── db.sqlite3               # SQLite база (development)
├── manage.py                # Django управления
├── requirements.txt         # Python зависимости
├── .env.example             # Пример переменных окружения
├── README.md                # Полная документация (русский)
├── QUICKSTART.md            # Быстрый старт (русский)
├── DEPLOY.md                # Гайд по деплою (русский)
├── API.md                   # API документация (русский)
└── DEVGUIDE.md              # Эта справка (русский)
```

---

## 🏗️ Архитектура

### Слои приложения

```
┌─────────────────────────────────┐
│     HTML Templates + JS         │  ← Presentation Layer
├─────────────────────────────────┤
│   Django Views + ViewSets       │  ← Application Layer
│   (shop.views, accounts.views)  │
├─────────────────────────────────┤
│   Forms + Serializers           │  ← Data Validation Layer
│   (shop.forms, REST framework)  │
├─────────────────────────────────┤
│   Models + Managers             │  ← Domain Layer
│   (shop.models, accounts.models)│
├─────────────────────────────────┤
│   Services + Utilities          │  ← Business Logic Layer
│   (payment.services, cart.py)   │
├─────────────────────────────────┤
│   Celery Tasks (async jobs)     │  ← Background Tasks
├─────────────────────────────────┤
│   PostgreSQL / SQLite           │  ← Persistence Layer
└─────────────────────────────────┘
```

---

## 📊 Модели данных

### shop.models

```python
Category
├── name: str
├── description: text
└── products: ManyToMany

Product
├── category: ForeignKey → Category
├── name: str
├── description: text
├── price: decimal
├── stock: int
├── image: ImageField
└── created_at: datetime

Cart
├── user: OneToOneField → User
├── created_at: datetime
├── updated_at: datetime
└── items: Reverse(CartItem)

CartItem
├── cart: ForeignKey → Cart
├── product: ForeignKey → Product
├── quantity: int
└── added_at: datetime

Order
├── user: ForeignKey → User
├── order_number: str (unique)
├── status: choice (pending, processing, shipped, delivered, cancelled)
├── payment_status: choice (pending, paid, refunded)
├── payment_method: choice (qr_code, card, link)
├── total_amount: decimal
├── address: ForeignKey → Address
├── payment_id: str
├── qr_code: ImageField
├── created_at: datetime
└── items: Reverse(OrderItem)

OrderItem
├── order: ForeignKey → Order
├── product: ForeignKey → Product
├── quantity: int
└── price_at_purchase: decimal

Address
├── user: ForeignKey → User
├── country: str
├── city: str
├── street: str
├── building: str
├── apartment: str
├── postal_code: str
├── is_default: bool
└── created_at: datetime
```

### accounts.models

```python
User (кастомный AUTH_USER_MODEL)
├── phone: str (unique для клиентов)
├── email: str (unique для админов)
├── first_name: str
├── last_name: str
├── patronymic: str
├── is_verified: bool
├── verification_code: str
├── last_login: datetime
├── user_type: choice (client, admin)
├── is_active: bool
├── is_staff: bool
├── is_superuser: bool
└── created_at: datetime

ClientProfile
├── user: OneToOneField → User
└── phone: str (денормализованное для удобства)

AdminProfile
├── user: OneToOneField → User
└── email: str (денормализованное)
```

---

## 🔐 Аутентификация

### Процесс входа клиента (по телефону)

```
1. POST /accounts/register/
   ├── Проверка формата номера (+996...)
   ├── Создание/поиск User
   ├── Генерация 4-значного кода
   ├── Celery task: отправка SMS
   └── Return: sms_sent status

2. POST /accounts/verify/
   ├── Проверка кода верификации
   ├── Установка is_verified=True
   ├── Создание session/token
   └── Return: user object + session cookie
```

### Процесс входа администратора (по email)

```
1. POST /accounts/admin_login/
   ├── Проверка email + пароль
   └── Создание session

2. POST /accounts/admin_register/
   ├── Создание нового User (is_staff=True)
   └── Отправка письма подтверждения (Celery task)
```

### Кастомная аутентификация (auth_backends.py)

```python
PhoneBackend
├── Аутентифицирует по номеру телефона
└── Используется в LoginForm

EmailBackend
├── Аутентифицирует по email
└── Используется для админов
```

---

## 🛒 Логика корзины

### Файл: shop/cart.py

Двухуровневая система:

```python
1. Session Cart (гость)
   - Хранится в session['cart']
   - Структура: {product_id: quantity}
   - Теряется при закрытии браузера

2. Database Cart (авторизованный)
   - Привязана к User
   - OneToOne relation
   - Синхронизируется с сессией при логине
```

### Операции корзины

```python
add_to_cart(request, product_id, quantity)
├── Проверка наличия товара
├── Обновление сессии/БД
└── Return: updated cart

get_cart_total(cart)
├── Расчет итоговой суммы
└── Return: decimal

merge_session_to_db(request)
├── После логина: слияние сессии в БД
└── Удаление сессии
```

---

## 💳 Платежи - Finik

### Структура: payment/

**services.py - FinikService**

```python
class FinikService:
    create_payment(order_id, amount, description)
    ├── Stub mode: генерирует фальшивый платеж
    ├── Production: запрос к Finik API
    └── Return: payment_id + qr_code

    verify_webhook(payment_data)
    ├── Проверка подписи
    ├── Обновление статуса заказа
    └── Return: success/failed
```

**views.py - Webhook**

```
POST /webhook/finik/
├── Получение payment_id + status
├── Поиск заказа в БД
├── Обновление payment_status
└── Отправка SMS уведомления (Celery)
```

---

## 🔔 Фоновые задачи - Celery

### Файл: accounts/tasks.py

```python
@shared_task
send_verification_sms(phone, code)
├── SMS провайдер (console/twilio)
└── Логирование попытки

@shared_task
send_order_notification(order_id)
├── SMS: "Заказ принят"
└── SMS: "Заказ отправлен"
```

### Конфигурация: project/celery.py

```python
# Development: CELERY_TASK_ALWAYS_EAGER = True
# Production: CELERY_TASK_ALWAYS_EAGER = False
# Broker: redis://localhost:6379/0
# Backend: redis://localhost:6379/1
```

---

## 🎯 Основные потоки (Views)

### shop/views.py

```python
# Каталог товаров
index(request)
├── Получить все товары + категории
├── Пагинация 20 товаров на странице
└── Render: index.html

# Деталь товара
product_detail(request, product_id)
├── Получить товар + рецензии
├── Форма добавления в корзину
└── Render: product_detail.html

# Корзина
cart_view(request)
├── Получить корзину пользователя
├── Рассчитать сумму
└── Render: cart.html

# Оформление заказа
checkout(request)
├── Валидация адреса
├── Выбор способа оплаты
├── Создание заказа
├── Генерация QR (если QR платеж)
└── Redirect: order_success
```

### accounts/views.py

```python
# Регистрация клиента
register(request)
├── Валидация номера телефона
├── Создание User
├── Отправка SMS (task)
└── Redirect: verify

# Верификация
verify(request)
├── Проверка кода
├── Установка is_verified
├── Создание session
└── Redirect: profile

# Профиль
profile(request)
├── Проверка авторизации
├── История заказов
├── Сохраненные адреса
└── Render: profile.html
```

---

## 📝 Формы

### shop/forms.py

```python
CheckoutForm
├── Fields: address (выбор сохраненного или новый)
├── Fields: country, city, street, building, apartment
├── Fields: postal_code, payment_method
└── Validators: почтовый код, обязательные поля

AddressForm
├── Встроен в CheckoutForm
└── Может использоваться отдельно
```

### accounts/forms.py

```python
ClientRegistrationForm
├── phone (кастомное поле, валидация +996)
├── first_name, last_name, patronymic
└── Validators: формат номера

PhoneLoginForm
├── phone + verification_code
└── Двухступенчатая аутентификация

AdminRegistrationForm
├── email, password, password_confirm
└── Validators: сложность пароля
```

---

## 🎨 Шаблоны

### base.html

Главный шаблон со:
- Навигацией (Каталог, Корзина, Профиль)
- Логин/Регистрацией
- Боковой панелью (категории)
- Footer

### index.html

Каталог товаров:
- Grid товаров (3 колонки)
- Фильтр по категориям
- Пагинация
- Каждый товар: изображение, название, цена, кнопка "Добавить"

### cart.html

Корзина:
- Таблица товаров (название, количество, цена)
- Кнопки ±/удалить
- Итоговая сумма
- Кнопка "Оформить заказ"

### checkout.html

Оформление:
- Форма адреса (страна, город, улица, etc.)
- Выбор способа оплаты
- Сумма заказа
- Кнопка "Создать заказ"

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
python manage.py test

# Одно приложение
python manage.py test shop
python manage.py test accounts

# Один тест класс
python manage.py test accounts.tests.UserModelTest

# С verbose
python manage.py test -v 2
```

### Структура тестов

```
shop/tests.py
├── ProductModelTest
├── CartTest
└── CheckoutViewTest

accounts/tests.py
├── UserModelTest
├── AuthenticationTest
└── VerificationTest
```

---

## 🐛 Отладка

### Включение Debug mode

```python
# settings.py
DEBUG = True  # development
DEBUG = False  # production
```

### Логирование

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Отладочная информация")
logger.info("Информационное сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")
```

### Django Shell

```bash
python manage.py shell

>>> from shop.models import Product
>>> Product.objects.all()
>>> product = Product.objects.first()
>>> product.price
```

### Пользовательские команды

```bash
# Создание команды
touch shop/management/commands/populate_products.py

# Использование
python manage.py populate_products
```

---

## 📚 Полезные ресурсы

- [Django Documentation](https://docs.djangoproject.com/en/5.0/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [Celery Documentation](https://docs.celeryproject.io/en/stable/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

---

## ✅ Чек-лист для новых разработчиков

- [ ] Клонировать репозиторий
- [ ] Создать `.venv` и активировать
- [ ] Установить зависимости: `pip install -r requirements.txt`
- [ ] Скопировать `.env.example` в `.env`
- [ ] Запустить миграции: `python manage.py migrate`
- [ ] Загрузить тестовые данные: `python manage.py loaddata shop/fixtures/sample_catalog.json`
- [ ] Создать superuser: `python manage.py createsuperuser`
- [ ] Запустить сервер: `python manage.py runserver`
- [ ] Открыть http://127.0.0.1:8000/ в браузере
- [ ] Зарегистрироваться как клиент
- [ ] Добавить товар в корзину
- [ ] Оформить пробный заказ
- [ ] Зайти в админ-панель и проверить заказ

---

**Добро пожаловать в разработку!** 👨‍💻
