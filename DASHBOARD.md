# Dashboard и временный OTP

## Production, без отдельного demo-режима
Используется обычная конфигурация ENVIRONMENT=production, DEBUG=False, PostgreSQL, Redis,
Celery worker/beat, Gunicorn, Nginx и HTTPS. Единственное предусмотренное исключение — SMS OTP.

В приватном .env.production временно задайте:
```dotenv
FIXED_OTP_CODE=1234
```
В example значение оставлено пустым, чтобы общий код не включался случайно.
При заданном коде SMS/Twilio не вызываются ни при создании challenge, ни в Celery-задаче доставки.
Код хранится только как hash; сохраняются TTL, попытки, resend cooldown, лимит запросов номера/IP,
проверка challenge, подтверждение телефона и обычная Django session. Параллельные проверки
challenge сериализуются блокировкой строки профиля.

Новый валидный номер +996 и девять цифр сначала проходит регистрацию. Вход для неизвестного
номера сохраняет прежний анти-enumeration decoy-flow: сначала зарегистрируйтесь.
Существующие активные клиенты используют обычный вход. Заблокированные клиенты не реактивируются.
Staff/superuser/admin не могут получить доступ через общий OTP даже если имеют клиентский профиль:
для сотрудников нужен защищённый /admin/login/ с паролем.

**Общий OTP НЕ подтверждает владение номером.** Любой знающий код может войти под чужим
клиентским номером. Не переносите реальные клиентские данные на публичный показ с общим OTP.
Флаг phone_verified при таком входе технически выставляется существующим flow, но это не доказательство владения SIM.
Django выдаёт project.W002 (WARNING), запуск не блокируется. Неверный формат кода — project.E030.
SMS production checks E015/E016 освобождены только при непустом FIXED_OTP_CODE.
Проверки HTTPS, cookies, CSRF, PostgreSQL, Redis, Celery, Finik, SMTP и upload validators не отключаются.

Для настоящих продаж:
1. Заполните Twilio или реализуйте и протестируйте другого SMS-провайдера.
2. Установите FIXED_OTP_CODE= (пустое значение).
3. Пересоздайте web, worker, beat с обновлённым env. Не оставляйте старые workers с другим значением.
4. Аннулируйте клиентские сессии показа и активные OTP challenges перед допуском реальных клиентов.
5. Проверьте реальный случайный OTP с доставкой; project.W002 должен исчезнуть.
Изменение только env не аннулирует уже выданные сессии/хеши автоматически.

## URL
- /dashboard/ — обзор.
- /dashboard/orders/ — список, поиск, фильтры, пагинация.
- /dashboard/orders/<id>/ — позиции, получатель, резерв, оплата, история событий согласно правам.
- /dashboard/orders/<id>/action/?action=ship|deliver|cancel — подтверждение; изменение только POST.
- /dashboard/products/ — каталог.
- /dashboard/products/new/ — новый товар.
- /dashboard/products/<id>/edit/ — карточка, главное фото, видео, галерея, оптовые диапазоны.
- /dashboard/categories/ — категории.
- /dashboard/categories/new/ и /dashboard/categories/<id>/edit/ — создание/редактирование.
- /dashboard/customers/ и /dashboard/customers/<id>/ — клиенты, адреса и заказы без auth secrets.
- /dashboard/payments/ — только чтение; история событий в карточке заказа.
- /dashboard/stock/ и /dashboard/stock/<id>/ — доступный остаток, резерв, корректировка с причиной.
- /dashboard/reviews/ и /dashboard/reviews/<id>/ — просмотр и модерация.
- /admin/ сохранён как технический fallback.
- /admin/login/ — единственный обработчик пароля сотрудников с прежним rate limit.
  Старый /accounts/admin/login/ только перенаправляет.
  После входа открывается dashboard либо безопасный локальный next.

## Первое создание ролей
После migrate, на выбранном сервере (не выполнялось этой задачей):
```sh
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T web python manage.py setup_dashboard_roles
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T web python manage.py createsuperuser
```
Команда ролей идемпотентна, но **перезаписывает набор permissions пяти одноимённых групп**.
Она не создаёт пользователей, не меняет пароли и не назначает is_staff.
Создайте сотрудника, установите is_active/is_staff, безопасный пароль и назначьте группу через /admin/.
Автоматических/стандартных production-паролей нет. Не используйте пароли из QA-тестов.
Существующему суперпользователю группа не обязательна.

## Роли
| Роль | Доступ |
|---|---|
| Owner | Все рабочие разделы; каталог/опт/медиа; склад; отправка/доставка/отмена; модерация; управление сотрудниками и группами через техническую админку |
| Administrator | Все операционные разделы и действия, без управления пользователями/группами |
| Manager | Каталог/категории/опт/медиа, склад, заказы и их допустимые переходы, клиенты, чтение платежей, модерация |
| Warehouse | Просмотр каталога и заказов, складские корректировки, отправка/доставка оплаченных заказов; без отмен, платежных событий, клиентского справочника и изменения карточек |
| Support | Чтение заказов/клиентов/каталога/платежей, отмена ожидающего заказа с причиной, модерация; без изменения каталога/склада/отправки |

Owner — доверенная административная роль: accounts.change_user/auth.change_group в /admin/
позволяют управлять правами, включая повышение привилегий. Не назначайте Owner обычным менеджерам.
У staff без permissions доступен только пустой обзор; чужие данные не выдаются.
Обычный клиент получает 403, anonymous — redirect на защищённый вход.

### Точные наборы permissions
Базовые наборы в shop/management/commands/setup_dashboard_roles.py:
- READ_ORDERS: shop.view_order, shop.view_orderitem.
- READ_CLIENTS: accounts.view_user, accounts.view_clientprofile, shop.view_address.
- READ_CATALOG: shop.view_product, shop.view_category, shop.view_productimage, shop.view_wholesaleprice.
- CATALOG_EDIT: shop.add_product, shop.change_product, shop.add_category, shop.change_category,
  shop.adjust_stock; add/change/delete для shop.productimage и shop.wholesaleprice.
- OPERATIONS: READ_ORDERS + READ_CLIENTS + READ_CATALOG + payment.view_paymentevent + shop.view_review.
- Owner (31): OPERATIONS + CATALOG_EDIT + shop.fulfill_order + shop.cancel_order + shop.change_order +
  shop.change_review + accounts.add_user + accounts.change_user + auth.view_group + auth.add_group + auth.change_group.
- Administrator (26): OPERATIONS + CATALOG_EDIT + shop.fulfill_order + shop.cancel_order + shop.change_order + shop.change_review.
- Manager (25): OPERATIONS + CATALOG_EDIT + shop.fulfill_order + shop.cancel_order + shop.change_review.
- Warehouse (8): READ_ORDERS + READ_CATALOG + shop.fulfill_order + shop.adjust_stock.
- Support (13): OPERATIONS + shop.cancel_order + shop.change_review.

Просмотр общей карточки заказа раскрывает получателя/телефон для доставки; доступ к отдельному
справочнику клиентов и платежным событиям проверяется отдельно. Наборы прав намеренно не дают удаления заказов/клиентов.

## Состояния, stock, аудит
Новые модели заказов/платежей или второй backend не создавались.
В существующей модели нет processing/completed:
- paid отображается как «Оплачены / к обработке»;
- delivered — «Доставлены / завершены».
Категории не имеют is_active — переключатель не выдуман.

Разрешены только paid+success → shipped → delivered и отмена pending+waiting без освобождённого резерва.
Отмена требует причину и вызывает существующий release_order_stock; повтор не возвращает резерв дважды.
Dashboard и технический OrderAdmin используют общий transition_order с row lock.
Кнопки «отметить paid» нет, поля payment_status/status из произвольного POST не принимаются.
Нет нового ручного reconciliation endpoint — работает существующая периодическая Celery-задача.

Product.stock — уже доступный (не зарезервированный) остаток.
Резерв показан как сумма позиций pending/paid заказов, где stock_released=False.
Редактирование карточки не меняет stock; новый товар имеет 0 до корректировки в «Склад».
StockForm требует причину и expected_stock; сервис блокирует продукт, отклоняет отрицательное число
и конфликт изменения остатка. Технический ProductAdmin не принимает stock и сохраняет актуальный остаток под блокировкой.
Действия dashboard записываются в существующий django_admin_log, без новой таблицы аудита.

## Production QA и ограничения
Для локальной проверки использовался тот же production образ и Compose, с отдельными QA volumes,
синтетическими данными, FIXED_OTP_CODE=1234 и DEBUG=False.
Изоляция QA — не новый режим приложения. Внешняя сеть web/worker заблокирована на уровне Docker.
Локальный Nginx использовал self-signed сертификат; browser test игнорировал только доверие к этому сертификату,
а не CSRF/secure cookies/HTTPS. В реальном deploy нужен доверенный Let's Encrypt сертификат.
Выполнен реальный HTTPS browser flow: регистрация → 1234 → товар → корзина → checkout → заказ → dashboard.
При недоступном Finik заказ остаётся ожидающим оплаты; реального успешного платежа этим тестом не подтверждено.

**Остался внешний блокер предыдущего аудита:** реальный FINIK_STATUS_API_URL/контракт acquiring API,
ключи и проверка Finik sandbox. В QA были синтетические ключи; это не готовые production credentials.
Не подставляйте фиктивные секреты, чтобы пройти checks на сервере.
Нужны также SMTP, домен/DNS/TLS, секреты PostgreSQL/Django, права media, off-server backup.
Порты 5432/6379 в production Compose не публикуются; web по умолчанию только 127.0.0.1:8010.
Hetzner, commit, push и серверный deploy этой задачей не выполнялись.
