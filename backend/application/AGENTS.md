# Application Layer

Use cases, CQRS-команды и запросы, оркестрация операций. Связывает presentation с infrastructure и domain.

## Структура

```text
application/
├── errors.py                       # ServiceError + domain_to_http() маппинг
├── authentication.py               # authenticate_access_token / *_with_db (для presentation/dependencies/auth.py)
├── commands/                       # write-операции (state changes)
│   ├── auth.py                     # login, verify_phone, register, refresh, logout, resend_code
│   ├── purchases.py                # create_purchase_orders, pay_remaining, request/approve_cancellation, pay_schedule_item
│   ├── notifications.py            # create, mark_read, mark_all_read, delete
│   ├── email_preferences.py        # update
│   └── vehicle_images.py           # upload, delete
└── queries/                        # read-операции
    ├── purchases.py                # list, details, schedule, receipts
    ├── notifications.py            # list, counts
    ├── email_preferences.py        # get_or_default (без write)
    ├── vehicle_images.py
    └── company_lookup.py
```

## Паттерн работы с доменом

Хендлер гидрирует доменную сущность из dict'а репозитория и делегирует ей бизнес-правила:

```python
order_dict = await repo.get_by_id_with_details(session, cmd.order_id)
if not order_dict:
    raise OrderNotFoundError()
order = PurchaseOrder.from_dict(order_dict)  # гидрация
order.ensure_owned_by(cmd.user_id)           # domain guard
amount = order.ensure_can_pay_remaining()    # domain guard + возвращает сумму
```

Хендлер **не** проверяет бизнес-правила сам — он вызывает методы сущности.

## Контракт application↔presentation

Хендлеры команд возвращают **wrapped dict** с осмысленным ключом, а не голый ORM-результат:

```python
return {"order": updated}                          # cancellation
return {"order": order_dict, "payment": payment}   # pay_remaining
return {"payment": ..., "scheduleItem": ...}       # pay_schedule_item
return {"orders": [...], "widgetData": ..., ...}   # create_purchase_orders
```

Это унифицировано после фикса #17 — присматривай за консистентностью при добавлении новых хендлеров.

## Ошибки

Два типа:

- **`DomainError`** (из `domain/errors.py`) — бросаются доменными сущностями. Без HTTP-кодов.
- **`ServiceError`** (из `application/errors.py`) — бросаются хендлерами для инфра-ситуаций. Несут `status_code`.

`domain_to_http(exc)` маппит доменные ошибки в HTTP-коды. Роутер ловит оба типа: `except (ServiceError, DomainError) as exc: raise _http(exc)`.

## Транзакции

- `session.commit()` — **в роутере**, не в хендлере. Хендлер делает `session.flush()` если нужен `id` до возврата.
- Если хендлер должен вызвать внешний шлюз (ModulBank) и записать ответ — flush до вызова, коммит после возврата управления роутеру.
- Откаты — через router-ское `try/except`, которое делает `session.rollback()` при `(ServiceError, DomainError)` или необработанном исключении.

## Auth (`commands/auth.py`)

- Двухшаговая OTP-аутентификация: `login` → SMS-код → `verify-phone`.
- SMS отправляются через `_fire_sms()` (fire-and-forget `asyncio.create_task`). Tasks хранятся в `_sms_tasks` set, чтобы event loop их не собрал.
- `_build_tokens()` создаёт `user_session` row, генерит токены через `infrastructure.auth.generate_tokens`, обновляет `refresh_token_hash`.
- `handle_refresh_token` — ротация: проверяет `sid` + `refresh_token_hash`, при mismatch удаляет сессию (reuse detection). `jti` пока не валидируется (TODO #47-tail требует Alembic-миграции).
- `handle_logout` удаляет `user_session` row.

## Notifications (`commands/notifications.py`)

- Авторизация — на presentation через `require_roles("carcraft_employee")`. Командный хендлер не проверяет роль.
- `mark_all_read` обёрнут в `try/except (ServiceError, DomainError)` в роутере (фикс #42).

## Email preferences

- **GET** — это query (`queries/email_preferences.py`), использует `get_or_default()` без записи в БД и без `commit()`. Раньше был get-with-side-effect (#38).
- **PUT** — `commands/email_preferences.py`, нормальное обновление.

## Правила

- Команды и хендлеры — в одном файле (нет отдельной `handlers/` директории).
- Хендлеры импортируют `infrastructure.repositories.*` напрямую и `infrastructure.services.payment_gateway` (последнее — TODO #14, нужен порт `PaymentGateway` в `domain/services` или `application/ports`).
- `await session.flush()` если нужен `id` до возврата управления роутеру.
- `# type: ignore[arg-type]` на `Entity.from_dict(repo_dict)` — допустимо, пока репо возвращает `TypedDict`.
