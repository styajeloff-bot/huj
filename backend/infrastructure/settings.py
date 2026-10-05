"""Application settings loaded from environment variables."""
from functools import cached_property
from typing import Annotated, ClassVar, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    api_url: str = ""
    public_url: str = "https://test.multileasing.ru"
    e2e_base_url: str = "http://localhost"

    # Database
    database_url: str = ""
    db_user: str = ""
    db_password: str = ""
    db_host: str = ""
    db_port: int = 5432
    db_name: str = ""
    db_pool_size: int = 8
    db_max_overflow: int = 4
    db_pool_timeout: int = 30
    taskiq_max_async_tasks: int = 4
    taskiq_max_prefetch: int = 4
    taskiq_import_concurrency: int = 4

    # Auth
    jwt_access_secret: str = ""
    access_token_expiry_minutes: int = 30
    refresh_token_expiry_days: int = 7
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "strict"

    # Redis (cache/KV — JTI denylist, rate limiter, CSRF state if needed)
    redis_url: str = "redis://redis:6379/0"
    redis_connect_timeout_seconds: float = 3.0
    taskiq_broker_redis_socket_timeout_seconds: float | None = None
    # If Redis is unreachable, denylist defaults to fail-closed in prod.
    # Set to True only for local dev smoke-tests without Redis.
    auth_denylist_fail_open: bool = False

    # OTP lockout — how many consecutive wrong codes before the phone is
    # blocked from verifying further, and for how long.
    otp_max_failures: int = 5
    otp_lockout_window_seconds: int = 15 * 60

    # Rate limiting (fastapi-limiter, Redis-backed). All windows in seconds.
    rate_limit_enabled: bool = True
    rate_limit_login_per_minute: int = 5
    rate_limit_verify_per_minute: int = 10
    rate_limit_refresh_per_minute: int = 20
    rate_limit_resend_per_minute: int = 3
    rate_limit_register_per_minute: int = 5
    rate_limit_special_equipment_catalog_per_minute: int = 300
    special_equipment_cascade_delete_max_rows: int = 5000

    csrf_enabled: bool = False
    csrf_cookie_name: str = "csrfToken"
    csrf_header_name: str = "X-CSRF-Token"
    cors_allowed_origins_raw: str = Field(
        default="",
        validation_alias=AliasChoices("CORS_ALLOWED_ORIGINS", "ALLOWED_ORIGINS"),
    )

    # Catalog image fetch (shared httpx.AsyncClient)
    catalog_image_fetch_timeout: float = 30.0
    catalog_image_http_max_connections: int = 100
    catalog_image_http_max_keepalive: int = 50
    # Per-vehicle parallelism inside the image consumer (asyncio.Semaphore).
    catalog_image_concurrency_per_vehicle: int = 20
    # Batch size for the row + image consumers (FastStream batch=True).
    catalog_row_batch_size: int = 50
    catalog_image_batch_size: int = 16
    # Exact HTTPS hosts allowed to serve temporary special-equipment images.
    # This is intentionally not configurable via environment variables.
    special_equipment_image_source_hosts: ClassVar[frozenset[str]] = frozenset(
        {"drive.google.com", "drive.usercontent.google.com"}
    )
    special_equipment_import_image_concurrency: int = 4
    special_equipment_import_image_budget_seconds: int = 600

    # Image optimizer — max output dimensions (keeps aspect ratio, never upscales)
    image_max_width: int = Field(
        default=584,
        validation_alias=AliasChoices("IMAGE_MAX_WIDTH"),
    )
    image_max_height: int = Field(
        default=384,
        validation_alias=AliasChoices("IMAGE_MAX_HEIGHT"),
    )

    # ModulBank
    modulbank_shop_id: str = ""
    modulbank_secret_key: str = ""
    modulbank_form_url: str = "https://pay.modulbank.ru/pay"
    modulbank_sbp_api_url: str = "https://pay.modulbank.ru/api/v1/sbp_payment"
    modulbank_sbp_request_timeout: float = 15.0
    modulbank_default_client_email: str = "noreply@carcraft.ru"

    # Payment fiscalization / expiry
    # Delay (seconds) before each retry attempt. Number of retries = len(list).
    fiscalization_retry_delays_seconds: list[int] = [60, 300, 900]
    fiscalization_sent_stale_seconds: int = 15 * 60
    fiscalization_failed_retry_seconds: int = 60
    payment_expiry_sweep_interval_seconds: float = 60.0
    special_equipment_callback_lease_seconds: int = 5 * 60
    special_equipment_callback_retry_delays_seconds: list[int] = [30, 120, 600]

    # ModulKassa
    modulkassa_api_url: str = "https://service.modulkassa.ru/api/fn/v2"
    modulkassa_create_receipt_timeout: float = 30.0
    modulkassa_check_status_timeout: float = 15.0
    # Exact comma-separated hosts allowed to serve fiscal receipt PDFs.  The
    # hostname from ``modulkassa_api_url`` is always included automatically.
    modulkassa_receipt_source_hosts: str = ""
    modulkassa_receipt_download_timeout: float = 20.0
    modulkassa_receipt_max_bytes: int = 10 * 1024 * 1024
    modulkassa_receipt_max_redirects: int = 3
    modulkassa_receipt_retry_delays_seconds: list[int] = [10, 60, 300]
    modulkassa_receipt_processing_stale_seconds: int = 15 * 60
    modulkassa_login: str = ""
    modulkassa_password: str = ""
    modulkassa_cashier_name: str = "Ладыгина Ирина"
    modulkassa_cashier_position: str = "Главный бухгалтер"
    modulkassa_retail_point_id: str = ""
    modulkassa_callback_url: str = ""
    modulkassa_callback_token: str = ""
    # Configured tokens are always enforced. This flag additionally fails
    # closed when a production deployment accidentally omits the secret.
    modulkassa_callback_token_required: bool = False

    # SMTP (used for SMS gateway)
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_user: str = ""
    # Express uses SMTP_PASS; accept both names
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("SMTP_PASSWORD", "SMTP_PASS"),
    )

    # SMSC SMS gateway
    smsc_login: str = ""
    smsc_password: str = ""
    smsc_sender: str = ""

    # External company lookup (provider-agnostic; currently DaData)
    dadata_api_key: str = ""
    dadata_api_url: str = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
    dadata_request_timeout: float = 5.0

    # DBRAIN — passport / document recognition (provider-agnostic name kept
    # for legacy compatibility; new code should use `document_recognition_*`).
    document_recognition_host: str = Field(
        default="https://latest.dbrain.io",
        validation_alias=AliasChoices("DOCUMENT_RECOGNITION_HOST", "DBRAIN_HOST"),
    )
    document_recognition_token: str = Field(
        default="",
        validation_alias=AliasChoices("DOCUMENT_RECOGNITION_TOKEN", "DBRAIN_TOKEN"),
    )
    document_recognition_timeout_seconds: float = 30.0

    # Document storage prefix (within the configured S3 bucket).
    document_storage_prefix: str = "documents"

    # External accounting-report provider (ФНС bookkeeping; provider-agnostic)
    accounting_provider_name: str = "parser_api"
    accounting_cache_ttl_days: int = 30
    parser_api_url: str = "https://parser-api.com"
    parser_api_key: str = ""
    parser_api_timeout_ms: int = 15000

    # Magic links — one-shot URLs sent by SMS when a CEO / founder is
    # invited to sign СОПД. The frontend resolves them at `{public_url}/s/{token}`.
    magic_link_ttl_days: int = 14
    magic_link_path_prefix: str = "/s"

    # Catalog parser
    catalog_preview_sample_size: int = 5

    # Object storage (provider-agnostic; currently S3-compatible)
    s3_endpoint: str = "https://storage.yandexcloud.net"
    s3_region: str = "ru-central1"
    s3_bucket: str = "multileasing"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""

    # Kafka / FastStream. `KAFKA_BROKERS` matches Redpanda Console env naming.
    kafka_brokers: str = "localhost:9092"
    kafka_dwh_consumer_group: str = "carcraft-dwh-sync"
    kafka_auth_audit_consumer_group: str = "auth_audit_persister"
    kafka_auth_notifications_consumer_group: str = "auth_notifications"
    kafka_notification_consumer_group: str = "business_notifications_v1"
    notification_email_retry_delays_seconds: list[Annotated[int, Field(gt=0)]] = [60, 300, 900, 3600, 21600]
    notification_email_lease_seconds: int = Field(default=600, ge=120)
    notification_smtp_timeout_seconds: int = Field(default=30, ge=1, le=60)
    notification_business_timezone: str = "Europe/Moscow"
    notification_digest_hour: int = Field(default=9, ge=0, le=23)
    notification_digest_weekday: int = Field(default=0, ge=0, le=6)
    notification_outbox_retention_days: int = Field(default=30, ge=1)
    notification_batch_size: int = Field(default=100, ge=1, le=1000)

    @field_validator("notification_business_timezone")
    @classmethod
    def validate_notification_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("notification_business_timezone must be an IANA timezone") from exc
        return value

    # JWT signing (ES256 + JWKS). See infrastructure/crypto/jwt_keys.py.
    # Decode always requires the `kid` header and rejects HS256 access/refresh
    # tokens.
    jwt_keys_dir: str = ""
    jwt_active_kid: str = ""

    # Mobile ID identity verification. Enabled by default for shared
    # environments; set MOBILE_ID_ENABLED=false only for local smoke tests.
    mobile_id_enabled: bool = True
    mobile_id_provider: Literal["local", "mts", "eqid"] = "mts"
    mobile_id_client_id: str = ""
    mobile_id_base_url: str = "https://idgw.mobileid.mts.ru/oidc"
    mobile_id_audience: str = "https://idgw.mobileid.mts.ru"
    mobile_id_issuer: str = "https://idgw.mobileid.mts.ru"
    mobile_id_scope: str = "openid mc_authn mc_identity_basic"
    mobile_id_request_version: str = "mc_si_r2_v1.0"
    mobile_id_acr_values: str = "2"
    mobile_id_notification_uri: str = "/api/v1/notifications/webhook/mobileid-final"
    mobile_id_sms_otp_notification_uri: str = "/api/v1/notifications/webhook/mobileid"
    mobile_id_jwks_public_url: str = "/.well-known/jwks.json"
    mobile_id_notification_token: str = ""
    mobile_id_sig_kid: str = "sig"
    mobile_id_enc_kid: str = "enc"
    mobile_id_request_timeout_seconds: float = 10.0
    mobile_id_attempt_ttl_seconds: int = 600
    mobile_id_diagnostics_rate_limit_per_window: int = 3
    mobile_id_diagnostics_rate_limit_window_seconds: int = 600
    mobile_id_verbose_logs: bool = True
    eqid_base_url: str = "https://eqid.ru"
    eqid_token: str = ""
    eqid_request_timeout_seconds: float = 10.0

    # Security headers (applied by presentation/middleware/security_headers.py).
    # Set any to empty string to suppress that header.
    security_headers_enabled: bool = True
    security_hsts: str = "max-age=63072000; includeSubDomains; preload"
    security_content_type_options: str = "nosniff"
    security_frame_options: str = "DENY"
    security_referrer_policy: str = "strict-origin-when-cross-origin"
    security_permissions_policy: str = "geolocation=(), microphone=(), camera=(), payment=()"
    security_csp: str = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    # Webhook replay protection — Redis-backed nonce store keyed per
    # transaction_id + signature. Catches retransmission of captured
    # webhooks by an attacker (signature alone doesn't prove freshness).
    webhook_replay_enabled: bool = True
    webhook_replay_window_seconds: int = 24 * 60 * 60  # 24h
    webhook_replay_fail_open: bool = False
    # Reject webhooks whose gateway-supplied timestamp is outside this
    # tolerance. Prevents replay of very old captured webhooks, and
    # makes clock-skew attacks noisy.
    webhook_timestamp_tolerance_seconds: int = 5 * 60

    # --- A3: JWT iss/aud/nbf claims (RFC 7519 standard identifiers) ---
    jwt_issuer: str = "carcraft-fastapi"
    # Audience for the access token — validators compare against this. Can be
    # a comma-separated list to support multi-service fan-out later.
    jwt_audience: str = "carcraft-api"
    # Refuse tokens claiming to be issued more than this many seconds in the
    # future (clock-skew tolerance). Prevents pre-dated forgery.
    jwt_clock_skew_tolerance_seconds: int = 30
    # Back-compat: tokens issued before this change have no `iss`/`aud` and
    # must still verify. Flip to False after all issued tokens have expired
    # (typically: refresh TTL + 1 day).
    jwt_legacy_no_iss_aud_accept: bool = True

    # --- A1: Audit log consumer + retention ---
    audit_retention_days: int = 180  # 152-ФЗ floor: 6 months
    audit_retention_sweep_interval_seconds: int = 3600
    # --- A2: Session metadata ---
    geoip_lookup_enabled: bool = False  # stub; left off until GeoIP source is wired
    trusted_proxy_hops: int = 1          # how many X-Forwarded-For entries we trust

    # --- BE-1: Inactive session timeout ---
    # Max hours a refresh session may sit idle before being rejected.
    # Separate knob per privileged role so admins get a tighter leash.
    max_inactive_session_hours_default: int = 24 * 14   # 14 days for clients
    max_inactive_session_hours_employee: int = 24 * 3   # 3 days for employees

    # --- BE-2: GeoIP ---
    geoip_db_path: str = ""  # MaxMind GeoLite2-Country.mmdb path; empty → Noop

    # --- BE-3: Security notifications ---
    security_notifications_enabled: bool = True
    security_notification_throttle_seconds: int = 3600
    security_new_device_lookback_days: int = 30

    # Logging
    log_level: str = "INFO"
    environment: str = "local"
    service_version: str = "unknown"
    repository_slow_query_ms: float = Field(default=200.0, ge=0)
    tracemalloc_enabled: bool = True

    # --- Calculator fallback rates (used if leasing_rates table is empty) ---
    # Mirror the original Express defaults so calculator output is stable
    # without operator setup. Operators may still override via the DB row.
    calculator_default_key_rate: float = 21.0
    calculator_default_surcharge: float = 4.0
    calculator_default_vat_rate: float = 20.0
    calculator_default_profit_tax_rate: float = 20.0
    calculator_use_default_rates_fallback: bool = True

    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_db: str = "default"

    # Historical analytics calendar and short-lived funnel cache.
    analytics_timezone: str = "Europe/Moscow"
    analytics_funnel_cache_ttl_seconds: int = 60

    kafka_dwh_batch_size: int = 50
    kafka_dwh_batch_flush_seconds: float = 5.0
    metrics_port: int = 8000

    @cached_property
    def clickhouse_dsn(self) -> str:
        return (
            f"clickhouse+http://{self.clickhouse_user}:{self.clickhouse_password}"
            f"@{self.clickhouse_host}:{self.clickhouse_port}/{self.clickhouse_db}"
        )

    @cached_property
    def database_dsn(self) -> str:
        if self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @cached_property
    def cors_allowed_origins(self) -> list[str]:
        origins = [origin.strip() for origin in self.cors_allowed_origins_raw.split(",")]
        filtered = [origin for origin in origins if origin]
        if self.public_url and self.public_url not in filtered:
            filtered.append(self.public_url)
        return filtered


settings = Settings()
