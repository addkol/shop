# 🚀 Быстрый старт - Онлайн Магазин

Полная инструкция для запуска проекта за 5 минут.

## Минимальные требования

- Python 3.10+
- Windows/Mac/Linux
- Интернет

## Шаг за шагом

### 1️⃣ Откройте терминал в папке проекта

```powershell
cd c:\Users\user\Documents\OnlineShop
```

### 2️⃣ Создайте виртуальное окружение

```powershell
python -m venv .venv
```

### 3️⃣ Активируйте окружение

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

✅ **Проверка:** в начале строки должно появиться `(.venv)`

### 4️⃣ Установите зависимости

```powershell
pip install -r requirements.txt
```

⏱️ Это займет 2-3 минуты

### 5️⃣ Настройте окружение

```powershell
copy .env.example .env
```

*Оставьте `.env` как есть для разработки*

### 6️⃣ Подготовьте базу данных

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py loaddata shop/fixtures/sample_catalog.json
```

### 7️⃣ Запустите сервер

```powershell
python manage.py runserver
```

**Готово!** 🎉

---

## 🌐 Откройте в браузере

**Главная страница:** http://127.0.0.1:8000/

- Каталог с товарами: ✅
- Корзина: ✅
- Регистрация по телефону: ✅
- SMS верификация: ✅ (коды печатаются в консоль)
- Оформление заказа: ✅
- Профиль: ✅

---

## 📊 Админ-панель

**URL:** http://127.0.0.1:8000/admin/

Для входа создайте администратора:

```powershell
python manage.py createsuperuser
```

Введите:
- Email: `admin@example.com`
- Пароль: `ваш пароль`

---

## 🔐 Тестирование авторизации

### Регистрация клиента:

1. Нажмите "Новый аккаунт"
2. Введите номер: **+996777123456** (любой в формате)
3. Введите имя (опционально)
4. Нажмите "Отправить код SMS"
5. В консоли найдите код (4 цифры)
6. Введите код в форму верификации

✅ Вы авторизованы!

---

## 🛒 Тестирование покупок

1. Откройте "Каталог"
2. Нажмите "Добавить" на товар
3. Перейдите в "Корзину"
4. Нажмите "Оформить"
5. Заполните адрес доставки
6. Выберите способ оплаты
7. Нажмите "Оформить заказ"

✅ Заказ создан! Посмотрите в профиле.

---

## 📱 Тестирование SMS

Все SMS выводятся в консоль при `SMS_PROVIDER=console` (по умолчанию).

Пример в консоли:
```
SMS to +996777123456: Your verification code is 1234
```

Используйте этот код для верификации.

---

## 🚫 Если что-то не работает

### Ошибка: "Port 8000 is already in use"
```powershell
python manage.py runserver 8001
```

### Ошибка: "No migrations to apply"
```powershell
python manage.py makemigrations --empty shop
python manage.py migrate
```

### Ошибка при loaddata
```powershell
python manage.py loaddata shop/fixtures/sample_catalog.json
```

### Очистить БД (опасно!)
```powershell
python manage.py flush
```

---

## 📝 Основные команды

| Команда | Для чего |
|---------|----------|
| `python manage.py runserver` | Запуск сервера |
| `python manage.py createsuperuser` | Создать администратора |
| `python manage.py migrate` | Применить миграции |
| `python manage.py makemigrations` | Создать миграции |
| `python manage.py loaddata <file>` | Загрузить данные |
| `python manage.py flush` | Стереть БД (осторожно!) |

---

## 🔧 Полезные ссылки

- **Админ-панель:** http://127.0.0.1:8000/admin/
- **API:** http://127.0.0.1:8000/api/
- **Товары:** http://127.0.0.1:8000/
- **Корзина:** http://127.0.0.1:8000/cart/
- **Профиль:** http://127.0.0.1:8000/accounts/profile/

---

## 💡 Подсказки

1. **Консоль всегда активна** - смотрите туда для SMS кодов и ошибок
2. **Перезагрузитесь** при изменении settings.py
3. **Миграции нужны** при изменении моделей
4. **Удаляйте старую БД** если много ошибок: `rm db.sqlite3`

---

## ✨ Что дальше?

- Проверьте [README.md](README.md) для полной документации
- Измените данные в админ-панели
- Добавьте свои товары
- Настройте платежи для production

**Удачи!** 🎉
