# Infrastructure Layer

Технические детали: БД, ORM-модели, репозитории, внешние сервисы, настройки. **Никогда** не импортирует из `application/` или `presentation/`.

## Структура

```text
infrastructure/
├── settings.py                 # Все env-переменные через pydantic-settings
├── database.py                 # async engine, AsyncSessionLocal, get_db dependency
├── auth.py                     # JWT helpers: generate_tokens, decode_*, hash_refresh_token
├── models/                     # SQLAlchemy ORM-модели (для Alembic и raw queries)
│   ├── payments.py             # PurchaseOrder, Payment, LeasingPaymentSchedule
│   ├── users.py                # User, UserSession, ClientProfile, ...
│   ├── vehicles.py             # Vehicle, Warehouse, ...
│   ├── catalog.py              # Mark, CarModel, Generation, Configuration, Modification
│   ├── companies.py            # Company, UserCompany, CompanySelectHistory, ...
│   ├── applications.py         # LeasingApplication
│   ├── documents.py            # Document
│   ├── email_preferences.py    # EmailPreference
│   ├── enums.py                # SQLAlchemy enum types
│   ├── misc.py                 # Notification, ...
│   └── subsidies.py
├── repositories/
│   ├── auth_repository.py                  # Users, sessions, verification codes
│   ├── purchase_repository.py              # Orders, payments, schedule, vehicles
│   ├── notification_repository.py
│   ├── email_preferences_repository.py     # get_or_default + update
│   ├── company_registration_repository.py  # create_or_get_company, user_companies
│   └── special_equipment_repository.py
└── services/
    ├── payment_gateway.py      # ModulBank: prepare_payment, request_sbp_link, webhook, fiscalization, expiry
    ├── payment_models.py       # Pydantic-схемы запросов/ответов ModulBank (amount: Decimal)
    ├── modulkassa.py           # ModulKassa: чеки
    ├── sms.py                  # SMS-провайдер: send_verification_sms, get_verification_code, is_test_phone
    ├── image_optimizer.py      # PIL-обработка
    ├── company_enrichment.py   # фоновая дозагрузка по ИНН (Dadata)
    ├── company_lookup/
    │   └── dadata.py           # реализация CompanyLookupProvider
    └── object_storage/         # S3-like adapter (реализация ObjectStorage)
```

## Ключевые правила

### Settings

Все `os.environ` / `os.getenv` **запрещены**. Только `from infrastructure.settings import settings` (pydantic-settings). Дефолты в `settings.py`, прод-overrides — через env.

### Репозитории

- Все методы возвращают `dict` / `list[dict]` (TypedDict для type hints), **никогда** ORM-объекты.
- Внутри — `_to_dict()` хелпер.
- Никаких ORM-объектов за пределами репозитория.
- Принимают `AsyncSession` параметром, **не вызывают** `commit()` сами.

### Модели

SQLAlchemy ORM — только для Alembic-миграций и raw queries. **Не использовать как DTO** между слоями.

### `expire_on_commit=False`

Намеренный инвариант в `database.py`:

- Репозитории отдают `dict`, поэтому экспайр ORM-инстансов после commit бесполезен и провоцирует `MissingGreenlet` в async-коде.
- **Если кто-то начнёт возвращать ORM-объекты** — либо `await session.refresh(obj)` после commit, либо включать `expire_on_commit=True`.

### Auth (`auth.py`)

- `generate_tokens(user_id, role, company_id, refresh_session_id)` → `(access, refresh)`. Access/refresh JWT подписываются ES256 ключом из `jwt_keys_dir` и всегда несут `kid`; HS256 access/refresh токены не поддерживаются.
- Refresh-токен включает `sid` (id `user_session`-row) и `jti` (random nonce).
- `hash_refresh_token` — SHA-256 для хранения в `user_session.refresh_token_hash`.
- Reuse detection — на стороне `application.commands.auth.handle_refresh_token`: при mismatch hash сессия удаляется.

### Payment gateway (`services/payment_gateway.py`)

Центральный сервис жизненного цикла платежа:

- `prepare_payment` / `request_sbp_link` — сборка payload + подпись + (для SBP) HTTP-запрос. **Не** пишут в БД до HTTP — `gateway_transaction_id` сохраняется в `application/commands/purchases.py` сразу после `create_payment` (фикс #15).
- `handle_payment_callback` — обработка вебхука: проверка SHA-1 double-hash подписи (`verify_modulbank_signature`), обновление платежа, заказа, статуса машины.
- `_complete_payment` / `_fail_payment` — внутренние транзакционные операции, всё в `Decimal` (фикс #13).
- `trigger_fiscalization` — переписан после фикса #48: цикл `for retry in range(FISCAL_MAX_RETRIES + 1)`, каждая попытка вынесена в `_fiscalization_attempt()` с **собственным** `async with AsyncSessionLocal()`. `await asyncio.sleep()` между ретраями происходит **без открытой сессии** — соединения из пула не удерживаются.
- `start_fiscalization_task` — fire-and-forget через `asyncio.create_task`, tasks хранятся в `_background_tasks` set чтобы event loop их не GC.
- `expire_stale_payments` — sweep, дёргается из `_payment_expiry_loop` в `main.py` каждые 60 секунд.

### Payment models (`services/payment_models.py`)

Все суммы — `Decimal`, **не** `float`. ModulBank принимает строку с точкой, urlencode сериализует `Decimal` корректно.
