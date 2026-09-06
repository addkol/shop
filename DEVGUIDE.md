# Руководство разработчика

Каноническое описание запуска, архитектуры, базы, авторизации, изображений, заказов, Finik и production checklist находится в `README.md`. Этот файл содержит короткую карту кода для сопровождения.

## Приложения

- `accounts`: `User`, `ClientProfile`, `AdminProfile`, OTP-вход, админский вход, SMS/email задачи.
- `shop`: категории, товары, галерея, видео, оптовые цены, корзина, адреса, заказы, отзывы.
- `payment`: Finik authorizer, создание платежа, подписанный webhook, `PaymentEvent`.
- `project`: settings, root URLs, Celery, health-check, security middleware, media view.

## Правила изменений

1. Не изменяйте цену заказа после создания: историческая цена хранится в `OrderItem`.
2. Любое уменьшение остатка выполняйте под `transaction.atomic()` и `select_for_update()`.
3. Возвращайте резерв только через `release_order_stock()` — операция идемпотентна.
4. Не доверяйте сумме или статусу из браузера; сервер пересчитывает корзину и проверяет webhook.
5. Не храните OTP, токены и ключи открытым текстом.
6. Не создавайте скрытые оптовые скидки; диапазоны задаются в `WholesalePrice`.
7. Для media используйте Django storage API, а не ручную сборку путей.

## Проверка перед merge

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py collectstatic --noinput
```

Для production дополнительно выполните `python manage.py check --deploy` с production-переменными.
