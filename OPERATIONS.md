# Эксплуатация магазина

Основной интерфейс владельца — /dashboard/, технический fallback — /admin/.
Роли, корректировка склада, допустимые переходы заказов и отключение общего OTP:
[DASHBOARD.md](DASHBOARD.md). После показа с FIXED_OTP_CODE необходимо не только
выключить настройку во всех процессах, но и аннулировать клиентские сессии/активные challenges показа.

## Ежедневный контроль

- `/health/` возвращает `200`, database/cache имеют статус `ok`.
- `web`, `db`, `redis`, `worker`, `beat` работают без restart loop.
- `celery -A project inspect ping` получает `pong` от worker.
- Сверка Finik не накапливает `payment_reconciliation_failures`.
- Нет необработанных заказов со статусом `refund_required`.
- Свободное место host и PostgreSQL выше аварийного порога.

## Reconciliation Finik

Celery Beat раз в `FINIK_RECONCILIATION_INTERVAL_SECONDS` ставит `payment.tasks.reconcile_pending_payments_task`. Worker выбирает ожидающие платежи старше `FINIK_RECONCILIATION_MIN_AGE_SECONDS` и недавно отменённые заказы в пределах `FINIK_RECONCILIATION_LOOKBACK_HOURS`.

- `PENDING`, `PROCESSING`, `WAITING` не меняют финансовый статус заказа.
- Только `SUCCESS/SUCCEEDED` с совпадающими `payment_id`, суммой и валютой KGS отмечает заказ оплаченным.
- `FAILED/CANCELED` безопасно возвращает резерв один раз.
- Успех после отмены переводит оплату в `refund_required`, но не резервирует товар повторно.
- Timeout, HTTP error, неизвестный status, другой `payment_id` или неверная сумма не считаются успехом; ошибка записывается в заказ и повторяется следующим запуском.
- Уникальный `provider_event_id`, блокировка заказа в транзакции и повторная проверка состояния делают webhook/polling идемпотентными.

Автоматическая отмена реального просроченного платежа разрешена только после успешной проверки провайдера не раньше `payment_expires_at`. При недоступности Finik резерв сохраняется: безопаснее ручная проверка, чем ложная отмена оплаченного заказа.

## Backup

```bash
cd /opt/onlineshop
sh deploy/scripts/backup.sh
```

Скрипт прекращает работу, если PostgreSQL container не запущен. Он создаёт PostgreSQL custom dump во временном новом каталоге, проверяет его через `pg_restore --list`, архивирует `data/media`, проверяет tar, записывает `SHA256SUMS`, выполняет `sha256sum -c` и только затем создаёт `BACKUP_COMPLETE`. Неполный backup удаляется.

Каждый обычный `deploy.sh` обязательно вызывает этот скрипт до `git pull` и migrations. `FIRST_DEPLOY=1` разрешён только при полном отсутствии контейнера и volume OnlineShop PostgreSQL; bypass-флага для рабочей БД нет.

Храните минимум одну зашифрованную копию вне Hetzner. Практический минимум: 7 ежедневных, 4 еженедельных, 12 ежемесячных копий. Автоматическое удаление не включено намеренно.

## Restore

Не проверяйте restore впервые на production. Восстанавливайте свежую копию на отдельном стенде и сверяйте пользователей, товары, заказы, позиции, платежные события и media.

```bash
cd /opt/onlineshop
CONFIRM_RESTORE=YES RESTORE_MEDIA=1 \
  sh deploy/scripts/restore.sh backups/<UTC-timestamp>
```

Restore проверяет `SHA256SUMS`, останавливает web/worker/beat, пересоздаёт схему PostgreSQL, загружает dump, при явном `RESTORE_MEDIA=1` восстанавливает media, применяет migrations и запускает сервисы. Операция разрушительна для текущей БД: перед ней обязателен отдельный актуальный backup.

Media распаковываются внутри одноразового контейнера от UID/GID `10001`, чтобы восстановление работало с правами `appuser`. Перед запуском web проверяются ссылки media. При ошибке сервисы остаются остановленными до ручной проверки, чтобы не открыть магазин с частично восстановленными данными.

После restore выполните:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T web \
  python manage.py verify_media_references
docker compose --env-file .env.production -f docker-compose.prod.yml exec -T web \
  python manage.py check --deploy --database default
curl -fsS https://shop.example.com/health/
```

## Media permissions

`data/media` принадлежит числовому UID/GID `10001:10001`. Default ACL разрешает host `www-data` и deploy-пользователю чтение новых файлов и каталогов. После ручного копирования или restore повторите:

```bash
sudo env PROJECT_ROOT=/opt/onlineshop DEPLOY_USER="$USER" \
  sh deploy/scripts/setup-media-permissions.sh
```

Затем обязательно запустите `verify_media_references`. Не применяйте `chmod -R 777`.

## Платёжные инциденты

- Не меняйте `payment_status`, сумму, `stock_released` или остатки напрямую в БД.
- `refund_required` требует ручной сверки и возврата у провайдера.
- Проверяйте `PaymentEvent`, `payment_checked_at`, `payment_reconciliation_failures` и `payment_last_error`.
- Payload старше `PAYMENT_EVENT_PAYLOAD_RETENTION_DAYS` очищается, строка аудита сохраняется.
- Предварительная оценка без изменения БД: `python manage.py purge_payment_payloads --dry-run`.
- При массовой недоступности Finik не отменяйте ожидающие заказы автоматически вручную; сначала подтвердите статусы у провайдера.

## Первичный перенос

`export_initial_data` и `import_initial_data` предназначены только для первого переноса SQLite → пустой PostgreSQL. Повторный import в рабочую БД блокируется. Test/stub-кандидаты перечисляются в manifest и переносятся только после явного подтверждения; автоматического удаления нет. После успешного переноса храните bundle как чувствительный backup либо безопасно уничтожьте его по утверждённой политике.

## Ротация секретов

При утечке замените ключ у провайдера и значение в `.env.production`. После смены `SECRET_KEY` Django-сессии станут недействительны. После ротации Finik API/private/webhook public key повторите signed beta/production сценарии. После смены БД-пароля синхронно обновите `POSTGRES_PASSWORD` и `DB_PASSWORD` с плановой ротацией PostgreSQL role.

## Обновление зависимостей

Изменяйте `requirements.in`/`requirements-dev.in`, пересобирайте hash-locked файлы под Python 3.12 и запускайте CI:

```bash
pip-compile --generate-hashes -o requirements.txt requirements.in
pip-compile --generate-hashes -o requirements-dev.txt requirements-dev.in
pip-audit -r requirements.txt
```

Не редактируйте версии и hashes вручную.
