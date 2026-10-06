"""Unified error response formatting and global exception handlers.

Client-facing errors use this base shape by default::

    {"detail": "<human-readable Russian text>", "code": "<PROGRAMMATIC_CODE>"}

* Base-format ``detail`` is a plain Russian string — never a dict or list.
* ``code`` is optional; omitted only for truly generic 5xx fallback.
* selected conflict responses may preserve documented structured extension
  fields from ``HTTPException.detail``.
* The documented special-equipment color contract is a scoped exception and
  uses ``{"error": {"code", "message", "detail", "field_errors"}}``.

This module is the **single source of truth** for how errors leave the API.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from application.errors import DomainError, ServiceError, domain_to_http

# ---------------------------------------------------------------------------
# Russian translations for standard Starlette / HTTP phrases
# ---------------------------------------------------------------------------

_HTTP_TRANSLATIONS: dict[int, str] = {
    400: "Некорректный запрос",
    401: "Требуется авторизация",
    403: "Доступ запрещён",
    404: "Ресурс не найден",
    405: "Метод не поддерживается",
    409: "Конфликт данных",
    413: "Размер запроса превышает допустимый лимит",
    415: "Неподдерживаемый тип файла",
    422: "Некорректные данные запроса",
    429: "Слишком много запросов",
    500: "Произошла внутренняя ошибка. Попробуйте позже.",
    502: "Внешний сервис недоступен",
    503: "Сервис временно недоступен",
}

# Starlette ships English phrases for 404/405 even when the status code is
# already known. We normalise them here.
_STARLETTE_PHRASES: dict[str, str] = {
    "not found": "Ресурс не найден",
    "method not allowed": "Метод не поддерживается",
    "bad request": "Некорректный запрос",
}

_VALIDATION_FIELD_LABELS: dict[str, str] = {
    "application_query": "Поиск по заявке",
    "application_id": "ID заявки",
    "support_query": "Поиск по поддержке",
    "applied_support_id": "ID применённой поддержки",
    "compensation_id": "ID компенсации",
    "due_date_from": "Срок с",
    "due_date_to": "Срок по",
    "page": "Страница",
    "limit": "Лимит",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_text_and_code(
    raw: str | dict[str, Any] | list[Any] | None,
) -> tuple[str, str | None]:
    """Pull a Russian string + optional code out of anything a handler may
    have stuffed into *detail*.

    Supported legacy shapes inside routers:
    * ``str`` — returned as-is.
    * ``{"error": "...", "code": "..."}`` — used by auth/users.
    * ``{"detail": "...", "code": "..."}`` — alternate legacy shape.
    * ``list`` (Pydantic validation dump) — collapsed to generic text.
    * ``None`` — generic fallback.
    """
    if raw is None:
        return "Произошла ошибка", None

    if isinstance(raw, dict):
        text = raw.get("error") or raw.get("detail")
        code = raw.get("code")
        if text is None:
            # Fallback for malformed dicts — should never happen after cleanup.
            text = str(raw)
        return text if isinstance(text, str) else str(text), code

    if isinstance(raw, list):
        # Pydantic ValidationError detail dumps or other lists.
        return "Некорректные данные запроса", "VALIDATION_ERROR"

    if isinstance(raw, str):
        return raw, None

    return str(raw), None


def _maybe_translate(text: str, status_code: int) -> str:
    """If *text* is still an English stock phrase, replace it."""
    lower = text.strip().lower()
    if lower in _STARLETTE_PHRASES:
        return _STARLETTE_PHRASES[lower]
    # Also guard against numeric-only or empty strings.
    if not text.strip():
        return _HTTP_TRANSLATIONS.get(status_code, "Произошла ошибка")
    return text


def _domain_error_code(exc: DomainError) -> str:
    """``VehicleNotFoundError`` → ``VEHICLE_NOT_FOUND_ERROR``."""
    return _snake_upper(type(exc).__name__)


def _snake_upper(name: str) -> str:
    """CamelCase → SCREAMING_SNAKE_CASE."""
    result: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.upper())
    return "".join(result)


def _validation_detail(exc: RequestValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Некорректные данные запроса"

    messages: list[str] = []
    for error in errors[:4]:
        loc = error.get("loc") or ()
        field = _validation_field_label(loc)
        reason = _validation_reason(error)
        messages.append(f"{field}: {reason}" if field else reason)

    if len(errors) > 4:
        messages.append(f"ещё ошибок: {len(errors) - 4}")

    return "Проверьте данные запроса: " + "; ".join(messages)


def _is_product_management_request(request: Request | None) -> bool:
    """Whether the request uses the warehouse-aware product API contract."""
    if request is None:
        return False
    prefix = "/api/v1/admin/special-equipment/products"
    path = request.url.path.rstrip("/")
    if path != prefix and not path.startswith(f"{prefix}/"):
        return False
    suffix = path[len(prefix) :].strip("/")
    parts = suffix.split("/") if suffix else []
    return (
        (request.method == "POST" and not parts)
        or (request.method in {"GET", "PATCH"} and len(parts) == 1)
        or (
            request.method == "PUT"
            and len(parts) == 2
            and parts[1] == "warehouse"
        )
    )


def _is_warehouse_admin_request(request: Request | None) -> bool:
    if request is None:
        return False
    prefix = "/api/v1/admin/warehouses"
    path = request.url.path.rstrip("/")
    return path == prefix or path.startswith(f"{prefix}/")


def _is_admin_company_update_request(request: Request | None) -> bool:
    if request is None or request.method != "PATCH":
        return False
    prefix = "/api/v1/admin/companies/"
    suffix = request.url.path.rstrip("/").removeprefix(prefix)
    return request.url.path.startswith(prefix) and "/" not in suffix


def _admin_company_update_error_response(
    *,
    status_code: int,
    detail: str | dict[str, Any] | list[Any] | None,
    code: str,
    field_errors: list[dict[str, Any]] | None = None,
    blockers: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    text, _ = _extract_text_and_code(detail)
    content: dict[str, Any] = {
        "detail": _maybe_translate(text, status_code),
        "code": code,
        "field_errors": field_errors or [],
    }
    if blockers is not None:
        content["blockers"] = blockers
    return JSONResponse(status_code=status_code, content=content)


def _validation_field_label(loc: object) -> str:
    if not isinstance(loc, (list, tuple)):
        return ""
    parts = [str(part) for part in loc if part not in {"body", "query", "path"}]
    if not parts:
        return ""
    label = _VALIDATION_FIELD_LABELS.get(parts[-1])
    return label or ".".join(parts)


def _validation_reason(error: dict[str, Any]) -> str:
    error_type = str(error.get("type") or "")
    ctx = error.get("ctx") if isinstance(error.get("ctx"), dict) else {}

    simple_reasons = {
        "uuid_parsing": "ожидается UUID в формате xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "uuid_type": "ожидается UUID в формате xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        "date_from_datetime_parsing": "ожидается дата в формате ГГГГ-ММ-ДД",
        "date_parsing": "ожидается дата в формате ГГГГ-ММ-ДД",
        "date_type": "ожидается дата в формате ГГГГ-ММ-ДД",
        "int_parsing": "ожидается целое число",
        "int_type": "ожидается целое число",
        "float_parsing": "ожидается число",
        "float_type": "ожидается число",
        "decimal_parsing": "ожидается число",
        "missing": "обязательное поле",
        "extra_forbidden": "лишнее поле",
    }

    reason = simple_reasons.get(error_type)
    if reason is None and error_type == "literal_error":
        expected = ctx.get("expected") if ctx else None
        reason = (
            f"допустимые значения: {expected}"
            if expected
            else "недопустимое значение"
        )
    if reason is None and error_type in {"greater_than_equal", "less_than_equal"}:
        bound_key = "ge" if error_type == "greater_than_equal" else "le"
        bound = ctx.get(bound_key) if ctx else None
        comparator = "не меньше" if bound_key == "ge" else "не больше"
        reason = f"значение должно быть {comparator} {bound}"

    message = str(error.get("msg") or "").strip()
    return reason or message or "некорректное значение"


# ---------------------------------------------------------------------------
# Public: response builder
# ---------------------------------------------------------------------------

def error_response(
    status_code: int,
    detail: str | dict[str, Any] | list[Any] | None = None,
    *,
    code: str | None = None,
) -> JSONResponse:
    """Build the canonical error JSONResponse.

    Parameters
    ----------
    status_code:
        HTTP status to return.
    detail:
        Anything the caller originally placed in *HTTPException.detail*.
    code:
        Explicit programmatic code. If omitted we try to extract it from
        *detail* (legacy dicts) or fall back to None.
    """
    text, extracted_code = _extract_text_and_code(detail)
    text = _maybe_translate(text, status_code)

    # If no explicit code was passed and we extracted one from a legacy dict,
    # use it. Otherwise leave it out for generic errors.
    final_code = code if code is not None else extracted_code

    # Hard safety net: ensure we never return a 5xx with an empty detail.
    if status_code >= 500 and not text.strip():
        text = _HTTP_TRANSLATIONS.get(status_code, "Произошла внутренняя ошибка")

    payload: dict[str, Any] = {"detail": text}
    if final_code:
        payload["code"] = final_code
    if isinstance(detail, dict):
        for key in (
            "blockers",
            "entity_type",
            "entity_id",
            "entity_code",
            "entity_name",
            "dependencies",
            "field",
            "vin",
            "source_number",
        ):
            if key in detail:
                payload[key] = detail[key]

    return JSONResponse(status_code=status_code, content=payload)


def _is_special_equipment_v516_problem_request(request: Request | None) -> bool:
    """Return whether the route belongs to the scoped v5.16 RFC 9457 contract."""

    if request is None:
        return False
    path = request.url.path
    return path.startswith(
        (
            "/api/v1/special-equipment/products",
            "/api/v1/admin/special-equipment/products",
            "/api/v1/admin/special-equipment/modifications",
            "/api/v1/admin/special-equipment/trims",
        )
    ) or path == "/api/v1/special-equipment/facets"


def special_equipment_problem_response(
    status_code: int,
    detail: str | dict[str, Any] | list[Any] | None = None,
    *,
    code: str | None = None,
    type_uri: str = "about:blank",
    title: str | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build the scoped RFC 9457 response used by special-equipment v5.16."""

    text, extracted_code = _extract_text_and_code(detail)
    text = _maybe_translate(text, status_code)
    final_code = code or extracted_code or {
        400: "REQUEST_ERROR",
        401: "AUTHENTICATION_REQUIRED",
        403: "ACCESS_DENIED",
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "STATE_CONFLICT",
        412: "PRECONDITION_FAILED",
        422: "VALIDATION_ERROR",
        428: "PRECONDITION_REQUIRED",
        429: "RATE_LIMIT_EXCEEDED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "REQUEST_ERROR")
    payload: dict[str, Any] = {
        "type": type_uri,
        "title": title or _HTTP_TRANSLATIONS.get(status_code, "Ошибка запроса"),
        "status": status_code,
        "detail": text,
        "code": final_code,
    }
    if isinstance(detail, dict) and isinstance(detail.get("errors"), list):
        payload["errors"] = detail["errors"]
    if extensions:
        payload.update(extensions)
    return JSONResponse(
        status_code=status_code,
        content=payload,
        media_type="application/problem+json",
    )


def _is_color_request(request: Request | None) -> bool:
    return request is not None and request.url.path.startswith(
        "/api/v1/admin/special-equipment/colors"
    )


def _is_color_product_request(request: Request | None) -> bool:
    return request is not None and request.url.path.startswith(
        "/api/v1/admin/special-equipment/products"
    )


class ColorErrorDetail(dict[str, Any]):
    """Typed marker for the explicitly scoped color error contract."""


def color_error_detail(
    *,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    field_errors: list[dict[str, Any]] | None = None,
) -> ColorErrorDetail:
    return ColorErrorDetail(
        {
            "error": {
                "code": code,
                "message": message,
                "detail": detail,
                "field_errors": field_errors or [],
            }
        }
    )


def _color_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    field_errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=color_error_detail(
            code=code,
            message=message,
            detail=detail,
            field_errors=field_errors,
        ),
    )


# ---------------------------------------------------------------------------
# Passport snapshot API errors
# ---------------------------------------------------------------------------

def _is_passport_snapshot_request(request: Request) -> bool:
    path = request.url.path
    return (
        "/sopd-signers/" in path and "/passport" in path
    ) or (path.startswith("/api/v1/signatures/") and "/passport" in path)


def _passport_error_code(status_code: int, raw: Any) -> str:
    if isinstance(raw, dict):
        code = raw.get("code")
        if isinstance(code, str):
            return code
    text = str(raw)
    rules = (
        (("несохранённые изменения",), "PASSPORT_ACTIONS_BLOCKED_UNSAVED_CHANGES"),
        (("Подтверждённый снимок", "Сначала распознайте"), "PASSPORT_SNAPSHOT_NOT_CONFIRMED"),
        (("недоступно для изменения",), "PASSPORT_REQUEST_NOT_EDITABLE"),
        (("распознать",), "PASSPORT_RECOGNITION_FAILED"),
    )
    for fragments, code in rules:
        if any(fragment in text for fragment in fragments):
            return code
    if status_code in (403, 404):
        return "PASSPORT_ACCESS_DENIED"
    return "PASSPORT_FIELDS_REQUIRED" if status_code == 422 else "PASSPORT_REQUEST_NOT_EDITABLE"



def _passport_error_response(request: Request, *, status_code: int, raw: Any) -> JSONResponse:
    code = _passport_error_code(status_code, raw)
    detail: dict[str, Any] = {
        "code": code,
        "message": (
            raw.get("message") if isinstance(raw, dict) and isinstance(raw.get("message"), str)
            else {
                "PASSPORT_ACCESS_DENIED": "Нет доступа к паспортным данным.",
                "PASSPORT_REQUEST_NOT_EDITABLE": "СОПД недоступно для изменения.",
                "PASSPORT_SNAPSHOT_NOT_CONFIRMED": "Подтвердите паспортные данные перед продолжением.",
                "PASSPORT_ACTIONS_BLOCKED_UNSAVED_CHANGES": "Сначала сохраните изменения паспортных данных.",
                "PASSPORT_RECOGNITION_FAILED": "Не удалось распознать паспортные данные.",
                "PASSPORT_FIELDS_REQUIRED": "Заполните обязательные поля паспорта.",
                "PASSPORT_NATIONALITY_REQUIRED": "Необходимо указать гражданство.",
                "PASSPORT_RU_FORMAT_INVALID": "Неверный формат паспортных данных.",
                "PASSPORT_NAME_MISMATCH": "ФИО в распознанном паспорте не совпадает с ФИО кандидата на момент загрузки.",
                "PASSPORT_SURNAME_REUPLOAD_REQUIRED": "Фамилия существенно отличается от результата распознавания. Загрузите более качественное фото паспорта.",
            }[code]
        ),
    }
    if isinstance(raw, dict) and isinstance(raw.get("fields"), dict):
        detail["fields"] = raw["fields"]
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


# ---------------------------------------------------------------------------
# Global exception handlers (wired in main.py)
# ---------------------------------------------------------------------------

async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
    """Catch unhandled DomainError anywhere in the router tree."""
    service_error = domain_to_http(exc)
    if _is_special_equipment_v516_problem_request(request):
        return special_equipment_problem_response(
            status_code=service_error.status_code,
            detail=str(service_error),
            code=_domain_error_code(exc),
        )
    # Fast deal errors point at the offending input (field) or unit (VIN).
    extension = {
        key: value
        for key in ("field", "vin", "source_number")
        if (value := getattr(exc, key, None)) is not None
    }
    return error_response(
        status_code=service_error.status_code,
        detail={"error": str(service_error), **extension} if extension else str(service_error),
        code=_domain_error_code(exc),
    )


async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
    """Catch unhandled ServiceError anywhere in the router tree."""
    if _is_special_equipment_v516_problem_request(request):
        return special_equipment_problem_response(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code or "SERVICE_ERROR",
        )
    return error_response(
        status_code=exc.status_code,
        detail=str(exc),
        code="SERVICE_ERROR",
    )


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Normalise FastAPI / Starlette HTTPException into the canonical shape.

    This covers:
    * direct ``raise HTTPException(...)`` inside routers;
    * the ``_http()`` wrappers that routers currently use;
    * built-in Starlette 404 / 405 responses.
    """
    if _is_admin_company_update_request(request):
        text, incoming_code = _extract_text_and_code(exc.detail)
        admin_code = incoming_code or {
            403: "INSUFFICIENT_PERMISSIONS",
            404: "COMPANY_NOT_FOUND",
            409: "INN_ALREADY_EXISTS",
            422: "VALIDATION_ERROR",
        }.get(exc.status_code, "REQUEST_ERROR")
        field_errors = (
            exc.detail.get("field_errors", [])
            if isinstance(exc.detail, dict)
            and isinstance(exc.detail.get("field_errors"), list)
            else [
                {
                    "field": "inn",
                    "code": "already_exists",
                    "message": text,
                }
            ]
            if exc.status_code == 409
            else []
        )
        return _admin_company_update_error_response(
            status_code=exc.status_code,
            detail=exc.detail,
            code=admin_code,
            field_errors=field_errors,
            blockers=(
                exc.detail.get("blockers")
                if isinstance(exc.detail, dict)
                and isinstance(exc.detail.get("blockers"), list)
                else None
            ),
        )
    if _is_passport_snapshot_request(request):
        return _passport_error_response(
            request, status_code=exc.status_code, raw=exc.detail
        )
    if isinstance(exc.detail, ColorErrorDetail):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    problem_header = any(
        key.lower() == "content-type" and value == "application/problem+json"
        for key, value in (exc.headers or {}).items()
    )
    product_request = _is_product_management_request(request)
    warehouse_request = _is_warehouse_admin_request(request)
    if problem_header or product_request or warehouse_request:
        text, code = _extract_text_and_code(exc.detail)
        resource = "Warehouse" if warehouse_request else "Product"
        content: dict[str, Any] = {
            "type": "about:blank",
            "title": {
                400: f"Invalid {resource.lower()} request",
                401: "Authentication required",
                403: "Access denied",
                404: f"{resource} or dependency not found",
                409: f"{resource} conflict",
                412: f"{resource} precondition failed",
                422: f"{resource} validation error",
                428: f"{resource} precondition required",
            }.get(exc.status_code, f"{resource} request error"),
            "status": exc.status_code,
            "detail": _maybe_translate(text, exc.status_code),
        }
        if code is not None:
            content["code"] = code
        if isinstance(exc.detail, dict):
            content.update(
                {
                    k: v
                    for k, v in exc.detail.items()
                    if k not in ("status", "detail", "code")
                }
            )
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            media_type="application/problem+json",
        )
    if _is_color_request(request):
        text, _code = _extract_text_and_code(exc.detail)
        message = _maybe_translate(text, exc.status_code)
        code = {
            401: "authentication_required",
            403: "access_denied",
            404: "color_not_found",
            422: "validation_error",
        }.get(exc.status_code, "color_error")
        return _color_error_response(
            status_code=exc.status_code,
            code=code,
            message=message,
        )
    if _is_special_equipment_v516_problem_request(request):
        response = special_equipment_problem_response(
            status_code=exc.status_code, detail=exc.detail
        )
    else:
        response = error_response(status_code=exc.status_code, detail=exc.detail)
    return response


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic / FastAPI request-validation (422)."""
    if _is_admin_company_update_request(request):
        field_errors = [
            {
                "field": _validation_field_label(error.get("loc") or ()) or "request",
                "code": str(error.get("type") or "invalid"),
                "message": _validation_reason(error),
            }
            for error in exc.errors()
        ]
        return _admin_company_update_error_response(
            status_code=422,
            detail=_validation_detail(exc),
            code="VALIDATION_ERROR",
            field_errors=field_errors,
        )
    if _is_passport_snapshot_request(request):
        return _passport_error_response(
            request, status_code=422, raw={"code": "PASSPORT_FIELDS_REQUIRED"}
        )
    product_request = _is_product_management_request(request)
    warehouse_request = _is_warehouse_admin_request(request)
    if product_request or warehouse_request:
        resource = "Warehouse" if warehouse_request else "Product"
        return JSONResponse(
            status_code=422,
            content={
                "type": "about:blank",
                "title": f"{resource} validation error",
                "status": 422,
                "detail": _validation_detail(exc),
                "code": "VALIDATION_ERROR",
            },
            media_type="application/problem+json",
        )
    color_fields = {"body_color_id", "interior_color_id"}
    has_color_field = any(
        any(str(part) in color_fields for part in (error.get("loc") or ()))
        for error in exc.errors()
    )
    if _is_color_request(request) or (
        _is_color_product_request(request) and has_color_field
    ):
        field_errors = [
            {
                "field": _validation_field_label(error.get("loc") or ()) or "request",
                "code": str(error.get("type") or "invalid"),
                "message": _validation_reason(error),
            }
            for error in exc.errors()
        ]
        return _color_error_response(
            status_code=422,
            code="validation_error",
            message=_validation_detail(exc),
            field_errors=field_errors,
        )
    if _is_special_equipment_v516_problem_request(request):
        return special_equipment_problem_response(
            status_code=422,
            detail=_validation_detail(exc),
            code="VALIDATION_ERROR",
        )
    return error_response(
        status_code=422,
        detail=_validation_detail(exc),
        code="VALIDATION_ERROR",
    )


async def handle_unhandled_exception(
    request: Request, _exc: Exception
) -> JSONResponse:
    """Last-resort catch-all (500).  Must never leak traceback to client."""
    if _is_special_equipment_v516_problem_request(request):
        response = special_equipment_problem_response(
            status_code=500,
            detail="Произошла внутренняя ошибка. Попробуйте позже.",
            code="INTERNAL_ERROR",
        )
    else:
        response = error_response(
            status_code=500,
            detail="Произошла внутренняя ошибка. Попробуйте позже.",
            code="INTERNAL_ERROR",
        )
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        response.headers["X-Request-ID"] = request_id
    return response
