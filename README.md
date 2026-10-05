# Платформа мультилизинга CarCraft

Платформа для автолизинга с поддержкой нескольких лизинговых компаний, дилеров
и дистрибьюторов.

## Технологии

- **Фронтенд:** Nuxt 3, Vue 3, Tailwind CSS, Pinia.
- **Шлюз FastAPI:** Python 3.12, FastAPI, SQLAlchemy 2, asyncpg, Alembic.
- **База данных:** PostgreSQL 15.
- **Инфраструктура:** Docker, Nginx.

## Запуск

```bash
# Все сервисы через Docker — рекомендуемый вариант
docker compose up -d --build

# Приложение: http://localhost
# Swagger FastAPI: http://localhost/api/v1/docs
```

### Локальная разработка

```bash
# Фронтенд, порт 3000
bun run dev:frontend

# Шлюз FastAPI, порт 3002
cd backend
uv sync
uv run uvicorn main:app --reload --port 3002
```

## Сервисы

| Сервис | Порт | Описание |
| --- | --- | --- |
| Nginx | 80 | Обратный прокси: `/api` → FastAPI, `/` → фронтенд |
| Фронтенд | 3000 | Nuxt 3 SSR |
| Backend (FastAPI) | 3002 | API-шлюз: нативные маршруты `/purchases`, `/payments` |
| PostgreSQL | 5433→5432 | Основная БД |

## Клиентские приложения

Текущий Nuxt-фронтенд реализует только desktop web-версию с минимальной
шириной viewport 768 CSS-пикселей. Мобильная responsive-версия сайта не
поддерживается и не разрабатывается. Для мобильных устройств позднее будет
создано отдельное нативное приложение.

## Структура проекта

```text
├── backend/         # шлюз FastAPI: DDD+CQRS, покупки, платежи, прокси
├── frontend/        # фронтенд Nuxt 3: страницы, компоненты, хранилища
├── specs/           # спецификации задач
├── docker-compose.yml
└── nginx.conf
```

## Маршрутизация Nginx → FastAPI

Все запросы `/api/*` направляются в FastAPI:

- `GET /api/v1/health` — проверка состояния FastAPI;
- `POST /api/v1/purchases/*` — покупки и оплата;
- `POST /api/v1/payments/webhook/*` — вебхуки ModulBank и ModulKassa.

## Роли пользователей

| Роль | Описание |
| --- | --- |
| `carcraft_employee` | Полный доступ, подтверждение отмен |
| `dealer` | Работа с клиентами, создание заявок |
| `client` | Каталог, покупки, оплата |
| `leasing_company` | Рассмотрение заявок |
| `distributor` | Управление складом |

## Демоаккаунты

Пароль для всех перечисленных аккаунтов: `0000`.

| Телефон | Роль |
| --- | --- |
| +76661234567 | `carcraft_employee` |
| +76661234568 | `dealer` |
| +76661234569 | `client` — физическое лицо |
| +76661234570 | `client` — юридическое лицо |
| +76661234571 | `leasing_company` |
| +76661234573 | `distributor` |
