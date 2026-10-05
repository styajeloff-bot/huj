# Domain Layer

Бизнес-правила, сущности, value objects, ошибки. Ядро приложения — **не зависит ни от какого другого слоя**, не делает I/O.

## Структура

```text
domain/
├── values.py               # Enums: OrderStatus, PurchaseType, PaymentStatus, PaymentMethod, PaymentType, VehicleStatus
├── errors.py               # Доменные ошибки (без HTTP-кодов)
├── entities/
│   ├── purchase_order.py   # PurchaseOrder — aggregate root, status guards, ownership
│   ├── payment.py          # Payment — gateway helpers; validate_schedule_item()
│   ├── notification.py     # Notification — ownership check
│   └── proxy.py            # ProxyRequest, ProxyResponse (legacy proxy)
├── events/
│   └── proxy.py            # RequestProxied, RequestFailed (legacy proxy)
└── services/               # Provider Protocols (port в DDD-смысле)
    ├── object_storage.py        # ObjectStorage — S3-like adapter
    ├── company_lookup.py        # CompanyLookupProvider — Dadata и т.п.
    └── company_enrichment.py    # CompanyEnrichmentScheduler
```

## Ключевые сущности

### PurchaseOrder

Обычный `@dataclass` (раньше наследовался от `Aggregate`, сейчас этот мёртвый код удалён, см. фикс #12).

- `compute_amounts(purchase_type, total_price, use_gateway, down_payment_percent)` — расчёт суммы платежа, статуса, paid/remaining. Всё в `Decimal`.
- `ensure_owned_by(user_id)` — `AccessDeniedError` если чужой.
- `ensure_can_pay_remaining()` → `Decimal` — guard + возвращает сумму к оплате.
- `ensure_can_request_cancellation()`, `ensure_can_approve_cancellation()`, `ensure_can_pay_schedule()`, `ensure_has_schedule()`.
- `target_vehicle_status(purchase_type)` — `RESERVED` / `SOLD`.
- `from_dict(data)` — гидрация из dict'а репозитория (игнорит лишние ключи).

### Payment

- `uses_gateway(method)` — нужен ли шлюз.
- `initial_status(use_gateway)` — `pending` vs `processing`.
- `compute_expiry(use_gateway)` — дата истечения для pending payment.
- `PAYMENT_EXPIRY_MINUTES = 30`.

### `validate_schedule_item(item, order_id) -> item`

Generic-функция: проверяет invariants графика лизинга и **возвращает** валидированный item с сохранением типа (`ScheduleItemDict` остаётся `ScheduleItemDict`). Бросает `ScheduleItem*Error` при нарушении.

### Notification

- `ensure_owned_by(user_id)` — IDOR-защита для `mark_read` / `delete`.
- `from_dict(data)` — гидрация.

## Provider Protocols (`domain/services/`)

Чистые `Protocol` без I/O. Используются в `application/` (TODO: пока часть импортов идёт напрямую в `infrastructure.services.*`, см. #14). Конкретные адаптеры — в `infrastructure/services/`.

- `ObjectStorage` — `upload`, `delete`, `presigned_url`.
- `CompanyLookupProvider` — `search_by_name`, `search_by_inn`. Реализация: Dadata.
- `CompanyEnrichmentScheduler` — фоновая дозагрузка данных по ИНН.

## Ошибки (`errors.py`)

Доменные ошибки **не знают про HTTP**. Маппинг — в `application/errors.py:domain_to_http()`.

| Ошибка | HTTP |
| --- | --- |
| `OrderNotFoundError`, `VehicleNotFoundError`, `PaymentNotFoundError`, `NotificationNotFoundError` | 404 |
| `AccessDeniedError` | 403 |
| `VehicleNotAvailableError`, `InsufficientVehiclesError` | 409 |
| `InvalidOrderStatusError`, `ScheduleItemAlreadyPaidError`, `ScheduleItemMismatchError` | 400 |
| `UserNotFoundError` | 404 |
| `UserAlreadyExistsError` | 409 |
| `UserDeactivatedError` | 403 |
| `InvalidVerificationCodeError` | 401 |
| `InvalidSignatureError` | 401 (webhooks) |

## Правила

- **Никаких зависимостей** на `application`, `infrastructure`, `presentation`. Это enforced через `lint-imports`.
- Чистые `@dataclass`, `Protocol`, enum — без side effects, без I/O.
- Деньги — `Decimal`, не `float`.
- Enums из `values.py` — единственный источник истины для статусов.
- Если сущности нужен I/O (отправить email и т.п.) — это use case в `application/`, не в domain.
