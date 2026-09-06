# Политика безопасности

## Сообщение об уязвимости

Не публикуйте реальные секреты, ключи Finik, персональные данные или детали эксплойта в публичном issue. Сообщите владельцу магазина по закрытому каналу и укажите затронутую версию, шаги воспроизведения и возможное влияние.

## Границы доверия

- Браузер не определяет цену, остаток или статус оплаты: сервер пересчитывает корзину и заказ.
- Finik webhook принимается только после проверки свежести timestamp, RSA-подписи, валюты и суммы.
- OTP хранится только как password hash, имеет TTL, лимит попыток и rate limit по телефону/IP.
- Client IP читается из proxy-заголовка только при явно настроенном доверенном reverse proxy.
- Загружаемые изображения/видео проверяются по расширению, MIME, размеру и magic bytes.
- Платёжные URL разрешены только по HTTPS и allowlist доменов.

## Secrets

`.env`, production backup, БД и media исключены из Git. В репозитории не должно быть готовых логинов или паролей. Используйте Render secrets или файл `.env.production` с правами `600`; регулярно ротируйте credentials.

## Production defaults

`python manage.py check --deploy` блокирует запуск при DEBUG, SQLite, wildcard hosts/origins, небезопасных cookies/TLS, local cache/eager Celery, тестовых SMS/Finik, Django media serving или незаполненных обязательных credentials.

## Поддерживаемые версии

Поддерживается текущая версия ветки `main` с hash-locked зависимостями. Dependabot и CI проверяют Python/Docker/GitHub Actions обновления, тесты, Bandit и `pip-audit`.