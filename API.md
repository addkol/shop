# 🔌 REST API документация

Полный справочник всех API endpoints для Онлайн Магазина.

## 📝 Основа

- **Базовый URL:** `http://127.0.0.1:8000/api/`
- **Формат:** JSON
- **Аутентификация:** Session-based (cookies)
- **CORS:** Поддерживается

## 🔐 Аутентификация

### Регистрация клиента

**POST** `/accounts/register/`

Request:
```json
{
    "phone": "+996777123456",
    "first_name": "Иван",
    "patronymic": "Иванович"
}
```

Response:
```json
{
    "status": "sms_sent",
    "message": "SMS код отправлен на номер +996777123456"
}
```

---

### Верификация SMS

**POST** `/accounts/verify/`

Request:
```json
{
    "phone": "+996777123456",
    "code": "1234"
}
```

Response:
```json
{
    "status": "verified",
    "user": {
        "id": 1,
        "phone": "+996777123456",
        "first_name": "Иван"
    },
    "token": "session-id"
}
```

---

### Вход администратора

**POST** `/admin/login/`

Request:
```json
{
    "email": "admin@example.com",
    "password": "password123"
}
```

Response:
```json
{
    "status": "success",
    "admin": {
        "id": 1,
        "email": "admin@example.com",
        "full_name": "Admin User"
    }
}
```

---

### Выход

**POST** `/accounts/logout/`

Response:
```json
{
    "status": "logged_out"
}
```

---

## 🛍️ Товары

### Список всех товаров

**GET** `/products/`

Query Parameters:
- `category` - фильтр по ID категории
- `search` - поиск по названию
- `page` - номер страницы (20 товаров на странице)

Response:
```json
{
    "count": 100,
    "next": "/api/products/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "name": "Товар 1",
            "description": "Описание товара",
            "price": 1000.00,
            "category": 1,
            "stock": 50,
            "image": "/media/products/product-1.jpg",
            "created_at": "2024-01-01T10:00:00Z"
        }
    ]
}
```

---

### Товар по ID

**GET** `/products/{id}/`

Response:
```json
{
    "id": 1,
    "name": "Товар 1",
    "description": "Подробное описание",
    "price": 1000.00,
    "category": {
        "id": 1,
        "name": "Электроника"
    },
    "stock": 50,
    "image": "/media/products/product-1.jpg",
    "reviews": [
        {
            "id": 1,
            "user": "Иван",
            "rating": 5,
            "comment": "Отличный товар!",
            "date": "2024-01-15T10:00:00Z"
        }
    ]
}
```

---

### Создание товара (только администратор)

**POST** `/products/`

Request:
```json
{
    "name": "Новый товар",
    "description": "Описание",
    "price": 1500.00,
    "category": 1,
    "stock": 100,
    "image": "<base64 или URL>"
}
```

---

### Редактирование товара (только администратор)

**PUT** `/products/{id}/`

Request:
```json
{
    "name": "Обновленное имя",
    "price": 1200.00,
    "stock": 80
}
```

---

### Удаление товара (только администратор)

**DELETE** `/products/{id}/`

Response: 204 No Content

---

## 📂 Категории

### Список категорий

**GET** `/categories/`

Response:
```json
[
    {
        "id": 1,
        "name": "Электроника",
        "description": "Электронные товары",
        "product_count": 45
    }
]
```

---

## 🛒 Корзина

### Получить корзину

**GET** `/cart/`

Response:
```json
{
    "id": 1,
    "user": 1,
    "items": [
        {
            "id": 10,
            "product": {
                "id": 1,
                "name": "Товар 1",
                "price": 1000.00
            },
            "quantity": 2,
            "subtotal": 2000.00
        }
    ],
    "total": 2000.00,
    "updated_at": "2024-01-20T10:00:00Z"
}
```

---

### Добавить товар в корзину

**POST** `/cart/items/`

Request:
```json
{
    "product": 1,
    "quantity": 2
}
```

Response: 201 Created

---

### Обновить количество товара в корзине

**PUT** `/cart/items/{id}/`

Request:
```json
{
    "quantity": 3
}
```

---

### Удалить товар из корзины

**DELETE** `/cart/items/{id}/`

Response: 204 No Content

---

### Очистить корзину

**DELETE** `/cart/`

Response:
```json
{
    "status": "cart_cleared"
}
```

---

## 📦 Заказы

### Создать заказ

**POST** `/orders/`

Request:
```json
{
    "address": {
        "country": "Киргизия",
        "city": "Бишкек",
        "street": "ул. Чуй",
        "building": "123",
        "apartment": "45",
        "postal_code": "720000"
    },
    "payment_method": "qr_code",
    "save_address": true
}
```

Response:
```json
{
    "id": 1,
    "user": 1,
    "order_number": "ORD-2024-001",
    "items": [...],
    "total": 5000.00,
    "status": "pending",
    "payment_status": "pending",
    "payment_method": "qr_code",
    "qr_code": "/media/qrcodes/payment-1.png",
    "created_at": "2024-01-20T10:00:00Z"
}
```

---

### Список заказов пользователя

**GET** `/orders/`

Response:
```json
[
    {
        "id": 1,
        "order_number": "ORD-2024-001",
        "total": 5000.00,
        "status": "delivered",
        "payment_status": "paid",
        "created_at": "2024-01-20T10:00:00Z"
    }
]
```

---

### Заказ по ID

**GET** `/orders/{id}/`

Response:
```json
{
    "id": 1,
    "order_number": "ORD-2024-001",
    "items": [
        {
            "id": 1,
            "product": {
                "id": 1,
                "name": "Товар 1",
                "price": 1000.00
            },
            "quantity": 1,
            "subtotal": 1000.00
        }
    ],
    "address": {
        "country": "Киргизия",
        "city": "Бишкек",
        "street": "ул. Чуй",
        "building": "123"
    },
    "total": 5000.00,
    "status": "delivered",
    "payment_status": "paid",
    "payment_method": "qr_code",
    "timeline": [
        {
            "status": "pending",
            "timestamp": "2024-01-20T10:00:00Z"
        },
        {
            "status": "processing",
            "timestamp": "2024-01-20T11:00:00Z"
        },
        {
            "status": "shipped",
            "timestamp": "2024-01-21T09:00:00Z"
        },
        {
            "status": "delivered",
            "timestamp": "2024-01-22T14:00:00Z"
        }
    ]
}
```

---

### Обновить статус заказа (только администратор)

**PATCH** `/orders/{id}/`

Request:
```json
{
    "status": "processing"
}
```

Допустимые статусы:
- `pending` - ожидание
- `processing` - обработка
- `shipped` - отправлено
- `delivered` - доставлено
- `cancelled` - отменено

---

## 👤 Профиль

### Получить профиль

**GET** `/accounts/profile/`

Response:
```json
{
    "id": 1,
    "phone": "+996777123456",
    "first_name": "Иван",
    "patronymic": "Иванович",
    "last_name": "Иванов",
    "email": "ivan@example.com",
    "created_at": "2024-01-01T10:00:00Z",
    "order_count": 5,
    "saved_addresses": [
        {
            "id": 1,
            "country": "Киргизия",
            "city": "Бишкек",
            "street": "ул. Чуй",
            "building": "123",
            "apartment": "45",
            "postal_code": "720000",
            "is_default": true
        }
    ]
}
```

---

### Обновить профиль

**PUT** `/accounts/profile/`

Request:
```json
{
    "first_name": "Иван",
    "last_name": "Иванов",
    "email": "newemail@example.com"
}
```

---

### Сохраненные адреса

**GET** `/accounts/addresses/`

Response:
```json
[
    {
        "id": 1,
        "country": "Киргизия",
        "city": "Бишкек",
        "street": "ул. Чуй",
        "building": "123",
        "apartment": "45",
        "postal_code": "720000",
        "is_default": true
    }
]
```

---

### Добавить адрес

**POST** `/accounts/addresses/`

Request:
```json
{
    "country": "Киргизия",
    "city": "Бишкек",
    "street": "ул. Ленина",
    "building": "456",
    "apartment": "78",
    "postal_code": "720000"
}
```

---

### Удалить адрес

**DELETE** `/accounts/addresses/{id}/`

Response: 204 No Content

---

## 💳 Платежи

### Вебхук Finik

**POST** `/webhook/finik/`

Request (от Finik):
```json
{
    "payment_id": "PAY-123456",
    "order_id": 1,
    "status": "success",
    "amount": 5000.00,
    "timestamp": "2024-01-20T10:00:00Z"
}
```

Response:
```json
{
    "status": "ok"
}
```

---

## ⚠️ Статус коды

| Код | Описание |
|-----|---------|
| 200 | OK - успешный запрос |
| 201 | Created - ресурс создан |
| 204 | No Content - успешно удалено |
| 400 | Bad Request - неверные данные |
| 401 | Unauthorized - не авторизован |
| 403 | Forbidden - доступ запрещен |
| 404 | Not Found - ресурс не найден |
| 500 | Server Error - ошибка сервера |

---

## 📝 Примеры использования

### JavaScript/Fetch

```javascript
// Получить товары
fetch('http://localhost:8000/api/products/')
    .then(r => r.json())
    .then(data => console.log(data));

// Создать заказ
fetch('http://localhost:8000/api/orders/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
        address: {...},
        payment_method: 'qr_code'
    })
})
    .then(r => r.json())
    .then(data => console.log(data));
```

### Python/Requests

```python
import requests

# Получить товары
response = requests.get('http://localhost:8000/api/products/')
products = response.json()

# Создать заказ
response = requests.post(
    'http://localhost:8000/api/orders/',
    json={
        'address': {...},
        'payment_method': 'qr_code'
    },
    cookies=session.cookies
)
order = response.json()
```

### cURL

```bash
# Получить товары
curl http://localhost:8000/api/products/

# Создать заказ
curl -X POST http://localhost:8000/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{
    "address": {...},
    "payment_method": "qr_code"
  }'
```

---

## 🔍 Фильтрация и поиск

### Поиск товаров

```
GET /api/products/?search=смартфон
GET /api/products/?category=1&search=телефон
GET /api/products/?page=2
```

### Сортировка

```
GET /api/products/?ordering=price
GET /api/products/?ordering=-price  # По убыванию
GET /api/products/?ordering=-created_at
```

---

## ✅ Best Practices

1. **Всегда проверяйте статус коды** - используйте правильные обработчики ошибок
2. **Кэшируйте данные** - не делайте одинаковые запросы несколько раз
3. **Используйте pagination** - не загружайте все товары сразу
4. **Validate на клиенте** - уменьшите неверные запросы
5. **Используйте HTTPS в production** - никогда не отправляйте пароли по HTTP

---

**Полная документация API готова!** 📚
