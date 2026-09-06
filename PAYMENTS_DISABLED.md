# Показ клиента без онлайн-оплаты и SMTP

Используется обычный production deployment, не отдельный demo/backend.
Создайте приватный .env.production только на сервере:
```dotenv
ENVIRONMENT=production
DEBUG=False
FIXED_OTP_CODE=1234
PAYMENT_ENABLED=False
FINIK_USE_STUB=False
ADMIN_EMAIL_VERIFICATION_ENABLED=False
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

Finik API/account/private/webhook keys и FINIK_STATUS_API_URL можно оставить пустыми.
При отключённой email-регистрации EMAIL_HOST/USER/PASSWORD тоже могут быть пустыми.
Фиктивные credentials не нужны. Оба новых флага по умолчанию True для сохранения прежнего поведения.

## Оплата отключена
- Checkout сохраняет настоящий заказ и резервирует остаток обычным способом.
- Заказ имеет status=pending, payment_status=waiting, paid_at=NULL.
- Payment ID, платёжная ссылка и QR не создаются.
- В checkout/заказе показано «Онлайн-оплата временно недоступна».
- В профиле вместо «Оплатить» отображается «Посмотреть заказ».
- Старые QR/ссылки не выводятся. Повторная оплата не вызывает gateway.
- create_payment/check_payment_status защищены флагом до любых сетевых запросов/назначения ID.
- Обе точки reconciliation пропускают работу. Beat/worker продолжают выполнять остальные задачи.
- Webhook отвечает 503 до обработки тела/подписи/изменения заказа. Stub route недоступен даже при ошибочно включённом stub.
- FINIK_USE_STUB=True по-прежнему запрещён production-check E018.
- Исторические состояния существующих оплаченных заказов не переписываются.
- В dashboard остаётся реальный статус из БД; ручного paid нет.

Обычный TTL резерва и отмена сохраняются: новый неоплаченный заказ без payment ID после срока
может быть отменён штатной задачей с возвратом остатков. Не превращаем показ в бесконечный резерв.
Заказы со старым реальным payment ID сохраняют прежние защитные условия отмены.

Этот режим предназначен для показа ДО реальных платежей.
Не выключайте его посреди реальных операций без плана сверки: callbacks получают 503,
а reconciliation остановлен; поздние платежи нужно сверить после восстановления интеграции.

## Email отключён безопасно
Проверка кода показала единственный вызов send_mail: отправка ссылки регистрации администратора.
При ADMIN_EMAIL_VERIFICATION_ENABLED=False:
- /accounts/admin/register/ не создаёт пользователя и возвращает 503;
- /accounts/admin/verify/<token>/ не активирует пользователя и возвращает 503;
- задача send_admin_verification_email возвращает admin-email-disabled без вызова send_mail,
  включая ранее поставленные в очередь задачи;
- существующие активные сотрудники входят по паролю через /admin/login/;
- /dashboard/ и /admin/ сохраняются;
- первого владельца создают явно через createsuperuser, без стандартного пароля.
Не используйте console backend в production: E017 остаётся ошибкой даже при отключённом email.
Неподтверждённые email-аккаунты не активируются автоматически; это не обход email verification.

## Production checks
- PAYMENT_ENABLED=False снимает только Finik requirements E019/E020/E029 и выдаёт W003.
- ADMIN_EMAIL_VERIFICATION_ENABLED=False снимает обязательность SMTP credentials E028 и выдаёт W004.
- FIXED_OTP_CODE=1234 сохраняет существующее SMS-исключение/W002.
- SECRET_KEY, DEBUG, ALLOWED_HOSTS, CSRF, HTTPS/HSTS, secure cookies, PostgreSQL,
  Redis, Celery, trusted proxy, media/upload checks не ослабляются.
- Sentry W001 может остаться, если сервис не настроен.
Предупреждения W002/W003/W004 ожидаемы, но не означают готовность к реальным продажам.

## Возврат к реальным операциям
1. Подтвердить Finik acquiring status endpoint/контракт и проверить интеграцию.
2. Заполнить реальные Finik credentials и включить PAYMENT_ENABLED=True.
3. FINIK_USE_STUB оставить False.
4. Заполнить настоящий SMTP и включить ADMIN_EMAIL_VERIFICATION_ENABLED=True, если нужна email-регистрация.
5. Отключить общий OTP, настроить настоящий SMS, аннулировать сессии/challenges показа.
6. Пересоздать все процессы OnlineShop с одинаковым env: web, worker, beat; проверить migrate config тоже.
7. Проверить новые/поздние платежи, callback и reconciliation; не считать ручной статус подтверждением оплаты.

Никогда не оставляйте смесь старых и новых workers с разными флагами.
Общий OTP не подтверждает владение SIM: нельзя показывать реальные клиентские данные с кодом 1234.

## Оставшиеся инфраструктурные условия
Нужны домен/DNS, доверенный TLS, реальные Django/PostgreSQL secrets, media ACL,
отдельный перенос данных SQLite → PostgreSQL и media, backup, согласованная сетевая/ресурсная изоляция.
Отсутствие Finik/SMTP credentials больше не блокирует показ, если соответствующие функции явно отключены.
Никакие настройки соседнего проекта, host PostgreSQL или Nginx не должны изменяться.
