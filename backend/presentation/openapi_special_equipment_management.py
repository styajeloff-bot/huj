"""OpenAPI post-processing for the corrected catalog-management API."""

from __future__ import annotations

from typing import Any

_MANAGEMENT_PREFIX = "/api/v1/admin/special-equipment/"
_PUBLIC_CATALOG_PATHS = (
    "/api/v1/special-equipment/products",
    "/api/v1/special-equipment/facets",
)
_ERROR_SCHEMA_REF = "#/components/schemas/RegistryErrorResponse"
_WRITE_METHODS = {"post", "put", "patch", "delete"}
_OFFERING_RELATION_SUFFIXES = ("/compatible-attachments", "/components")
_ORDER_PURCHASE_TYPES = (
    "reservation",
    "preorder",
    "full_purchase",
    "leasing",
)
_ORDER_STATUSES = (
    "payment_pending",
    "reserved",
    "preordered",
    "purchased",
    "leasing_pending",
    "leasing_active",
    "cancellation_requested",
    "cancelled",
    "expired",
    "failed",
)


def _header(description: str, *, example: str) -> dict[str, Any]:
    return {
        "description": description,
        "schema": {"type": "string", "example": example},
    }


_ETAG_HEADER = _header(
    "Текущая версия ресурса для последующего If-Match.",
    example='"550e8400-e29b-41d4-a716-446655440000:1"',
)
_LOCATION_HEADER = _header(
    "Канонический путь созданного ресурса.",
    example="/api/v1/admin/special-equipment/categories/"
    "550e8400-e29b-41d4-a716-446655440000",
)
_CONTENT_RANGE_HEADER = _header(
    "Диапазон возвращённых или допустимых байтов.",
    example="bytes 0-1023/4096",
)


def _registry_error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": _ERROR_SCHEMA_REF},
            }
        },
    }


def _set_error_response(
    operation: dict[str, Any], status: str, description: str
) -> None:
    operation.setdefault("responses", {})[status] = _registry_error_response(
        description
    )


def _if_match_parameter(operation: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "header"
            and parameter.get("name", "").casefold() == "if-match"
        ),
        None,
    )


def _query_parameter(
    operation: dict[str, Any], name: str
) -> dict[str, Any] | None:
    return next(
        (
            parameter
            for parameter in operation.get("parameters", [])
            if parameter.get("in") == "query" and parameter.get("name") == name
        ),
        None,
    )


def _document_public_catalog_queries(schema: dict[str, Any]) -> None:
    repeated_descriptions = {
        "mark_id": "Повторяемый UUID марки; значения объединяются через OR.",
        "model_id": (
            "Повторяемый UUID модели выбранной марки; значения объединяются через OR."
        ),
        "modification_id": (
            "Повторяемый UUID модификации выбранной модели; значения объединяются "
            "через OR."
        ),
        "availability": (
            "Повторяемая доступность объявления: available или on_order."
        ),
    }
    for path in _PUBLIC_CATALOG_PATHS:
        operation = schema.get("paths", {}).get(path, {}).get("get")
        if not isinstance(operation, dict):
            continue
        for name, description in repeated_descriptions.items():
            parameter = _query_parameter(operation, name)
            if parameter is None:
                continue
            parameter["description"] = description
            parameter["style"] = "form"
            parameter["explode"] = True
        attribute = _query_parameter(operation, "attribute")
        if attribute is None:
            continue
        attribute["description"] = (
            "Повторяемый фильтр характеристики в формате "
            "`<uuid>:eq:<value>`, `<uuid>:gte:<number>`, "
            "`<uuid>:lte:<number>` или `<uuid>:search:<text>`. "
            "Оператор search выполняет регистронезависимый contains-поиск."
        )
        attribute["style"] = "form"
        attribute["explode"] = True
        attribute["examples"] = {
            "exact": {
                "summary": "Точное значение",
                "value": [
                    "550e8400-e29b-41d4-a716-446655440000:eq:all-wheel"
                ],
            },
            "range": {
                "summary": "Числовой диапазон",
                "value": [
                    "550e8400-e29b-41d4-a716-446655440000:gte:100",
                    "550e8400-e29b-41d4-a716-446655440000:lte:300",
                ],
            },
            "textSearch": {
                "summary": "Поиск по текстовой характеристике",
                "value": [
                    "550e8400-e29b-41d4-a716-446655440000:search:гидравлика"
                ],
            },
        }


def _document_preorder_components(components: dict[str, Any]) -> None:
    order = components.get("SpecialEquipmentOrderOut")
    if not isinstance(order, dict):
        return
    properties = order.get("properties")
    if not isinstance(properties, dict):
        return
    purchase_type = properties.get("purchase_type")
    if isinstance(purchase_type, dict):
        purchase_type["enum"] = list(_ORDER_PURCHASE_TYPES)
    status = properties.get("status")
    if isinstance(status, dict):
        status["enum"] = list(_ORDER_STATUSES)


def _document_created_resource(operation: dict[str, Any]) -> None:
    created = operation.get("responses", {}).get("201")
    if created is None:
        return
    headers = created.setdefault("headers", {})
    headers["ETag"] = _ETAG_HEADER
    headers["Location"] = _LOCATION_HEADER


def _document_conditional_write(operation: dict[str, Any]) -> None:
    parameter = _if_match_parameter(operation)
    if parameter is None:
        return
    parameter["required"] = True
    for status, description in (
        ("404", "Редактируемый ресурс не найден."),
        ("409", "Изменение конфликтует с зависимыми ресурсами."),
        ("412", "If-Match не соответствует текущей версии ресурса."),
        ("428", "Для изменения требуется заголовок If-Match."),
    ):
        _set_error_response(operation, status, description)


def _document_media_response(operation: dict[str, Any]) -> None:
    responses = operation.setdefault("responses", {})
    responses.setdefault("200", {"description": "Полное содержимое изображения."})
    for status in ("200", "206", "304", "416"):
        response = responses.setdefault(status, {"description": "Изображение."})
        response.setdefault("headers", {})["ETag"] = _ETAG_HEADER
    responses["206"]["description"] = "Частичное содержимое изображения."
    responses["206"]["headers"]["Content-Range"] = _CONTENT_RANGE_HEADER
    responses["304"]["description"] = "Содержимое не изменилось."
    responses["416"]["description"] = "Запрошенный byte range недопустим."
    responses["416"]["headers"]["Content-Range"] = _CONTENT_RANGE_HEADER
    _set_error_response(operation, "404", "Изображение не найдено.")


def enrich_special_equipment_management_openapi(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Document the corrected management contract and dependency conflicts."""

    schema.setdefault("info", {})[
        "x-special-equipment-catalog-task"
    ] = "Bitrix 21940 catalog enhancements"
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    _document_public_catalog_queries(schema)
    _document_preorder_components(components)
    components["RegistryErrorResponse"] = {
        "type": "object",
        "required": ["detail"],
        "additionalProperties": False,
        "properties": {
            "detail": {"type": "string"},
            "code": {"type": "string"},
            "entity_type": {"type": "string"},
            "entity_id": {"type": "string", "format": "uuid"},
            "entity_code": {"type": ["string", "null"]},
            "entity_name": {"type": ["string", "null"]},
            "dependencies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["entity", "id", "code", "name", "count"],
                    "additionalProperties": False,
                    "properties": {
                        "entity": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"},
                        "code": {"type": "string"},
                        "name": {"type": "string"},
                        "count": {"type": "integer", "minimum": 1},
                    },
                },
            },
        },
    }
    for path, operations in schema.get("paths", {}).items():
        if not path.startswith(_MANAGEMENT_PREFIX):
            continue
        for method, operation in operations.items():
            if method not in {"get", *_WRITE_METHODS}:
                continue

            _set_error_response(operation, "401", "Требуется авторизация.")
            _set_error_response(operation, "403", "Недостаточно прав.")
            _set_error_response(operation, "422", "Некорректные параметры запроса.")

            if method in _WRITE_METHODS:
                _set_error_response(
                    operation,
                    "409",
                    "Изменение конфликтует с зависимыми ресурсами.",
                )
                _document_conditional_write(operation)
            if method == "post":
                _document_created_resource(operation)
            if any(suffix in path for suffix in _OFFERING_RELATION_SUFFIXES):
                status = (
                    "201"
                    if method == "post"
                    else "204"
                    if method == "delete"
                    else "200"
                )
                operation.setdefault("responses", {}).setdefault(
                    status, {"description": "Упорядоченные товарные связи."}
                ).setdefault("headers", {})["ETag"] = _ETAG_HEADER
            if method == "get" and path.endswith(
                ("/image/content", "/images/{image_id}/content")
            ):
                _document_media_response(operation)

    return schema
