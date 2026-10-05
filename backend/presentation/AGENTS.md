# Presentation Layer

HTTP-слой: роутеры, схемы, валидация входящих данных, документация. Тонкая прослойка над `application/`.

## Структура

```text
presentation/
├── dependencies/
│   └── auth.py             # get_current_user (JWT-only), get_current_user_with_db, require_roles(*roles)
├── routers/
│   ├── auth.py             # /api/v1/auth/* — login, register, verify-phone, refresh, logout, me, resend-code
│   ├── purchases.py        # /api/v1/purchases/* — orders, payments, cancellation, schedule
│   ├── payments.py         # /api/v1/payments/webhook/* — ModulBank, ModulKassa
│   ├── notifications.py    # /api/v1/notifications/* — inbox + admin create
│   ├── email_preferences.py# /api/v1/email-preferences (GET/PUT)
│   ├── company_lookup.py   # /api/v1/company/* — public lookup (Dadata)
│   └── vehicle_images.py   # /api/v1/* — upload/delete car images
└── schemas/
    ├── auth.py             # LoginRequest, RegisterRequest, AuthResponse, MeResponse, ...
    ├── purchases.py        # Все purchase-схемы (Decimal для денег)
    ├── payments.py         # WebhookResponse
    ├── notifications.py    # CreateNotificationRequest, NotificationResource, ...
    ├── email_preferences.py# EmailPreferencesPayload, *Response
    ├── company_lookup.py
    └── vehicle_images.py
```

## Auth dependencies (`dependencies/auth.py`)

Два варианта (фикс #20 — fast path без БД):

- **`get_current_user`** — JWT-only, никакого DB roundtrip. Декодирует token, возвращает payload как dict (`{id, role, company_id, ...}`). Для большинства роутов этого достаточно.
- **`get_current_user_with_db`** — для эндпоинтов вроде `/me`, где нужен свежий снапшот пользователя из БД.
- **`require_roles(*roles)`** — фабрика, возвращает dependency-проверяльщик. Обёрнут вокруг `get_current_user` (без БД).

```python
@router.post("", dependencies=[Depends(require_roles("carcraft_employee"))])
```

Авторизация унифицирована (фикс #30/#44): роли проверяются здесь, не в командных хендлерах.

## Правила роутеров

**Каждый эндпоинт обязан иметь:**

- `response_model=` — Pydantic-схема из `schemas/`
- `summary=` — короткое название (Swagger list)
- `description=` — что делает, что возвращает, роли, особые случаи

**Это касается даже webhook'ов** — `routers/payments.py` имеет полные метаданные на `/webhook/modulbank` и `/webhook/modulkassa` (фикс #31).

**Cookies (`auth.py:_set_auth_cookies`):**

```python
response.set_cookie(
    key="accessToken", value=access_token, httponly=True,
    secure=settings.cookie_secure,        # default True (фикс #10)
    samesite=settings.cookie_samesite,    # фикс #27
    path="/",                             # явно (фикс #26)
    max_age=...,
)
```

`delete_cookie(..., path="/")` — тоже с path.

## Обработка ошибок

```python
def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))

try:
    result = await handle_*(...)
except (ServiceError, DomainError) as exc:
    raise _http(exc)
await session.commit()
```

`session.commit()` — **в роутере**, не в хендлере. На исключении до `commit` — router сам сделает `rollback` через зависимость `get_db`.

## Webhook'и (`routers/payments.py`)

- **Не требуют JWT.** Авторизация — по подписи (SHA-1 double-hash, проверяется внутри `payment_gateway.verify_modulbank_signature`).
- **Всегда возвращают HTTP 200**, даже на ошибках, чтобы ModulBank не повторял (он может слать webhooks по 50 раз).
- На ошибках в теле — `{"ok": False, "processed": False, "error_code": "INVALID_PAYLOAD" | "PROCESSING_ERROR"}`. Текст исключения наружу не уходит (фикс #9/#33).
- `start_fiscalization_task` вызывается **после** `commit` и **вне** основного `try/except` (обёрнут собственным catch-and-log) — чтобы случайное падение шедулера не откатило уже зафиксированный платёж (фикс #50).

## REST conventions

- **POST** create → `201` + `Location: /api/v1/<resource>/{id}` + полное тело.
- **GET** list → `200` + `{ items: [...], pagination: {...} }`.
- **PATCH** partial update → `200` + обновлённый ресурс.
- **PATCH** collection (например, `mark-all-read`) → `204 No Content`.
- **DELETE** → `204 No Content`.
- **Никаких `{ success: true, ... }` обёрток.** Status code несёт успех.
- Предпочитать **PATCH** над **PUT** для частичных обновлений.

## Возврат ответов

Все эндпоинты возвращают `JSONResponse(content=jsonable_encoder(...))`. `response_model` используется **только** для документации — FastAPI не валидирует `JSONResponse`.

## Порядок регистрации в `main.py`

Роутеры регистрируются в `main.py` в логическом порядке. Статичные маршруты с явными путями идут первыми; маршруты с path-параметрами и широкими префиксами — позже, чтобы не перехватывать более специфичные пути.

## Чего не делать

- Не реализовывать бизнес-логику — только вызов хендлеров из `application/`.
- Не обращаться к БД напрямую — через `get_db` dependency и application-хендлеры.
- Не проверять роли вручную в роутере — использовать `require_roles(...)`.
