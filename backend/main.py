"""FastAPI gateway entry point."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi_limiter import FastAPILimiter
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from application.authentication import authenticate_access_token
from application.errors import DomainError, ServiceError
from infrastructure.cache import get_redis, shutdown_redis, startup_redis
from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
from infrastructure.logging import configure_logging
from infrastructure.messaging.broker import start_broker, stop_broker
from infrastructure.settings import settings
from presentation.api.v1.accounting_upload_router import (
    router as accounting_upload_router,
)
from presentation.dependencies.auth import _extract_token
from presentation.errors import (
    handle_domain_error,
    handle_http_exception,
    handle_service_error,
    handle_unhandled_exception,
    handle_validation_error,
)
from presentation.middleware.api_trailing_slash import ApiTrailingSlashMiddleware
from presentation.middleware.csrf import CSRFMiddleware
from presentation.middleware.request_timing import RequestTimingMiddleware
from presentation.middleware.security_headers import SecurityHeadersMiddleware
from presentation.openapi_filter import build_role_openapi_schemas
from presentation.openapi_special_equipment_management import (
    enrich_special_equipment_management_openapi,
)
from presentation.routers.accounting import router as accounting_router
from presentation.routers.additional_options import (
    router as additional_options_router,
)
from presentation.routers.admin_application_vehicles import (
    router as admin_application_vehicles_router,
)
from presentation.routers.admin_applications import (
    router as admin_applications_router,
)
from presentation.routers.admin_auth import router as admin_auth_router
from presentation.routers.admin_calculator_rates import (
    router as admin_calculator_rates_router,
)
from presentation.routers.admin_companies import (
    router as admin_companies_router,
)
from presentation.routers.admin_signatures import (
    router as admin_signatures_router,
)
from presentation.routers.admin_stats import router as admin_stats_router
from presentation.routers.admin_storefront_pages import (
    builder_media_router as admin_storefront_builder_media_router,
)
from presentation.routers.admin_storefront_pages import (
    router as admin_storefront_pages_router,
)
from presentation.routers.admin_support import router as admin_support_router
from presentation.routers.admin_warehouses import (
    router as admin_warehouses_router,
)
from presentation.routers.analytics import router as analytics_router
from presentation.routers.application_status_funnel import (
    router as application_status_funnel_router,
)
from presentation.routers.application_vehicle_assignments import (
    router as application_vehicle_assignments_router,
)
from presentation.routers.application_vehicles import (
    router as application_vehicles_router,
)
from presentation.routers.applications import router as applications_router
from presentation.routers.auth import router as auth_router
from presentation.routers.bank_statements import router as bank_statements_router
from presentation.routers.calculator import router as calculator_router
from presentation.routers.cart import router as cart_router
from presentation.routers.citizenship import router as citizenship_router
from presentation.routers.client import router as client_router
from presentation.routers.commerce import router as commerce_router
from presentation.routers.commerce import (
    storefront_router as storefront_commerce_router,
)
from presentation.routers.companies import router as companies_router
from presentation.routers.company_lookup import router as company_lookup_router
from presentation.routers.compensations import router as compensations_router
from presentation.routers.data_imports import router as data_imports_router
from presentation.routers.dealer import router as dealer_router
from presentation.routers.dealer_leasing_applications import (
    router as dealer_leasing_applications_router,
)
from presentation.routers.dealer_options import (
    router as dealer_options_router,
)
from presentation.routers.distributor import router as distributor_router
from presentation.routers.distributor_analytics import (
    router as distributor_analytics_router,
)
from presentation.routers.document_registry import router as document_registry_router
from presentation.routers.documents import router as documents_router
from presentation.routers.email_preferences import (
    router as email_preferences_router,
)
from presentation.routers.employees import router as employees_router
from presentation.routers.exchange_bids import (
    router as exchange_bids_router,
)
from presentation.routers.exchange_cart import (
    router as exchange_cart_router,
)
from presentation.routers.exchange_requests import (
    router as exchange_requests_router,
)
from presentation.routers.exchange_requests_dealer import (
    router as exchange_requests_dealer_router,
)
from presentation.routers.exchange_requests_distributor import (
    router as exchange_requests_distributor_router,
)
from presentation.routers.fast_deals import router as fast_deals_router
from presentation.routers.fast_deals import vin_lookup_router as fast_deals_vin_lookup_router
from presentation.routers.identity_verification import (
    router as identity_verification_router,
)
from presentation.routers.leasing import router as leasing_router
from presentation.routers.leasing_company_applications import (
    router as lca_router,
)
from presentation.routers.monetization import router as monetization_router
from presentation.routers.notifications import router as notifications_router
from presentation.routers.organization_support import (
    router as organization_support_router,
)
from presentation.routers.payments import router as payments_router
from presentation.routers.positions import router as positions_router
from presentation.routers.purchases import router as purchases_router
from presentation.routers.questionnaire import router as questionnaire_router
from presentation.routers.questionnaire_dictionaries import (
    router as questionnaire_dictionaries_router,
)
from presentation.routers.section_visibility import (
    router as section_visibility_router,
)
from presentation.routers.signatures import router as signatures_router
from presentation.routers.special_equipment import router as special_equipment_router
from presentation.routers.special_equipment_commerce import (
    router as special_equipment_commerce_router,
)
from presentation.routers.special_equipment_imports import (
    router as special_equipment_imports_router,
)
from presentation.routers.special_equipment_management import (
    router as special_equipment_management_router,
)
from presentation.routers.storefront_fonts import router as storefront_fonts_router
from presentation.routers.storefront_pages import router as storefront_pages_router
from presentation.routers.storefronts import router as storefronts_router
from presentation.routers.users import router as users_router
from presentation.routers.warehouse_transfers import (
    router as warehouse_transfers_router,
)
from presentation.routers.well_known import router as well_known_router


def _setup_logging() -> None:
    configure_logging(service_name="carcraft-api")


_setup_logging()
logger = logging.getLogger("carcraft-backend")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    load_and_validate_key_configuration()
    from infrastructure.services.catalog_image_fetchers import (
        _client as catalog_image_client,
    )

    await startup_redis()
    if settings.tracemalloc_enabled:
        import tracemalloc

        if not tracemalloc.is_tracing():
            tracemalloc.start()
        current, peak = tracemalloc.get_traced_memory()
        logger.info(
            "tracemalloc started current=%.2fMB peak=%.2fMB",
            current / 1024 / 1024,
            peak / 1024 / 1024,
        )
    await catalog_image_client.start()
    # API process is a producer only: faststream consumers run in the
    # event-worker service and taskiq-scheduled jobs (compensation
    # sweeps, audit log retention, payment expiry) run in the
    # taskiq-worker service. This process does NOT import consumer
    # modules or application.tasks — it just serves HTTP and publishes
    # events.
    await start_broker()
    await _init_rate_limiter()
    await _warmup_blank_sopd()
    yield
    await stop_broker()
    await catalog_image_client.stop()
    await shutdown_redis()


async def _init_rate_limiter() -> None:
    """Wire fastapi-limiter to the shared Redis client."""
    if not settings.rate_limit_enabled:
        return
    await FastAPILimiter.init(get_redis())


async def _warmup_blank_sopd() -> None:
    """Enqueue a blank СОПД render so the first `/documents/sopd/download`
    hits a warm cache instead of a 202 retry loop. Idempotent: the task
    short-circuits when the ``(template_hash, context_hash)`` row already
    exists, and the template hash changes only when ``sopd.md``
    itself changes.
    """
    from application.tasks.sopd import render_sopd_pdf

    try:
        await render_sopd_pdf.kiq({})
    except Exception:
        logger.exception("Failed to enqueue blank СОПД warmup")


_openapi_tags = [
    {
        "name": "health",
        "description": "Проверка доступности сервиса.",
    },
    {
        "name": "auth",
        "description": (
            "Аутентификация по номеру телефона (OTP). "
            "Двухшаговый вход: отправка SMS-кода → верификация. "
            "Токены хранятся в httpOnly cookies `accessToken` / `refreshToken`."
        ),
    },
    {
        "name": "admin-auth",
        "description": (
            "Административные операции над сессиями пользователей "
            "(просмотр, принудительный logout, деактивация). "
            "Требуют scope `auth:admin`."
        ),
    },
    {
        "name": "purchases",
        "description": (
            "Управление заказами на покупку/бронирование автомобилей. "
            "Создание заказов, просмотр истории, оплата по графику, отмена. "
            "Требует JWT-токен; права зависят от роли (`client` / `carcraft_employee`)."
        ),
    },
    {
        "name": "commerce",
        "description": (
            "Единый типизированный facade для автомобилей и спецтехники: "
            "заказы, лизинговые заявки, платежи, графики и отмена без "
            "смешивания FK двух каталогов."
        ),
    },
    {
        "name": "payments",
        "description": (
            "Webhook-колбэки от платёжных систем (ModulBank, ModulKassa). "
            "Эндпоинты не требуют JWT — авторизация выполняется по подписи запроса."
        ),
    },
    {
        "name": "company",
        "description": (
            "Поиск внешних компаний по названию или ИНН. "
            "Провайдер-агностичный API — формат ответа не зависит "
            "от конкретного источника данных."
        ),
    },
    {
        "name": "email-preferences",
        "description": ("Настройки email-уведомлений пользователя."),
    },
    {
        "name": "notifications",
        "description": (
            "Внутренние уведомления пользователя (инбокс). "
            "Просмотр/пометка/удаление — только своих; создание — только сотрудникам."
        ),
    },
    {
        "name": "section-visibility",
        "description": (
            "Настройки видимости публичной и workspace-навигации. Публичная "
            "матрица доступна без входа, управление — сотрудникам Carcraft."
        ),
    },
    {
        "name": "compensations",
        "description": (
            "Управление компенсациями по субсидиям. "
            "Создание, просмотр, пересчёт и обновление статусов компенсаций. "
            "Реестр компенсаций с ролевой видимостью."
        ),
    },
    {
        "name": "accounting",
        "description": (
            "Бухгалтерская отчётность компаний (баланс, ОФР, cash flow) "
            "по ИНН. Провайдер-агностичный формат — источник данных "
            "(Parser API / Kontur / SPARK) прозрачен для клиента."
        ),
    },
    {
        "name": "well-known",
        "description": (
            "Публичные discovery-эндпоинты (RFC 5785). "
            "Содержит JWKS — публичные ключи для проверки подписи JWT."
        ),
    },
    {
        "name": "users",
        "description": (
            "Компании, привязанные к пользователю, и выбор текущей "
            "компании для пользовательского контекста."
        ),
    },
    {
        "name": "companies",
        "description": (
            "Профили компаний (карточки заказчиков, лизинговых компаний, "
            "дистрибьюторов). Чтение по идентификатору или для текущего "
            "пользователя через `users.company_id`."
        ),
    },
    {
        "name": "calculator",
        "description": (
            "Калькулятор лизинга: расчёт ежемесячного платежа, программ "
            "поддержки, история. Эндпоинты `/calculate` и `/support-status` "
            "поддерживают опциональную авторизацию; `/history` требует JWT."
        ),
    },
    {
        "name": "admin-support",
        "description": (
            "Администрирование программ поддержки субсидий и групп дилеров. "
            "Включая загрузку накладных (Bill of Lading) — PDF / DOC / DOCX / PPTX. "
            "Доступно только сотрудникам (`carcraft_employee`)."
        ),
    },
    {
        "name": "client",
        "description": (
            "Профиль клиента, избранные автомобили, сохранённые расчёты, "
            "смена номера телефона по SMS. Доступно ролям `client` и "
            "`carcraft_employee`."
        ),
    },
    {
        "name": "distributor",
        "description": (
            "Кабинет распределителя: автомобили в скоупе, заявки, "
            "сводка по складу, массовый импорт из Excel и массовое "
            "обновление цен/статусов. Доступно ролям `distributor` и "
            "`carcraft_employee`."
        ),
    },
    {
        "name": "applications",
        "description": (
            "Заявки на лизинг: создание, списки, детали, смена статуса, "
            "назначение VIN и отправка документов на рассмотрение. "
            "Ролевая видимость: клиент/дилер/LC видят только свои, "
            "сотрудник — все."
        ),
    },
    {
        "name": "documents",
        "description": (
            "Документы: загрузка, версионирование, статусы, требования. "
            "S3-хранилище + fire-and-forget распознавание паспортов. "
            "Владелец/роль проверяются на уровне доменной сущности."
        ),
    },
    {
        "name": "leasing",
        "description": (
            "Кабинет лизинговой компании: публичный справочник активных "
            "ЛК, очередь заявок на ревью и действия approve/reject/"
            "request-documents. Доступно роли `leasing_company` и "
            "`carcraft_employee`."
        ),
    },
    {
        "name": "cart",
        "description": (
            "Корзина автомобилей: CRUD позиций (`(user_id, vehicle_id)`), "
            "selection/quantity/custom_price/comment. Доступно ролям "
            "`dealer`, `client`, `carcraft_employee`. Кастомная цена — "
            "только для `dealer` и `carcraft_employee`."
        ),
    },
]

app = FastAPI(
    title="Carcraft Lead Generator API",
    description="API Gateway for Carcraft Lead Generator",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    openapi_tags=_openapi_tags,
    lifespan=lifespan,
)

# Keep slash normalization closest to the router so retries do not repeat
# auth, CSRF, timing, CORS, or metrics middleware.
app.add_middleware(ApiTrailingSlashMiddleware, router=app.router)

Instrumentator(
    should_group_status_codes=False,
    should_group_untemplated=False,
    excluded_handlers=["/metrics", "/api/v1/health"],
).instrument(app).expose(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_origin_regex=None
    if settings.cookie_secure
    else ".*",  # Allow all origins for non-secure cookies (dev only); in prod, CORS preflight must match the specific allowed origins.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "X-Request-ID"],
)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# Starlette wraps middleware in reverse registration order. Timing is added
# last so request correlation and the sole HTTP summary also cover responses
# returned directly by CORS, CSRF, and security middleware.
app.add_middleware(RequestTimingMiddleware)


@app.get("/api/v1/health", tags=["health"])
async def health() -> JSONResponse:
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "service": "fastapi-gateway"})


# Unprefixed discovery endpoints (e.g. /.well-known/jwks.json)
app.include_router(well_known_router)

# Native FastAPI routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(admin_auth_router, prefix="/api/v1/admin/auth", tags=["admin-auth"])
app.include_router(purchases_router, prefix="/api/v1/purchases", tags=["purchases"])
app.include_router(commerce_router, prefix="/api/v1/commerce", tags=["commerce"])
app.include_router(
    identity_verification_router,
    prefix="/api/v1",
    tags=["identity-verification"],
)
app.include_router(users_router, prefix="/api/v1/users", tags=["users"])
app.include_router(positions_router)
app.include_router(employees_router)
app.include_router(payments_router, prefix="/api/v1/payments", tags=["payments"])
app.include_router(company_lookup_router, prefix="/api/v1/company", tags=["company"])
app.include_router(citizenship_router, prefix="/api/v1/citizenship", tags=["citizenship"])
app.include_router(
    email_preferences_router,
    prefix="/api/v1/email-preferences",
    tags=["email-preferences"],
)
app.include_router(
    notifications_router,
    prefix="/api/v1/notifications",
    tags=["notifications"],
)
app.include_router(
    section_visibility_router,
    prefix="/api/v1",
    tags=["section-visibility"],
)
# Fast deal registration (Bitrix 22152). The VIN lookup sits under the special-equipment
# prefix; both routers are authenticated and mounted before the public catalog routes.
app.include_router(
    fast_deals_vin_lookup_router,
    prefix="/api/v1/special-equipment/catalog",
    tags=["fast-deals"],
)
app.include_router(
    fast_deals_router,
    prefix="/api/v1/fast-deals",
    tags=["fast-deals"],
)
app.include_router(
    special_equipment_router,
    prefix="/api/v1/special-equipment",
    tags=["special-equipment"],
)
app.include_router(
    special_equipment_commerce_router,
    prefix="/api/v1/special-equipment",
    tags=["special-equipment-commerce"],
)
app.include_router(
    special_equipment_router,
    prefix="/api/v1/storefronts/{storefront_slug}/special-equipment",
    tags=["storefront-special-equipment"],
)
app.include_router(
    special_equipment_commerce_router,
    prefix="/api/v1/storefronts/{storefront_slug}/special-equipment",
    tags=["storefront-special-equipment-commerce"],
)
app.include_router(
    special_equipment_imports_router,
    prefix="/api/v1",
)
app.include_router(
    special_equipment_management_router,
    prefix="/api/v1/admin/special-equipment",
    tags=["special-equipment-management"],
)
app.include_router(data_imports_router)
app.include_router(
    compensations_router, prefix="/api/v1/compensations", tags=["compensations"]
)
app.include_router(accounting_router, prefix="/api/v1/accounting", tags=["accounting"])
app.include_router(
    accounting_upload_router, prefix="/api/v1/accounting", tags=["accounting"]
)
app.include_router(
    bank_statements_router,
    prefix="/api/v1/bank-statements",
    tags=["bank-statements"],
)
app.include_router(companies_router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(signatures_router, prefix="/api/v1/signatures", tags=["signatures"])
app.include_router(
    admin_signatures_router, prefix="/api/v1/admin", tags=["admin-signatures"]
)
app.include_router(calculator_router, prefix="/api/v1/calculator", tags=["calculator"])
app.include_router(
    additional_options_router,
    prefix="/api/v1",
    tags=["additional-options"],
)
app.include_router(admin_support_router, prefix="/api/v1/admin", tags=["admin-support"])
app.include_router(
    organization_support_router,
    prefix="/api/v1",
    tags=["organization-support"],
)
app.include_router(
    admin_warehouses_router, prefix="/api/v1/admin", tags=["admin-warehouses"]
)
app.include_router(
    admin_warehouses_router, prefix="/api/v1", tags=["warehouses"]
)
app.include_router(
    dealer_options_router,
    prefix="/api/v1/exchange/dealer-options",
    tags=["dealer-options"],
)
app.include_router(client_router, prefix="/api/v1/client", tags=["client"])

app.include_router(
    admin_application_vehicles_router,
    prefix="/api/v1/admin",
    tags=["admin-application-vehicles"],
)
app.include_router(
    admin_calculator_rates_router,
    prefix="/api/v1/admin",
    tags=["admin-calculator-rates"],
)

# Admin residual CRUD (Phase 6 — F2) — companies / stats
# directories / applications listing & LC assignment. Employee-only.
# ``/admin/users`` was consolidated into ``/users`` in Phase 13 R13b —
# list/create/patch/delete now live on the main ``users_router``.
app.include_router(
    admin_companies_router,
    prefix="/api/v1/admin/companies",
    tags=["admin-companies"],
)
app.include_router(
    admin_applications_router,
    prefix="/api/v1/admin/applications",
    tags=["admin-applications"],
)
app.include_router(admin_stats_router, prefix="/api/v1/admin", tags=["admin-stats"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(
    application_status_funnel_router,
    prefix="/api/v1/analytics",
    tags=["analytics"],
)

app.include_router(storefronts_router, tags=["storefronts"])
app.include_router(storefront_fonts_router, tags=["storefront-fonts"])
app.include_router(
    admin_storefront_pages_router,
    prefix="/api/v1/admin/storefronts/{storefront_id}/pages",
    tags=["admin-storefront-pages"],
)
app.include_router(
    admin_storefront_builder_media_router,
    tags=["admin-storefront-pages"],
)
app.include_router(
    storefront_pages_router,
    tags=["storefront-pages"],
)
app.include_router(
    cart_router,
    prefix="/api/v1/storefronts/{storefront_slug}/cart",
    tags=["storefront-cart"],
)
app.include_router(
    client_router,
    prefix="/api/v1/storefronts/{storefront_slug}/client",
    tags=["storefront-client"],
)
app.include_router(
    applications_router,
    prefix="/api/v1/storefronts/{storefront_slug}/applications",
    tags=["storefront-applications"],
)
app.include_router(
    storefront_commerce_router,
    prefix="/api/v1/storefronts/{storefront_slug}/commerce",
    tags=["storefront-commerce"],
)

# Distributor cabinet — vehicles + applications + bulk Excel import.
# Requires `vehicles:admin` scope; in-handler scoping further
# restricts distributor users to their own vehicles.
app.include_router(
    distributor_router, prefix="/api/v1/distributor", tags=["distributor"]
)
app.include_router(
    warehouse_transfers_router,
    prefix="/api/v1/distributor/warehouse-transfers",
    tags=["distributor"],
)
app.include_router(
    distributor_analytics_router,
    prefix="/api/v1/distributor/analytics",
    tags=["distributor"],
)

# Leasing applications — Phase 3 aggregate root. Clients, dealers and
# employees create and read applications here; leasing companies see
# applications where their LC was selected. Ownership is enforced in
# the domain entity.
app.include_router(
    application_vehicle_assignments_router,
    prefix="/api/v1",
    tags=["application-vehicle-assignments"],
)
app.include_router(
    applications_router,
    prefix="/api/v1/applications",
    tags=["applications"],
)
app.include_router(
    dealer_leasing_applications_router,
    prefix="/api/v1/dealer/leasing-applications",
    tags=["dealer-leasing-applications"],
)
app.include_router(
    application_vehicles_router,
    prefix="/api/v1/application-vehicles",
    tags=["application-vehicles"],
)

# Documents (Phase 4 D1) — CRUD + S3 + versioning + document recognition.
# Owner / role visibility is enforced inside handlers via the Document
# aggregate.
app.include_router(
    documents_router,
    prefix="/api/v1/documents",
    tags=["documents"],
)

# LeasingCompanyApplications (LCA) — child application list/detail.
app.include_router(
    lca_router,
    prefix="/api/v1/leasing-company-applications",
    tags=["lca"],
)

# Leasing LC workflow (Phase 4 D3) — directory of active LCs plus the
# LC cabinet (review queue, approve / reject / request-documents).
app.include_router(
    leasing_router,
    prefix="/api/v1/leasing",
    tags=["leasing"],
)

# Cart (Phase 5 — E1) — per-user shopping cart (dealer / client / employee).
app.include_router(
    cart_router,
    prefix="/api/v1/cart",
    tags=["cart"],
)

# Dealer cabinet (Phase 5 — E3) — invite-client + dealer-scoped vehicles /
# applications.
app.include_router(
    dealer_router,
    prefix="/api/v1/dealer",
    tags=["dealer"],
)

# Exchange subsystem (Phase 5 — E2) — биржа транспортных средств.
# DealerOptions are mounted above under /api/v1/exchange/dealer-options (A4).
# The dealer-view router MUST mount before the LC router so `/requests/dealer*`
# matches the dealer prefix before the catch-all `/{request_id}` path converter.
app.include_router(exchange_requests_distributor_router,
    prefix="/api/v1/exchange/distributor/requests", tags=["exchange"])
app.include_router(
    exchange_requests_dealer_router,
    prefix="/api/v1/exchange/requests/dealer",
    tags=["exchange"],
)
app.include_router(
    exchange_requests_router,
    prefix="/api/v1/exchange/requests",
    tags=["exchange"],
)
app.include_router(
    exchange_bids_router,
    prefix="/api/v1/exchange/bids",
    tags=["exchange"],
)
app.include_router(
    exchange_cart_router,
    prefix="/api/v1/exchange/cart",
    tags=["exchange"],
)

# Legacy /questionnaire/:id path — upsert of per-application
# legal-entity questionnaire. Thin wrapper over the LC aggregate root.
app.include_router(
    questionnaire_router,
    prefix="/api/v1/questionnaire",
    tags=["applications"],
)


app.include_router(monetization_router, tags=["monetization"])
app.include_router(document_registry_router)
app.include_router(questionnaire_dictionaries_router)

# ---------------------------------------------------------------------------
# Role-filtered OpenAPI schema
#
# FastAPI generates a single openapi.json by default. We override the
# endpoint so that each role receives a schema containing only the routes
# it is authorised to call.  The filter is built once at startup by
# introspecting ``require_scopes`` / ``require_roles`` dependencies on
# every registered route.
# ---------------------------------------------------------------------------

# Remove the default openapi route so our custom handler takes precedence.
for _i, _route in enumerate(list(app.routes)):
    if getattr(_route, "path", None) == app.openapi_url:
        app.routes.pop(_i)
        break

_OPENAPI_PREFIX_OVERRIDES: dict[str, frozenset[str]] = {
    "/api/v1/client": frozenset({"client", "carcraft_employee"}),
    "/api/v1/dealer": frozenset({"dealer", "carcraft_employee"}),
    "/api/v1/exchange/cart": frozenset({"leasing_company"}),
    "/api/v1/exchange/requests/dealer": frozenset({"dealer"}),
}

_base_openapi_schema = enrich_special_equipment_management_openapi(app.openapi())
_ROLE_OPENAPI_SCHEMAS = build_role_openapi_schemas(
    app, _base_openapi_schema, prefix_overrides=_OPENAPI_PREFIX_OVERRIDES
)
_PUBLIC_OPENAPI_SCHEMA = _ROLE_OPENAPI_SCHEMAS.get(None, _base_openapi_schema)


@app.get("/api/v1/openapi.json", include_in_schema=False)
async def _openapi_json(request: Request) -> JSONResponse:
    token, source = _extract_token(
        access_token=request.cookies.get("accessToken"),
        authorization=request.headers.get("authorization"),
    )
    role: str | None = None
    if token:
        try:
            user = await authenticate_access_token(token)
            # Bearer auth is gated to external_api role in the auth dependency.
            if source != "bearer" or user.get("role") == "external_api":
                role = user.get("role")
        except Exception as _exc:
            logger.debug("Failed to decode token for openapi.json: %s", _exc)
    schema = _ROLE_OPENAPI_SCHEMAS.get(role, _PUBLIC_OPENAPI_SCHEMA)
    return JSONResponse(schema)


# ---------------------------------------------------------------------------
# Global exception handlers — every client-facing error follows the same
# canonical shape {"detail": "...", "code": "..."} with Russian text.
# ---------------------------------------------------------------------------
_ExcHandler = Callable[[Any, Any], Awaitable[JSONResponse]]
app.add_exception_handler(DomainError, cast("_ExcHandler", handle_domain_error))
app.add_exception_handler(ServiceError, cast("_ExcHandler", handle_service_error))
app.add_exception_handler(
    RequestValidationError, cast("_ExcHandler", handle_validation_error)
)
# StarletteHTTPException is the base for FastAPI's HTTPException.
app.add_exception_handler(
    StarletteHTTPException, cast("_ExcHandler", handle_http_exception)
)
# Fallback — should never happen in practice; catches anything else.
app.add_exception_handler(Exception, handle_unhandled_exception)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3002)
