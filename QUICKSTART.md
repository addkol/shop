# Быстрый запуск

## Windows PowerShell

```powershell
cd C:\Users\user\Documents\OnlineShop
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py loaddata shop/fixtures/sample_catalog.json
python manage.py runserver 0.0.0.0:8000
```

Откройте `http://127.0.0.1:8000/`. Для входа клиента используйте номер Кыргызстана; при `SMS_PROVIDER=console` одноразовый код появится в терминале.

## Администратор

```powershell
python manage.py createsuperuser
```

Админка: `http://127.0.0.1:8000/admin/`. Готовых логинов и паролей в репозитории нет.

## Проверка

```powershell
python manage.py check
python manage.py test
```

Подробное описание находится в `README.md`.
