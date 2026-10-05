# FastAPI Gateway

API backend для платформы CarCraft. Обслуживает весь API натив но; `express/` в репозитории — legacy-референс, не запускается.

## Запуск

```bash
# Зависимости
uv sync

# Dev-сервер
uv run uvicorn main:app --reload --port 3002

# Миграции
uv run alembic upgrade head

# Линтер
uv run ruff check .
uv run ruff check . --fix
```

## Архитектура

Паттерн: **DDD + CQRS + Clean Architecture**

Направление зависимостей: `Presentation → Application → Infrastructure ← Domain`

```text
presentation/     # HTTP: роутеры, схемы запросов/ответов
application/      # Use cases: команды, запросы, хэндлеры
infrastructure/   # Детали: БД, модели, репозитории, сервисы, настройки
domain/           # Прокси-сущности и события (legacy)
```

## Слои

### Presentation (`presentation/`)

- `routers/*.py` — нативные FastAPI-роутеры для всех доменов (auth, purchases, payments, leasing, cars, cart, documents и т.д.)
- `schemas/*.py` — Pydantic-схемы для входящих данных и `response_model`

### Application (`application/`)

- `commands/*.py` — команды + хэндлеры (state changes)
- `queries/*.py` — запросы + хэндлеры (read models)
- `errors.py` — `ServiceError` с `status_code`

### Infrastructure (`infrastructure/`)

- `settings.py` — все переменные окружения через `pydantic-settings` (один `settings` объект)
- `database.py` — SQLAlchemy async engine, `AsyncSessionLocal`, `get_db` dependency
- `auth.py` — JWT-декодирование, `get_current_user`, `require_roles(*roles)`
- `models/` — SQLAlchemy ORM-модели (users, companies, vehicles, payments, catalog и др.)
- `repositories/*.py` — репозитории, возвращают `dict` / `list[dict]`
- `services/payment_gateway.py` — ModulBank: подготовка платежа, СБП, обработка вебхука, фискализация
- `services/modulkassa.py` — ModulKassa: создание чека, проверка статуса, сборка payload

### Domain (`domain/`)

Сущности и бизнес-правила (PurchaseOrder, Notification, и т.д.), enums, ошибки и value objects. Не зависит ни от какого другого слоя.

## Настройки (`.env`)

Все переменные окружения читаются через `infrastructure/settings.py`. Полный список с дефолтами там же.

Обязательные для покупок/платежей:

```text
DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
JWT_ACCESS_SECRET
MODULBANK_SHOP_ID, MODULBANK_SECRET_KEY
API_URL, FRONTEND_URL
MODULKASSA_LOGIN, MODULKASSA_PASSWORD, MODULKASSA_RETAIL_POINT_ID
```

## API Docs

- Swagger UI: `http://localhost/api/v1/docs`
- ReDoc: `http://localhost/api/v1/redoc`
