"""Pure business rules for the special-equipment catalog."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from domain.errors import DomainError

MAX_SPECIAL_EQUIPMENT_CATEGORY_DEPTH = 5
MAX_PUBLIC_SPECIAL_EQUIPMENT_ATTRIBUTE_CODE_LENGTH = 100

_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_CODE_CHARACTER = re.compile(r"[^a-z0-9]+")
_PRIVATE_ATTRIBUTE_CODES = frozenset(
    {
        "id",
        "ids",
        "uuid",
        "uuids",
        "vin",
        "vin_number",
        "vehicle_identification_number",
        "vehicleidentificationnumber",
        "storage_key",
        "storage_keys",
        "storagekey",
        "storagekeys",
        "storage_url",
        "storage_uri",
        "storage_path",
        "storage_etag",
        "object_key",
        "object_keys",
        "objectkey",
        "objectkeys",
        "object_storage_key",
        "objectstoragekey",
        "source_object_key",
        "sourceobjectkey",
        "s3",
        "s3_key",
        "s3_keys",
        "s3_object_key",
        "s3_url",
        "s3_uri",
        "s3_bucket",
        "s3key",
        "s3objectkey",
        "s3objectkeys",
        "s3storagekey",
        "s3storagekeys",
        "s3url",
        "s3bucket",
        "internal_id",
        "internal_ids",
        "internal_uuid",
        "internal_identifier",
        "internalidentifier",
        "internalidentifiers",
        "database_id",
        "db_id",
        "record_id",
        "entity_id",
        "multipart_upload_id",
        "upload_id",
        "provider_etag",
        "provider_payload",
        "api_key",
        "access_token",
        "refresh_token",
        "auth_token",
    }
)
_PRIVATE_STORAGE_TOKENS = frozenset(
    {"key", "keys", "url", "uri", "path", "bucket", "etag", "id", "identifier"}
)
_PRIVATE_INTERNAL_IDENTIFIER_TOKENS = frozenset(
    {"id", "ids", "uuid", "uuids", "identifier", "identifiers", "key", "ref", "reference", "code"}
)
_SECRET_TOKENS = frozenset(
    {"secret", "secrets", "password", "credential", "credentials", "token", "tokens"}
)


def public_special_equipment_attribute_code(value: object) -> str | None:
    """Return the original public code or ``None`` for private/unsafe codes.

    This is the shared fail-closed privacy boundary for import validation and
    analytical projection. Canonicalization is used only for classification;
    safe persisted codes keep their original spelling after whitespace trim.
    """
    if not isinstance(value, str):
        return None
    code = value.strip()
    if not 1 <= len(code) <= MAX_PUBLIC_SPECIAL_EQUIPMENT_ATTRIBUTE_CODE_LENGTH:
        return None
    separated = _CAMEL_CASE_BOUNDARY.sub("_", code)
    canonical = _NON_CODE_CHARACTER.sub("_", separated.casefold()).strip("_")
    if not canonical:
        return None
    tokens = frozenset(canonical.split("_"))
    private = any(
        (
            canonical in _PRIVATE_ATTRIBUTE_CODES,
            "vin" in tokens,
            "s3" in tokens,
            "storage" in tokens
            and bool(tokens.intersection(_PRIVATE_STORAGE_TOKENS)),
            "object" in tokens and bool(tokens.intersection({"key", "keys"})),
            "internal" in tokens
            and bool(tokens.intersection(_PRIVATE_INTERNAL_IDENTIFIER_TOKENS)),
            canonical.startswith("private_"),
            canonical.endswith(("_id", "_ids", "_uuid", "_uuids")),
            bool(tokens.intersection(_SECRET_TOKENS)),
            "etag" in tokens,
        )
    )
    return None if private else code


class SpecialEquipmentCategoryTreeError(DomainError):
    """Base error for invalid category-tree mutations."""


class SpecialEquipmentCategoryNotFoundError(SpecialEquipmentCategoryTreeError):
    def __init__(self, category_id: UUID):
        super().__init__(f"Категория спецтехники {category_id} не найдена")
        self.category_id = category_id


class SpecialEquipmentCategoryCycleError(SpecialEquipmentCategoryTreeError):
    def __init__(self) -> None:
        super().__init__("Категория не может быть своим предком")


class SpecialEquipmentCategoryDepthError(SpecialEquipmentCategoryTreeError):
    def __init__(self, depth: int) -> None:
        super().__init__(
            "Глубина дерева категорий спецтехники не может превышать "
            f"{MAX_SPECIAL_EQUIPMENT_CATEGORY_DEPTH} уровней (получено: {depth})"
        )
        self.depth = depth


@dataclass(frozen=True)
class SpecialEquipmentCategoryTreePolicy:
    """Validate one category parent change without performing I/O."""

    max_depth: int = MAX_SPECIAL_EQUIPMENT_CATEGORY_DEPTH

    def ensure_parent_change(
        self,
        *,
        category_id: UUID,
        parent_id: UUID | None,
        parent_by_id: Mapping[UUID, UUID | None],
    ) -> None:
        if category_id not in parent_by_id:
            raise SpecialEquipmentCategoryNotFoundError(category_id)
        if parent_id is None:
            return
        if parent_id not in parent_by_id:
            raise SpecialEquipmentCategoryNotFoundError(parent_id)

        visited = {category_id}
        current_id: UUID | None = parent_id
        depth = 1
        while current_id is not None:
            if current_id in visited:
                raise SpecialEquipmentCategoryCycleError()
            visited.add(current_id)
            depth += 1
            if depth > self.max_depth:
                raise SpecialEquipmentCategoryDepthError(depth)
            current_id = parent_by_id.get(current_id)

        children_by_parent: dict[UUID, list[UUID]] = {}
        for child_id, existing_parent_id in parent_by_id.items():
            if existing_parent_id is not None:
                children_by_parent.setdefault(existing_parent_id, []).append(child_id)
        subtree_height = 1
        stack = [(category_id, 1)]
        subtree_visited: set[UUID] = set()
        while stack:
            node_id, node_height = stack.pop()
            if node_id in subtree_visited:
                raise SpecialEquipmentCategoryCycleError()
            subtree_visited.add(node_id)
            subtree_height = max(subtree_height, node_height)
            stack.extend(
                (child_id, node_height + 1)
                for child_id in children_by_parent.get(node_id, [])
            )
        resulting_depth = depth + subtree_height - 1
        if resulting_depth > self.max_depth:
            raise SpecialEquipmentCategoryDepthError(resulting_depth)
