"""Normalization and validation for the Russian special-equipment import v2."""

# ruff: noqa: PLR0912, PLR0915, TRY301

from __future__ import annotations

import hashlib
import json
import tempfile
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment import public_special_equipment_attribute_code
from domain.special_equipment_attachments import (
    attachment_branch_ids,
    rule_inheritance_graph,
)
from domain.special_equipment_catalog import (
    CategoryAttributeRule,
    CategoryGraph,
    EquipmentCondition,
    SpecialEquipmentCatalogError,
    UsageMetric,
    effective_attribute_rules,
    ensure_card_attribute_limit,
    ensure_condition_owners,
    ensure_condition_usage,
    ensure_single_usage_metric,
    ensure_vin_choice,
    generate_catalog_slug,
    resolve_trim_attribute_contract,
)
from domain.special_equipment_import import (
    DATA_SHEET_HEADERS,
    DATA_SHEET_NAMES,
    KIT_SUPERSTRUCTURE_MODEL_REQUIRED,
    KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH,
    KIT_SUPERSTRUCTURE_SOURCE_CONFLICT,
    KIT_SUPERSTRUCTURE_SOURCE_INVALID,
    MAX_UI_ISSUES,
    REFERENCE_NOT_IN_SNAPSHOT,
    REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
    SUPERSTRUCTURE_NAME_CONFLICT,
    ImportContractError,
    ImportIssue,
    ImportMode,
    IssueSeverity,
    ReferenceNotInSnapshotError,
    deterministic_entity_id,
    error_policy_for_mode,
    normalize_usage_metric,
    parse_bool,
    parse_image_source_urls,
    special_equipment_column_title,
    validate_entity_code,
)
from domain.special_equipment_management import (
    ProductPriceOnRequestModeLockedError,
    SpecialEquipmentColorConflictError,
    SpecialEquipmentColorValidationError,
    SpecialEquipmentManagementValidationError,
    ensure_color_applicability_change_allowed,
    ensure_price_on_request_mode_change,
    ensure_product_color_assignment_allowed,
    ensure_product_commercial_terms,
    ensure_warehouse_owner_matches_seller,
    normalize_color_applicability,
    normalize_color_code,
    normalize_color_name,
)
from infrastructure.repositories import special_equipment_import_repository as repo
from infrastructure.services.special_equipment_xlsx import (
    JsonlRows,
    ParsedWorkbook,
    create_row_stores,
)
from infrastructure.settings import settings

_ENTITY_FAMILIES = (
    "units",
    "marks",
    "models",
    "modifications",
    "trims",
    "categories",
    "attribute_groups",
    "attributes",
    "attribute_options",
    "superstructures",
    "colors",
    "products",
)
_LINK_FAMILIES = (
    "category_relations",
    "category_attributes",
    "superstructure_categories",
    "superstructure_attributes",
    "modification_categories",
    "modification_attribute_values",
    "trim_attributes",
    "trim_attribute_values",
    "product_categories",
    "product_chassis_values",
    "product_superstructure_values",
    "product_attachments",
)
_DIRECTORY_FAMILIES = (
    "units",
    "marks",
    "categories",
    "attribute_groups",
    "attributes",
)

_DIRECTORY_FIELD_DEFAULTS: dict[str, dict[str, Any]] = {
    "units": {"is_active": True},
    "categories": {
        "is_attachment_category": False,
        "is_visible_in_catalog": True,
        "sort_order": 0,
        "is_active": True,
    },
    "attribute_groups": {"sort_order": 0, "is_active": True},
    "marks": {"is_active": True},
    "attributes": {"is_active": True},
}


class _ProductFieldImportContractError(ImportContractError):
    """Product validation error tied to a concrete workbook column."""

    def __init__(
        self,
        column_name: str,
        message: str,
        code: str = "PRODUCT_INVALID",
    ) -> None:
        super().__init__(message)
        self.column_name = column_name
        self.code = code


class V2IssueCollector(list[ImportIssue]):
    """Bound issue samples while retaining exact error/warning totals."""

    def __init__(self, *, sample_limit: int = MAX_UI_ISSUES) -> None:
        super().__init__()
        self.sample_limit = sample_limit
        self.total_count = 0
        self.error_count = 0
        self.warning_count = 0

    @property
    def is_truncated(self) -> bool:
        return self.total_count > len(self)

    def append(self, issue: ImportIssue) -> None:
        self.total_count += 1
        if issue.severity is IssueSeverity.ERROR:
            self.error_count += 1
        else:
            self.warning_count += 1
        if len(self) < self.sample_limit:
            super().append(issue)

    def extend(self, issues: Iterable[ImportIssue]) -> None:
        for issue in issues:
            self.append(issue)


async def build_normalized_plan_v2(
    session: AsyncSession,
    *,
    job: dict[str, Any],
    workbook: ParsedWorkbook,
    plan_spool_dir: Path | None = None,
) -> tuple[
    dict[str, JsonlRows],
    V2IssueCollector,
    dict[str, Any],
    dict[uuid.UUID, int],
    set[uuid.UUID],
]:
    """Build a replayable v4 plan grouped into independently applicable roots."""

    mode = ImportMode(str(job["mode"]))
    policy = error_policy_for_mode(mode)
    issues = V2IssueCollector()
    issues.extend(workbook.adapter_issues)
    if workbook.manifest.get("error_policy") != policy.value:
        issues.append(_manifest_issue("PARAMETERS_POLICY_MISMATCH"))

    raw_rows = {
        family: [dict(row) for row in workbook.rows.get(family, ())]
        for family in DATA_SHEET_HEADERS
    }
    requested_codes, seller_inns = _requested_codes(raw_rows, issues)
    context = await repo.get_v2_import_context(
        session,
        requested_codes=requested_codes,
        seller_inns=seller_inns,
        target_warehouse_id=job.get("target_warehouse_id"),
        mode=mode,
    )
    work_dir = plan_spool_dir or Path(tempfile.mkdtemp(prefix="se-import-v2-"))
    plan = create_row_stores(work_dir / "normalized", DATA_SHEET_HEADERS)
    identity, accepted_entity_rows = _prepare_entity_identity(
        raw_rows=raw_rows,
        context=context,
        mode=mode,
        issues=issues,
    )

    valid_codes: dict[str, set[str]] = defaultdict(set)
    for family in _DIRECTORY_FAMILIES:
        for row in accepted_entity_rows[family]:
            normalized = _normalize_directory_entity(
                family=family,
                row=row,
                mode=mode,
                context=context,
                identity=identity,
                valid_codes=valid_codes,
                issues=issues,
            )
            if normalized is not None:
                plan[family].append(normalized)
                valid_codes[family].add(str(row["_code"]))

    for row in accepted_entity_rows["models"]:
        normalized = _normalize_model(
            row=row,
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
        )
        if normalized is not None:
            plan["models"].append(normalized)
            valid_codes["models"].add(str(row["_code"]))

    for row in accepted_entity_rows["modifications"]:
        normalized = _normalize_modification(
            row=row,
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
        )
        if normalized is not None:
            plan["modifications"].append(normalized)
            valid_codes["modifications"].add(str(row["_code"]))

    for row in accepted_entity_rows["trims"]:
        normalized = _normalize_trim(
            row=row,
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
        )
        if normalized is not None:
            plan["trims"].append(normalized)
            valid_codes["trims"].add(str(row["_identity_key"]))

    for row in accepted_entity_rows["colors"]:
        normalized = _normalize_color(
            row=row,
            mode=mode,
            context=context,
            issues=issues,
        )
        if normalized is not None:
            plan["colors"].append(normalized)
            valid_codes["colors"].add(str(row["_code"]))

    for row in accepted_entity_rows["attribute_options"]:
        normalized = _normalize_attribute_option(
            plan=plan,
            row=row,
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
        )
        if normalized is not None:
            plan["attribute_options"].append(normalized)
            valid_codes["attribute_options"].add(str(row["_identity_key"]))

    seen_superstructure_names: dict[str, str] = {}
    for row in accepted_entity_rows["superstructures"]:
        normalized = _normalize_superstructure(
            row=row,
            mode=mode,
            context=context,
            issues=issues,
            seen_names=seen_superstructure_names,
        )
        if normalized is not None:
            plan["superstructures"].append(normalized)
            valid_codes["superstructures"].add(str(row["_code"]))

    _normalize_superstructure_attributes(
        plan=plan,
        rows=raw_rows["superstructure_attributes"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_superstructure_categories(
        plan=plan,
        rows=raw_rows["superstructure_categories"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )

    _normalize_category_relations(
        plan=plan,
        rows=raw_rows["category_relations"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_modification_categories(
        plan=plan,
        rows=raw_rows["modification_categories"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _validate_modification_category_presence(
        plan=plan,
        context=context,
        mode=mode,
        valid_codes=valid_codes,
        issues=issues,
    )
    _normalize_category_attributes(
        plan=plan,
        rows=raw_rows["category_attributes"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_modification_values(
        plan=plan,
        rows=raw_rows["modification_attribute_values"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _validate_modification_attribute_scope_plan(
        plan=plan,
        context=context,
        mode=mode,
        issues=issues,
    )
    _normalize_trim_attributes(
        plan=plan,
        rows=raw_rows["trim_attributes"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_trim_values(
        plan=plan,
        rows=raw_rows["trim_attribute_values"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _validate_attribute_graph_mutation_plan(
        plan=plan,
        context=context,
        mode=mode,
        valid_codes=valid_codes,
        issues=issues,
    )

    context["_planned_category_metrics"] = {
        uuid.UUID(str(row["id"])): str(row["values"]["usage_metric"])
        for row in plan["categories"]
        if row["operation"] != "DELETE"
    }
    context["_planned_modification_categories"] = {
        (
            uuid.UUID(str(row["values"]["modification_id"])),
            uuid.UUID(str(row["values"]["category_id"])),
        )
        for row in plan["modification_categories"]
        if row["operation"] != "DELETE"
    }
    context["_import_mode"] = mode.value
    context["_planned_category_relations"] = list(plan["category_relations"])
    context["_planned_category_attributes"] = list(plan["category_attributes"])
    context["_planned_modification_attribute_values"] = list(
        plan["modification_attribute_values"]
    )
    _validate_card_attribute_limit_plan(
        plan=plan,
        context=context,
        mode=mode,
        issues=issues,
    )
    context["_planned_category_relations"] = list(plan["category_relations"])
    context["_planned_category_attributes"] = list(plan["category_attributes"])
    context["_effective_catalog_entities"] = _effective_catalog_entities(
        context=context,
        plan=plan,
        mode=mode,
    )
    product_link_codes: dict[str, set[str]] = defaultdict(set)
    product_link_codes.update(valid_codes)
    product_link_codes["products"].update(
        str(row["_code"]) for row in accepted_entity_rows["products"]
    )
    product_categories = _normalize_product_categories(
        plan=plan,
        rows=raw_rows["product_categories"],
        identity=identity,
        valid_codes=product_link_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    category_graph, _, _ = _effective_category_contract(
        plan=plan, context=context, mode=mode
    )
    attachment_ids = _planned_attachment_ids(
        context=context,
        plan=plan,
        mode=mode,
        graph=category_graph,
    )
    active_seller_ids: set[uuid.UUID] = set()
    planned_superstructure_categories = {
        (
            uuid.UUID(str(r["values"]["superstructure_id"])),
            uuid.UUID(str(r["values"]["category_id"])),
        )
        for r in plan.get("superstructure_categories", ())
        if r.get("operation") != "DELETE"
    }

    ordinary_rows: list[dict[str, Any]] = []
    kit_rows: list[dict[str, Any]] = []
    workbook_kit_codes: set[str] = set()
    for row in accepted_entity_rows["products"]:
        s_code = str(row.get("superstructure_code") or "").strip()
        code_str = str(row["_code"])
        current_product = context.get("products", {}).get(code_str, {})
        has_model = bool(str(row.get("model_code") or "").strip()) or bool(
            current_product.get("model_id")
        )
        has_kit_fields = any(
            bool(str(row.get(f) or "").strip())
            for f in (
                "superstructure_model_code",
                "superstructure_modification_code",
                "superstructure_source_code",
                "superstructure_name",
                "superstructure_manufacturer",
            )
        )
        is_kit = bool(s_code) and (has_model or has_kit_fields)
        if is_kit:
            kit_rows.append(row)
            workbook_kit_codes.add(code_str)
        else:
            ordinary_rows.append(row)

    workbook_ordinary_products: dict[str, dict[str, Any]] = {}
    for row in ordinary_rows:
        normalized = _normalize_product(
            row=row,
            categories=product_categories.get(str(row["_code"]), []),
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
            attachment_category_ids=attachment_ids,
            workbook_ordinary_products=workbook_ordinary_products,
            workbook_kit_codes=workbook_kit_codes,
            product_categories=product_categories,
            planned_superstructure_categories=planned_superstructure_categories,
        )
        if normalized is not None:
            plan["products"].append(normalized)
            valid_codes["products"].add(str(row["_code"]))
            workbook_ordinary_products[str(row["_code"])] = normalized
            seller_id = normalized["values"].get("seller_company_id")
            if seller_id is not None:
                active_seller_ids.add(uuid.UUID(str(seller_id)))

    for row in kit_rows:
        normalized = _normalize_product(
            row=row,
            categories=product_categories.get(str(row["_code"]), []),
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
            issues=issues,
            attachment_category_ids=attachment_ids,
            workbook_ordinary_products=workbook_ordinary_products,
            workbook_kit_codes=workbook_kit_codes,
            product_categories=product_categories,
            planned_superstructure_categories=planned_superstructure_categories,
        )
        if normalized is not None:
            plan["products"].append(normalized)
            valid_codes["products"].add(str(row["_code"]))
            seller_id = normalized["values"].get("seller_company_id")
            if seller_id is not None:
                active_seller_ids.add(uuid.UUID(str(seller_id)))

    _normalize_product_chassis_values(
        plan=plan,
        rows=raw_rows["product_chassis_values"],
        product_categories=product_categories,
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_product_superstructure_values(
        plan=plan,
        rows=raw_rows["product_superstructure_values"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
    )
    _normalize_offering_links(
        plan=plan,
        rows=raw_rows["product_attachments"],
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
        family="product_attachments",
    )
    _apply_job_target_warehouse(
        plan,
        target_warehouse_id=job.get("target_warehouse_id"),
        context=context,
        issues=issues,
        valid_codes=valid_codes,
    )
    _validate_offering_classification(
        plan=plan,
        context=context,
        mode=mode,
        issues=issues,
    )
    _validate_published_product_final_state(
        plan=plan,
        context=context,
        mode=mode,
        issues=issues,
    )

    _preflight_required_columns(
        plan=plan,
        issues=issues,
        valid_codes=valid_codes,
    )

    _prune_rejected_aggregate_links(
        plan,
        valid_codes=valid_codes,
        context=context,
        submitted_root_codes={
            family: {
                code
                for row in raw_rows[family]
                if (code := str(row.get("code") or "").strip())
            }
            for family in ("modifications", "products", "superstructures")
        },
    )
    summary = _build_summary(
        raw_rows=raw_rows,
        plan=plan,
        issues=issues,
        mode=mode,
    )
    expected_product_versions = {
        uuid.UUID(str(record["id"])): int(record["lock_version"])
        for code, record in context.get("products", {}).items()
        if code in valid_codes["products"]
    }
    return plan, issues, summary, expected_product_versions, active_seller_ids


def _apply_job_target_warehouse(
    plan: dict[str, JsonlRows],
    *,
    target_warehouse_id: uuid.UUID | None,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    valid_codes: dict[str, set[str]],
) -> None:
    """Validate and materialize the job fallback so preview and apply agree."""

    if target_warehouse_id is None:
        return
    target = context.get("warehouses", {}).get(str(target_warehouse_id))
    rows: list[dict[str, Any]] = []
    rejected_codes: set[str] = set()
    for row in plan["products"]:
        normalized_row = dict(row)
        values = dict(row.get("values") or {})
        if (
            row.get("operation") != "DELETE"
            and not bool(values.get("no_vin"))
        ):
            try:
                if target is None:
                    raise SpecialEquipmentManagementValidationError(
                        "Склад не найден"
                    )
                if target.get("status") != "active":
                    raise SpecialEquipmentManagementValidationError(
                        "Склад неактивен"
                    )
                ensure_warehouse_owner_matches_seller(
                    company_id=(
                        uuid.UUID(str(target["company_id"]))
                        if target.get("company_id") is not None
                        else None
                    ),
                    dealer_id=(
                        uuid.UUID(str(target["dealer_id"]))
                        if target.get("dealer_id") is not None
                        else None
                    ),
                    seller_company_id=(
                        uuid.UUID(str(values["seller_company_id"]))
                        if values.get("seller_company_id") is not None
                        else None
                    ),
                )
            except (SpecialEquipmentManagementValidationError, ValueError) as exc:
                code = str(row.get("_aggregate_code") or row.get("code") or "")
                rejected_codes.add(code)
                valid_codes["products"].discard(code)
                issues.append(
                    _row_issue(
                        row,
                        "TARGET_WAREHOUSE_INVALID",
                        str(exc),
                        entity_code=code,
                        column_name="ID склада",
                    )
                )
                continue
            before = values.get("warehouse_id")
            values["warehouse_id"] = target_warehouse_id
            normalized_row["values"] = values
            if before != target_warehouse_id:
                normalized_row["_warehouse_before"] = before
                normalized_row["_warehouse_target_applied"] = True
                if normalized_row.get("operation") == "NOOP":
                    normalized_row["operation"] = "SET"
        rows.append(normalized_row)
    plan["products"].replace(rows)
    if rejected_codes:
        for family in (
            "product_categories",
            "product_chassis_values",
            "product_superstructure_values",
            "product_attachments",
        ):
            plan[family].replace(
                row
                for row in plan[family]
                if str(row.get("_aggregate_code") or "") not in rejected_codes
            )


_apply_target_warehouse_assignment = _apply_job_target_warehouse


def _planned_attachment_ids(
    *,
    context: Mapping[str, Any],
    plan: Mapping[str, JsonlRows],
    mode: ImportMode,
    graph: CategoryGraph,
) -> frozenset[uuid.UUID]:
    category_attachment: dict[uuid.UUID, bool] = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            uuid.UUID(str(row["id"])): bool(row.get("is_attachment_category", False))
            for row in context.get("categories", {}).values()
        }
    )
    for row in plan.get("categories", ()):
        category_id = uuid.UUID(str(row["id"]))
        if row["operation"] == "DELETE":
            category_attachment.pop(category_id, None)
        else:
            raw_attachment = row["values"].get("is_attachment_category")
            if isinstance(raw_attachment, bool):
                category_attachment[category_id] = raw_attachment
            elif raw_attachment is not None:
                category_attachment[category_id] = bool(parse_bool(raw_attachment))
            else:
                category_attachment[category_id] = category_attachment.get(
                    category_id, False
                )
    attachment_roots = [
        category_id
        for category_id, is_attachment in category_attachment.items()
        if is_attachment and category_id in graph.category_ids
    ]
    return attachment_branch_ids(
        graph=graph,
        attachment_roots=attachment_roots,
    )


def _validate_card_attribute_limit_plan(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> None:
    """Reject structural import aggregates that make a modification exceed six."""

    structural_rows = [
        *plan["category_relations"],
        *plan["category_attributes"],
        *plan["modification_categories"],
    ]
    if not structural_rows:
        return
    effective_entities = _effective_catalog_entities(
        context=context,
        plan=plan,
        mode=mode,
    )
    category_ids = set(effective_entities["categories"])
    edges = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(parent_id)), uuid.UUID(str(child_id)))
            for parent_id, child_id in context.get("category_relations", set())
        }
    )
    for row in plan["category_relations"]:
        edge = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            edges.discard(edge)
        else:
            edges.add(edge)
    graph = CategoryGraph.from_edges(category_ids=category_ids, edges=edges)
    planned_attachment_ids = _planned_attachment_ids(
        context=context,
        plan=plan,
        mode=mode,
        graph=graph,
    )
    rule_graph = rule_inheritance_graph(
        graph=graph,
        attachment_ids=planned_attachment_ids,
    )

    final_rules = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(category_id)), uuid.UUID(str(attribute_id))): dict(rule)
            for (category_id, attribute_id), rule in context.get(
                "category_attributes", {}
            ).items()
        }
    )
    for row in plan["category_attributes"]:
        key = (
            uuid.UUID(str(row["values"]["category_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        if row["operation"] == "DELETE":
            final_rules.pop(key, None)
        else:
            final_rules[key] = dict(row["values"])
    rules_by_category: dict[uuid.UUID, list[CategoryAttributeRule]] = defaultdict(list)
    for (category_id, attribute_id), rule in final_rules.items():
        rules_by_category[category_id].append(
            CategoryAttributeRule(
                attribute_id=attribute_id,
                group_id=(
                    uuid.UUID(str(rule["group_id"]))
                    if rule.get("group_id") is not None
                    else None
                ),
                is_required=bool(rule.get("is_required")),
                is_filterable=bool(rule.get("is_filterable")),
                is_visible=bool(rule.get("is_visible")),
                sort_order=int(rule.get("sort_order") or 0),
            )
        )

    categories_by_modification: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if mode is not ImportMode.FULL_SNAPSHOT:
        for modification_id, categories in context.get(
            "_modification_category_details", {}
        ).items():
            categories_by_modification[uuid.UUID(str(modification_id))].update(
                uuid.UUID(str(category_id)) for category_id in categories
            )
    row_by_modification: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["modification_categories"]:
        modification_id = uuid.UUID(str(row["values"]["modification_id"]))
        category_id = uuid.UUID(str(row["values"]["category_id"]))
        row_by_modification.setdefault(modification_id, row)
        if row["operation"] == "DELETE":
            categories_by_modification[modification_id].discard(category_id)
        else:
            categories_by_modification[modification_id].add(category_id)

    invalid_modifications: set[uuid.UUID] = set()
    for (
        modification_id,
        modification_category_ids,
    ) in categories_by_modification.items():
        try:
            ensure_card_attribute_limit(
                graph=rule_graph,
                category_ids=tuple(sorted(modification_category_ids, key=str)),
                rules_by_category=rules_by_category,
            )
        except SpecialEquipmentCatalogError as exc:
            invalid_modifications.add(modification_id)
            representative = row_by_modification.get(
                modification_id,
                structural_rows[0],
            )
            issues.append(
                _row_issue(
                    representative,
                    "CARD_ATTRIBUTE_LIMIT_EXCEEDED",
                    str(exc),
                    entity_code=str(representative.get("_aggregate_code") or ""),
                )
            )
    if not invalid_modifications:
        return
    plan["modification_categories"].replace(
        row
        for row in plan["modification_categories"]
        if uuid.UUID(str(row["values"]["modification_id"])) not in invalid_modifications
    )
    if plan["category_relations"] or plan["category_attributes"]:
        plan["category_relations"].replace(())
        plan["category_attributes"].replace(())


def _effective_planned_attachment_ids(
    *,
    context: Mapping[str, Any],
    plan: Mapping[str, JsonlRows],
    mode: ImportMode,
) -> frozenset[uuid.UUID]:
    entities = _effective_catalog_entities(context=context, plan=plan, mode=mode)
    category_ids = set(entities["categories"])
    edges = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(parent_id)), uuid.UUID(str(child_id)))
            for parent_id, child_id in context.get("category_relations", set())
        }
    )
    for row in plan.get("category_relations", ()):
        edge = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            edges.discard(edge)
        else:
            edges.add(edge)
    graph = CategoryGraph.from_edges(category_ids=category_ids, edges=edges)
    return _planned_attachment_ids(
        context=context,
        plan=plan,
        mode=mode,
        graph=graph,
    )


def _effective_category_contract(
    *,
    plan: Mapping[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
) -> tuple[
    CategoryGraph,
    dict[uuid.UUID, list[CategoryAttributeRule]],
    dict[uuid.UUID, set[uuid.UUID]],
]:
    """Build the final category/rule state shared by import parity checks."""

    entities = _effective_catalog_entities(context=context, plan=plan, mode=mode)
    category_ids = set(entities["categories"])
    edges = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(parent_id)), uuid.UUID(str(child_id)))
            for parent_id, child_id in context.get("category_relations", set())
        }
    )
    for row in plan["category_relations"]:
        edge = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            edges.discard(edge)
        else:
            edges.add(edge)
    graph = CategoryGraph.from_edges(category_ids=category_ids, edges=edges)
    planned_attachment_ids = _planned_attachment_ids(
        context=context,
        plan=plan,
        mode=mode,
        graph=graph,
    )
    rule_graph = rule_inheritance_graph(
        graph=graph,
        attachment_ids=planned_attachment_ids,
    )

    final_rules = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(category_id)), uuid.UUID(str(attribute_id))): dict(rule)
            for (category_id, attribute_id), rule in context.get(
                "category_attributes", {}
            ).items()
        }
    )
    for row in plan["category_attributes"]:
        key = (
            uuid.UUID(str(row["values"]["category_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        if row["operation"] == "DELETE":
            final_rules.pop(key, None)
        else:
            final_rules[key] = dict(row["values"])
    rules_by_category: dict[uuid.UUID, list[CategoryAttributeRule]] = defaultdict(list)
    for (category_id, attribute_id), rule in final_rules.items():
        rules_by_category[category_id].append(
            CategoryAttributeRule(
                attribute_id=attribute_id,
                group_id=(
                    uuid.UUID(str(rule["group_id"]))
                    if rule.get("group_id") is not None
                    else None
                ),
                is_required=bool(rule.get("is_required")),
                is_filterable=bool(rule.get("is_filterable")),
                is_visible=bool(rule.get("is_visible")),
                sort_order=int(rule.get("sort_order") or 0),
            )
        )

    categories_by_modification: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if mode is not ImportMode.FULL_SNAPSHOT:
        for modification_id, categories in context.get(
            "_modification_category_details", {}
        ).items():
            categories_by_modification[uuid.UUID(str(modification_id))].update(
                uuid.UUID(str(category_id)) for category_id in categories
            )
    for row in plan["modification_categories"]:
        modification_id = uuid.UUID(str(row["values"]["modification_id"]))
        category_id = uuid.UUID(str(row["values"]["category_id"]))
        if row["operation"] == "DELETE":
            categories_by_modification[modification_id].discard(category_id)
        else:
            categories_by_modification[modification_id].add(category_id)
    return rule_graph, rules_by_category, categories_by_modification


def _validate_modification_category_presence(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    valid_codes: Mapping[str, set[str]],
    issues: V2IssueCollector,
) -> None:
    """Do not let import create or retain a modification without a category."""

    if not plan["modifications"] and not plan["modification_categories"]:
        return
    _graph, _rules, categories_by_modification = _effective_category_contract(
        plan=plan,
        context=context,
        mode=mode,
    )
    effective_modifications = _effective_catalog_entities(
        context=context,
        plan=plan,
        mode=mode,
    )["modifications"]
    modification_rows = {
        uuid.UUID(str(row["id"])): row for row in plan["modifications"]
    }
    category_rows: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["modification_categories"]:
        category_rows.setdefault(uuid.UUID(str(row["values"]["modification_id"])), row)
    impacted = set(modification_rows) | set(category_rows)
    invalid = {
        modification_id
        for modification_id in impacted
        if modification_id in effective_modifications
        and not categories_by_modification.get(modification_id)
    }
    if not invalid:
        return
    for modification_id in sorted(invalid, key=str):
        representative = (
            modification_rows.get(modification_id) or category_rows[modification_id]
        )
        issues.append(
            _row_issue(
                representative,
                "MODIFICATION_CATEGORY_REQUIRED",
                "У модификации должна быть основная категория",
                entity_code=str(representative.get("_aggregate_code") or ""),
                column_name="Код категории",
            )
        )
        code = str(representative.get("_aggregate_code") or "")
        valid_codes.get("modifications", set()).discard(code)
    plan["modifications"].replace(
        row for row in plan["modifications"] if uuid.UUID(str(row["id"])) not in invalid
    )
    plan["modification_categories"].replace(
        row
        for row in plan["modification_categories"]
        if uuid.UUID(str(row["values"]["modification_id"])) not in invalid
    )


def _validate_modification_attribute_scope_plan(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> None:
    """Restrict modification values to effective category attributes."""

    if not plan["modification_attribute_values"]:
        return
    graph, rules_by_category, categories_by_modification = _effective_category_contract(
        plan=plan, context=context, mode=mode
    )
    rejected: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for row in plan["modification_attribute_values"]:
        if row["operation"] == "DELETE":
            continue
        modification_id = uuid.UUID(str(row["values"]["modification_id"]))
        attribute_id = uuid.UUID(str(row["values"]["attribute_id"]))
        allowed = {
            rule.attribute_id
            for category_id in categories_by_modification.get(modification_id, ())
            for rule in effective_attribute_rules(
                graph=graph,
                category_id=category_id,
                rules_by_category=rules_by_category,
            )
        }
        if attribute_id in allowed:
            continue
        rejected.add((modification_id, attribute_id))
        issues.append(
            _row_issue(
                row,
                "MODIFICATION_ATTRIBUTE_OUTSIDE_CATEGORY_SCOPE",
                "Значения модификации разрешены только для характеристик выбранных категорий",
                entity_code=str(row.get("_aggregate_code") or ""),
                column_name="Код характеристики",
            )
        )
    if rejected:
        plan["modification_attribute_values"].replace(
            row
            for row in plan["modification_attribute_values"]
            if (
                uuid.UUID(str(row["values"]["modification_id"])),
                uuid.UUID(str(row["values"]["attribute_id"])),
            )
            not in rejected
        )


def _validate_attribute_graph_mutation_plan(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    valid_codes: Mapping[str, set[str]],
    issues: V2IssueCollector,
) -> None:
    """Keep generic attribute writes aligned with management dependencies."""

    if (
        not plan["attribute_groups"]
        and not plan["attributes"]
        and not plan["attribute_options"]
    ):
        return

    current_groups = {
        uuid.UUID(str(record["id"])): dict(record)
        for record in context.get("attribute_groups", {}).values()
    }
    groups = {} if mode is ImportMode.FULL_SNAPSHOT else dict(current_groups)
    group_rows: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["attribute_groups"]:
        entity_id = uuid.UUID(str(row["id"]))
        group_rows[entity_id] = row
        if row["operation"] == "DELETE":
            groups.pop(entity_id, None)
        else:
            groups[entity_id] = {
                **groups.get(entity_id, {}),
                **dict(row["values"]),
                "id": entity_id,
                "code": str(row["code"]),
            }

    current_attributes = {
        uuid.UUID(str(record["id"])): dict(record)
        for record in context.get("attributes", {}).values()
    }
    attributes = {} if mode is ImportMode.FULL_SNAPSHOT else dict(current_attributes)
    attribute_rows: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["attributes"]:
        entity_id = uuid.UUID(str(row["id"]))
        attribute_rows[entity_id] = row
        if row["operation"] == "DELETE":
            attributes.pop(entity_id, None)
        else:
            attributes[entity_id] = {
                **attributes.get(entity_id, {}),
                **dict(row["values"]),
                "id": entity_id,
                "code": str(row["code"]),
            }
            if attributes[entity_id].get("attribute_group_id") is not None:
                attributes[entity_id]["attribute_group_id"] = uuid.UUID(
                    str(attributes[entity_id]["attribute_group_id"])
                )

    category_rules = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(category_id)), uuid.UUID(str(attribute_id))): dict(rule)
            for (category_id, attribute_id), rule in context.get(
                "category_attributes", {}
            ).items()
        }
    )
    for row in plan["category_attributes"]:
        key = (
            uuid.UUID(str(row["values"]["category_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        if row["operation"] == "DELETE":
            category_rules.pop(key, None)
        else:
            category_rules[key] = dict(row["values"])

    value_keys = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(owner_id)), uuid.UUID(str(attribute_id)))
            for family in (
                "modification_attribute_values",
                "trim_attribute_values",
            )
            for owner_id, attribute_id in context.get(family, set())
        }
    )
    for family in ("modification_attribute_values", "trim_attribute_values"):
        owner_field = (
            "modification_id"
            if family == "modification_attribute_values"
            else "trim_id"
        )
        for row in plan[family]:
            key = (
                uuid.UUID(str(row["values"][owner_field])),
                uuid.UUID(str(row["values"]["attribute_id"])),
            )
            if row["operation"] == "DELETE":
                value_keys.discard(key)
            else:
                value_keys.add(key)
    value_attribute_ids = {attribute_id for _owner_id, attribute_id in value_keys}
    rule_attribute_ids = {attribute_id for _category_id, attribute_id in category_rules}
    rule_group_ids = {
        uuid.UUID(str(rule["group_id"]))
        for rule in category_rules.values()
        if rule.get("group_id") is not None
    }

    options = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            uuid.UUID(str(record["id"])): dict(record)
            for record in context.get("attribute_options", {}).values()
        }
    )
    option_rows: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["attribute_options"]:
        option_id = uuid.UUID(str(row["id"]))
        option_rows[option_id] = row
        if row["operation"] == "DELETE":
            options.pop(option_id, None)
        else:
            options[option_id] = {
                **options.get(option_id, {}),
                **dict(row["values"]),
                "id": option_id,
                "code": str(row["code"]),
            }
            if options[option_id].get("attribute_id") is not None:
                options[option_id]["attribute_id"] = uuid.UUID(
                    str(options[option_id]["attribute_id"])
                )

    value_details: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {}
    if mode is not ImportMode.FULL_SNAPSHOT:
        for family in ("modification", "trim"):
            for (owner_id, attribute_id), detail in context.get(
                f"_{family}_attribute_value_details", {}
            ).items():
                value_details[
                    (uuid.UUID(str(owner_id)), uuid.UUID(str(attribute_id)))
                ] = dict(detail)
    for family in ("modification_attribute_values", "trim_attribute_values"):
        owner_field = (
            "modification_id"
            if family == "modification_attribute_values"
            else "trim_id"
        )
        for row in plan[family]:
            key = (
                uuid.UUID(str(row["values"][owner_field])),
                uuid.UUID(str(row["values"]["attribute_id"])),
            )
            if row["operation"] == "DELETE":
                value_details.pop(key, None)
            else:
                value_details[key] = dict(row["values"])
    referenced_option_ids = {
        uuid.UUID(str(detail["option_id"]))
        for detail in value_details.values()
        if detail.get("option_id") is not None
    }

    rejected_groups: set[uuid.UUID] = set()
    for group_id, row in group_rows.items():
        target = groups.get(group_id)
        if target is not None and target.get("is_active"):
            continue
        has_members = (
            any(
                attribute.get("attribute_group_id") == group_id
                for attribute in attributes.values()
            )
            or group_id in rule_group_ids
        )
        if not has_members:
            continue
        rejected_groups.add(group_id)
        issues.append(
            _row_issue(
                row,
                "ATTRIBUTE_GROUP_DEACTIVATION_BLOCKED",
                "Нельзя деактивировать группу, используемую характеристиками",
                entity_code=str(row.get("_aggregate_code") or ""),
                column_name="Активность",
            )
        )

    rejected_attributes: set[uuid.UUID] = set()
    for attribute_id, row in attribute_rows.items():
        current = current_attributes.get(attribute_id)
        target = attributes.get(attribute_id)
        reason: str | None = None
        column_name = "Тип данных"
        if (
            current is not None
            and target is not None
            and target.get("data_type") != current.get("data_type")
            and attribute_id in value_attribute_ids
        ):
            reason = "Смена типа заблокирована сохранёнными значениями"
        elif (
            target is not None
            and target.get("data_type") != "select"
            and any(
                option.get("attribute_id") == attribute_id
                for option in options.values()
            )
        ):
            reason = "Варианты допустимы только для select-характеристики"
        elif (
            target is not None
            and not target.get("is_active")
            and (
                attribute_id in rule_attribute_ids
                or attribute_id in value_attribute_ids
            )
        ):
            reason = "Нельзя деактивировать используемую характеристику"
            column_name = "Активность"
        elif (
            target is not None
            and target.get("attribute_group_id") is not None
            and (
                target["attribute_group_id"] not in groups
                or not groups[target["attribute_group_id"]].get("is_active")
            )
        ):
            reason = "Нельзя назначить неактивную группу характеристик"
            column_name = "Код группы"
        if reason is None:
            continue
        rejected_attributes.add(attribute_id)
        issues.append(
            _row_issue(
                row,
                "ATTRIBUTE_MUTATION_BLOCKED",
                reason,
                entity_code=str(row.get("_aggregate_code") or ""),
                column_name=column_name,
            )
        )

    rejected_options: set[uuid.UUID] = set()
    for option_id, row in option_rows.items():
        target = options.get(option_id)
        if option_id not in referenced_option_ids or (
            target is not None and target.get("is_active")
        ):
            continue
        rejected_options.add(option_id)
        issues.append(
            _row_issue(
                row,
                "ATTRIBUTE_OPTION_DEACTIVATION_BLOCKED",
                "Нельзя деактивировать используемый вариант характеристики",
                entity_code=str(row.get("_aggregate_code") or ""),
                column_name="Активность",
            )
        )

    if rejected_groups:
        plan["attribute_groups"].replace(
            row
            for row in plan["attribute_groups"]
            if uuid.UUID(str(row["id"])) not in rejected_groups
        )
    if rejected_attributes:
        for row in attribute_rows.values():
            if uuid.UUID(str(row["id"])) in rejected_attributes:
                valid_codes.get("attributes", set()).discard(str(row["code"]))
        plan["attributes"].replace(
            row
            for row in plan["attributes"]
            if uuid.UUID(str(row["id"])) not in rejected_attributes
        )
        plan["attribute_options"].replace(
            row
            for row in plan["attribute_options"]
            if row["values"].get("attribute_id") is None
            or uuid.UUID(str(row["values"]["attribute_id"])) not in rejected_attributes
        )
        for family in (
            "category_attributes",
            "modification_attribute_values",
            "trim_attributes",
            "trim_attribute_values",
        ):
            plan[family].replace(
                row
                for row in plan[family]
                if uuid.UUID(str(row["values"]["attribute_id"]))
                not in rejected_attributes
            )
    if rejected_options:
        plan["attribute_options"].replace(
            row
            for row in plan["attribute_options"]
            if uuid.UUID(str(row["id"])) not in rejected_options
        )


def _effective_catalog_entities(
    *,
    context: Mapping[str, Any],
    plan: Mapping[str, JsonlRows],
    mode: ImportMode,
) -> dict[str, dict[uuid.UUID, dict[str, Any]]]:
    families = (
        "marks",
        "models",
        "modifications",
        "trims",
        "categories",
        "colors",
    )
    effective: dict[str, dict[uuid.UUID, dict[str, Any]]] = {}
    for family in families:
        current = (
            {}
            if mode is ImportMode.FULL_SNAPSHOT
            else {
                uuid.UUID(str(record["id"])): dict(record)
                for record in context.get(family, {}).values()
            }
        )
        for row in plan[family]:
            entity_id = uuid.UUID(str(row["id"]))
            if row["operation"] == "DELETE":
                current.pop(entity_id, None)
                continue
            values = dict(row["values"])
            reference_field = {
                "models": "mark_id",
                "modifications": "model_id",
                "trims": "modification_id",
            }.get(family)
            if reference_field and values.get(reference_field) is not None:
                values[reference_field] = uuid.UUID(str(values[reference_field]))
            current[entity_id] = {
                **current.get(entity_id, {}),
                **values,
                "id": entity_id,
                "code": str(row["code"]),
            }
        effective[family] = current
    return effective


def _requested_codes(
    rows: Mapping[str, list[dict[str, Any]]],
    issues: V2IssueCollector,
) -> tuple[dict[str, set[str]], set[str]]:
    requested: dict[str, set[str]] = defaultdict(set)
    fields = {
        "units_codes": ("unit_code",),
        "marks_codes": ("mark_code",),
        "models_codes": (
            "model_code",
            "superstructure_model_code",
        ),
        "modifications_codes": (
            "modification_code",
            "superstructure_modification_code",
        ),
        "superstructures_codes": ("superstructure_code",),
        "categories_codes": (
            "category_code",
            "parent_category_code",
            "child_category_code",
        ),
        "attribute_groups_codes": ("group_code",),
        "attributes_codes": ("attribute_code",),
        "products_codes": (
            "product_code",
            "attachment_product_code",
            "superstructure_source_code",
        ),
    }
    for family in _ENTITY_FAMILIES:
        for row in rows[family]:
            code_field = "code"
            code = str(row.get(code_field) or "").strip()
            if family == "attribute_options":
                code = str(row.get("code") or "").strip()
            if code:
                requested[f"{family}_codes"].add(code)
    for family_rows in rows.values():
        for row in family_rows:
            for target, candidate_fields in fields.items():
                for field in candidate_fields:
                    value = str(row.get(field) or "").strip()
                    if value:
                        requested[target].add(value)
    sellers = {
        str(row.get("seller_inn") or "").strip()
        for row in rows["products"]
        if str(row.get("seller_inn") or "").strip()
    }
    requested["warehouse_ids"].update(
        str(row.get("warehouse_id") or "").strip()
        for row in rows["products"]
        if str(row.get("warehouse_id") or "").strip()
        and "warehouse_id" not in set(row.get("_clear_fields") or ())
    )
    if any(len(code) > 255 for values in requested.values() for code in values):
        issues.append(_manifest_issue("CODE_TOO_LONG"))
    return dict(requested), sellers


def _prepare_entity_identity(
    *,
    raw_rows: Mapping[str, list[dict[str, Any]]],
    context: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> tuple[dict[str, dict[str, uuid.UUID]], dict[str, list[dict[str, Any]]]]:
    identity: dict[str, dict[str, uuid.UUID]] = defaultdict(dict)
    accepted: dict[str, list[dict[str, Any]]] = {
        family: [] for family in _ENTITY_FAMILIES
    }
    for family in _ENTITY_FAMILIES:
        existing = context.get(family, {})
        for key, record in existing.items():
            identity[family][str(key)] = uuid.UUID(str(record["id"]))
        seen: dict[str, str] = {}
        for row in raw_rows[family]:
            code_column_name = "Код"
            try:
                raw_code = str(row.get("code") or "")
                code = (
                    normalize_color_code(
                        raw_code,
                        name=str(row.get("name") or raw_code),
                    )
                    if family == "colors"
                    else validate_entity_code(raw_code)
                )
                if family == "attribute_options":
                    identity_key = (
                        f"{str(row.get('attribute_code') or '').strip()}:{code}"
                    )
                elif family == "trims":
                    code_column_name = "Код модификации"
                    modification_code = validate_entity_code(
                        str(row.get("modification_code") or "")
                    )
                    identity_key = f"{modification_code}:{code}"
                else:
                    identity_key = code
                if family == "attribute_options" and identity_key.startswith(":"):
                    raise ImportContractError("Код характеристики обязателен")
            except (
                ImportContractError,
                SpecialEquipmentManagementValidationError,
            ) as exc:
                issues.append(
                    _row_issue(
                        row,
                        "CODE_INVALID",
                        str(exc),
                        column_name=code_column_name,
                    )
                )
                continue
            fingerprint = hashlib.sha256(
                json.dumps(
                    _comparable_row(row),
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ).encode("utf-8")
            ).hexdigest()
            if identity_key in seen:
                severity = (
                    IssueSeverity.WARNING
                    if seen[identity_key] == fingerprint
                    else IssueSeverity.ERROR
                )
                issues.append(
                    _row_issue(
                        row,
                        (
                            "IDENTICAL_DUPLICATE"
                            if severity is IssueSeverity.WARNING
                            else "CONFLICTING_DUPLICATE"
                        ),
                        (
                            "Повторяющаяся строка проигнорирована"
                            if severity is IssueSeverity.WARNING
                            else "Код повторён с разными значениями"
                        ),
                        severity=severity,
                        entity_code=code,
                    )
                )
                continue
            seen[identity_key] = fingerprint
            current = existing.get(identity_key)
            if row.get("operation") == "UPSERT":
                if mode is ImportMode.APPEND:
                    row["operation"] = "ADD"
                elif current is not None:
                    row["operation"] = "SET"
                else:
                    row["operation"] = "ADD"
            operation = str(row["operation"])
            if not _operation_target_is_valid(
                mode=mode,
                operation=operation,
                exists=current is not None,
            ):
                issues.append(
                    _row_issue(
                        row,
                        "OPERATION_TARGET_INVALID",
                        "Действие не соответствует наличию записи в каталоге",
                        entity_code=code,
                    )
                )
                continue
            entity_type = (
                "unit"
                if family == "units"
                else ("superstructure" if family == "superstructures" else family)
            )
            entity_id = (
                uuid.UUID(str(current["id"]))
                if current is not None
                else deterministic_entity_id(entity_type, identity_key)
            )
            identity[family][identity_key] = entity_id
            prepared = {
                **row,
                "_code": code,
                "_identity_key": identity_key,
                "_id": entity_id,
            }
            accepted[family].append(prepared)
    return identity, accepted


def _operation_target_is_valid(
    *, mode: ImportMode, operation: str, exists: bool
) -> bool:
    if mode is ImportMode.APPEND:
        return operation == "ADD" and not exists
    if mode is ImportMode.PATCH:
        if operation == "ADD":
            return not exists
        return exists
    return operation in {"ADD", "SET"} and (operation != "ADD" or not exists)


def _normalize_directory_entity(
    *,
    family: str,
    row: dict[str, Any],
    mode: ImportMode,
    context: Mapping[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    operation = str(row["operation"])
    code = str(row["_code"])
    if operation == "DELETE":
        return _entity_plan_row(family=family, row=row, values={})
    try:
        normalized_row = row
        if family == "attributes":
            normalized_row = dict(row)
            group_code = str(row.get("group_code") or "").strip()
            clear_fields = set(row.get("_clear_fields") or ())
            group_id: uuid.UUID | None = None
            if group_code:
                group_id = _resolve_reference(
                    family="attribute_groups",
                    code=group_code,
                    identity=identity,
                    valid_codes=valid_codes,
                    context=context,
                    mode=mode,
                    row=row,
                    issues=issues,
                    not_found_code="ATTRIBUTES_INVALID",
                    not_found_message="Группа характеристики по умолчанию не найдена",
                    entity_code=code,
                    column_name="Код группы по умолчанию",
                )
                if group_id is None:
                    return None
            normalized_row["attribute_group_id"] = group_id
            if "group_code" in clear_fields:
                clear_fields.remove("group_code")
                clear_fields.add("attribute_group_id")

            unit_code = str(row.get("unit_code") or "").strip()
            unit_id: uuid.UUID | None = None
            if unit_code:
                unit_id = _resolve_reference(
                    family="units",
                    code=unit_code,
                    identity=identity,
                    valid_codes=valid_codes,
                    context=context,
                    mode=mode,
                    row=row,
                    issues=issues,
                    not_found_code="ATTRIBUTES_INVALID",
                    not_found_message="Единица измерения не найдена",
                    entity_code=code,
                    column_name="Код единицы измерения",
                )
                if unit_id is None:
                    return None
            normalized_row["unit_id"] = unit_id
            if "unit_code" in clear_fields:
                clear_fields.remove("unit_code")
                clear_fields.add("unit_id")
            normalized_row["_clear_fields"] = sorted(clear_fields)
        current = context.get(family, {}).get(code, {})
        values = _merge_values(
            row=normalized_row,
            current=current,
            mode=mode,
            fields=_directory_fields(family),
            required={"name"},
            family=family,
            defaults=_DIRECTORY_FIELD_DEFAULTS.get(family, {}),
        )
        values["slug"] = generate_catalog_slug(str(values["name"]))
        if family == "categories":
            if not values.get("usage_metric"):
                raise ImportContractError("Показатель эксплуатации обязателен")
            values["usage_metric"] = normalize_usage_metric(values["usage_metric"])
            values["sort_order"] = _nonnegative_int(values.get("sort_order", 0))
            if not _attach_category_image_action(
                values=values, row=row, mode=mode, issues=issues
            ):
                return None
        elif family == "attribute_groups":
            values["sort_order"] = _nonnegative_int(values.get("sort_order", 0))
        elif family == "attributes":
            if public_special_equipment_attribute_code(code) is None:
                raise ImportContractError(
                    "Attribute code is reserved for private or internal data"
                )
            if not values.get("data_type") or not values.get("filter_kind"):
                raise ImportContractError(
                    "Тип данных и тип фильтра характеристики обязательны"
                )
            if values["filter_kind"] == "range" and values["data_type"] != "number":
                raise ImportContractError(
                    "Диапазон разрешён только для числовой характеристики"
                )
            if values["filter_kind"] == "search" and values["data_type"] != "text":
                raise ImportContractError(
                    "Текстовый поиск разрешён только для текстовой характеристики"
                )
    except (ImportContractError, ValueError, TypeError) as exc:
        column_name = getattr(exc, "column_name", None)
        issues.append(
            _row_issue(
                row,
                f"{_aggregate_kind_for_family(family).upper()}_INVALID",
                str(exc),
                entity_code=code,
                column_name=column_name,
            )
        )
        return None
    return _entity_plan_row(family=family, row=row, values=values)


def _directory_fields(family: str) -> tuple[str, ...]:
    return {
        "units": ("name", "is_active"),
        "marks": ("name", "is_active"),
        "categories": (
            "name",
            "usage_metric",
            "is_attachment_category",
            "is_visible_in_catalog",
            "sort_order",
            "is_active",
        ),
        "attribute_groups": ("name", "sort_order", "is_active"),
        "attributes": (
            "name",
            "attribute_group_id",
            "data_type",
            "unit_id",
            "filter_kind",
            "is_active",
        ),
    }[family]


def _attach_category_image_action(  # noqa: PLR0911
    *,
    values: dict[str, Any],
    row: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> bool:
    clear_fields = set(row.get("_clear_fields") or ())
    if "image_source_url" in clear_fields:
        values["_image_action"] = "clear"
        return True
    raw_url = row.get("image_source_url")
    if raw_url is None or not str(raw_url).strip():
        if mode is ImportMode.PATCH and row.get("operation") == "SET":
            return True
        return True

    parsed = parse_image_source_urls(
        str(raw_url),
        allowed_hosts=settings.special_equipment_image_source_hosts,
        limit=50,
    )
    if any(issue.code == "PRODUCT_IMAGE_CLEAR_MIXED" for issue in parsed.issues):
        issues.append(
            _row_issue(
                row,
                "CATEGORY_INVALID",
                "Значение «Очистить» нельзя совмещать со ссылками на изображение",
                entity_code=str(row.get("_code") or ""),
                column_name="Картинка",
            )
        )
        return False
    if parsed.is_clear:
        values["_image_action"] = "clear"
        return True
    if len(parsed.refs) > 1:
        issues.append(
            _row_issue(
                row,
                "CATEGORY_IMAGE_MULTIPLE",
                "Для категории допускается одна ссылка на изображение",
                entity_code=str(row.get("_code") or ""),
                column_name="Картинка",
            )
        )
        return False
    if len(parsed.refs) == 1:
        values["_image_action"] = "replace"
        values["_image_source_url"] = parsed.refs[0].raw_url
        return True

    values["_image_action"] = "replace"
    values["_image_source_url"] = str(raw_url).strip()
    return True


def _attach_image_action(
    *,
    values: dict[str, Any],
    row: Mapping[str, Any],
    mode: ImportMode,
) -> None:
    """Keep PATCH blank/clear/replace semantics explicit in the private plan."""

    clear_fields = set(row.get("_clear_fields") or ())
    if "image_source_url" in clear_fields:
        values["_image_action"] = "clear"
        return
    raw_url = row.get("image_source_url")
    if raw_url is None or not str(raw_url).strip():
        if mode is ImportMode.PATCH and row.get("operation") == "SET":
            return
        return
    values["_image_action"] = "replace"
    values["_image_source_url"] = str(raw_url).strip()


def _normalize_model(
    *,
    row: dict[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="models", row=row, values={})
    mark_code = str(row.get("mark_code") or "").strip()
    mark_id = _resolve_reference(
        family="marks",
        code=mark_code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
        row=row,
        issues=issues,
        not_found_code="MARK_NOT_FOUND",
        not_found_message="Не найдена активная марка модели",
        entity_code=code,
        column_name="Код марки",
    )
    category_code = str(row.get("category_code") or "").strip()
    category_id = None
    clear_fields = set(row.get("_clear_fields") or ())
    if "category_code" in clear_fields or "category_id" in clear_fields:
        category_id = None
    elif category_code:
        category_id = _resolve_reference(
            family="categories",
            code=category_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="CATEGORY_NOT_FOUND",
            not_found_message="Не найдена активная категория модели",
            entity_code=code,
            column_name="Код категории",
        )
        if category_id is None:
            return None
    elif mode is ImportMode.PATCH:
        current_model = context.get("models", {}).get(code, {})
        category_id = current_model.get("category_id")

    try:
        values = _merge_values(
            row=row,
            current=context.get("models", {}).get(code, {}),
            mode=mode,
            fields=("name", "is_active"),
            required={"name"},
            family="models",
        )
        values.update(
            mark_id=mark_id,
            slug=generate_catalog_slug(str(values["name"])),
        )
        if (
            category_id is not None
            or "category_code" in clear_fields
            or "category_id" in clear_fields
        ):
            values["category_id"] = category_id
    except (ImportContractError, ValueError, TypeError) as exc:
        issues.append(_row_issue(row, "MODEL_INVALID", str(exc), entity_code=code))
        return None
    return _entity_plan_row(family="models", row=row, values=values)


def _normalize_modification(
    *,
    row: dict[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="modifications", row=row, values={})
    model_code = str(row.get("model_code") or "").strip()
    model_id = _resolve_reference(
        family="models",
        code=model_code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
        row=row,
        issues=issues,
        not_found_code="MODEL_NOT_FOUND",
        not_found_message="Не найдена активная модель модификации",
        entity_code=code,
        column_name="Код модели",
    )
    if model_id is None:
        return None
    try:
        values = _merge_values(
            row=row,
            current=context.get("modifications", {}).get(code, {}),
            mode=mode,
            fields=("name", "year_from", "year_to", "is_active"),
            required={"name"},
            family="modifications",
        )
        values["year_from"] = _optional_year(values.get("year_from"))
        values["year_to"] = _optional_year(values.get("year_to"))
        if (
            values["year_from"] is not None
            and values["year_to"] is not None
            and values["year_from"] > values["year_to"]
        ):
            raise ImportContractError("Начальный год не может быть больше конечного")
        values.update(
            model_id=model_id,
            slug=generate_catalog_slug(str(values["name"])),
        )
    except (ImportContractError, ValueError, TypeError) as exc:
        issues.append(
            _row_issue(row, "MODIFICATION_INVALID", str(exc), entity_code=code)
        )
        return None
    return _entity_plan_row(family="modifications", row=row, values=values)


def _normalize_trim(
    *,
    row: dict[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    identity_key = str(row["_identity_key"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="trims", row=row, values={})
    modification_code = str(row.get("modification_code") or "").strip()
    modification_id = _resolve_reference(
        family="modifications",
        code=modification_code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
        row=row,
        issues=issues,
        not_found_code="TRIM_MODIFICATION_NOT_FOUND",
        not_found_message="Модификация комплектации не найдена",
        entity_code=identity_key,
        column_name="Код модификации",
    )
    if modification_id is None:
        return None
    try:
        values = _merge_values(
            row=row,
            current=context.get("trims", {}).get(identity_key, {}),
            mode=mode,
            fields=("name", "sort_order", "is_active"),
            required={"name"},
            family="trims",
        )
        values.update(
            modification_id=modification_id,
            sort_order=_nonnegative_int(values.get("sort_order", 0)),
            slug=generate_catalog_slug(str(values["name"])),
        )
    except (ImportContractError, ValueError, TypeError) as exc:
        issues.append(
            _row_issue(
                row,
                "TRIM_INVALID",
                str(exc),
                entity_code=identity_key,
                column_name="Название",
            )
        )
        return None
    return _entity_plan_row(family="trims", row=row, values=values)


def _normalize_superstructure(
    *,
    row: dict[str, Any],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    seen_names: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="superstructures", row=row, values={})

    current = context.get("superstructures", {}).get(code, {})
    try:
        values = _merge_values(
            row=row,
            current=current,
            mode=mode,
            fields=("name", "is_active"),
            required={"name"},
            family="superstructures",
            defaults={"is_active": True},
        )
        values["slug"] = generate_catalog_slug(str(values["name"]))
    except (ImportContractError, ValueError, TypeError) as exc:
        issues.append(
            _row_issue(
                row,
                "SUPERSTRUCTURE_INVALID",
                str(exc),
                entity_code=code,
                column_name="Название",
            )
        )
        return None

    normalized_name = str(values["name"]).strip().casefold()
    if seen_names is not None:
        if normalized_name in seen_names and seen_names[normalized_name] != code:
            issues.append(
                _row_issue(
                    row,
                    SUPERSTRUCTURE_NAME_CONFLICT,
                    "Название типа надстройки уже используется",
                    entity_code=code,
                    column_name="Название",
                )
            )
            return None
        seen_names[normalized_name] = code

    for existing_code, existing in context.get("superstructures", {}).items():
        if (
            str(existing_code) != code
            and str(existing.get("name") or "").strip().casefold() == normalized_name
        ):
            issues.append(
                _row_issue(
                    row,
                    SUPERSTRUCTURE_NAME_CONFLICT,
                    "Название типа надстройки уже используется",
                    entity_code=code,
                    column_name="Название",
                )
            )
            return None

    return _entity_plan_row(family="superstructures", row=row, values=values)


def _normalize_color(
    *,
    row: dict[str, Any],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="colors", row=row, values={})
    current = context.get("colors", {}).get(code, {})
    try:
        values = _merge_values(
            row=row,
            current=current,
            mode=mode,
            fields=("name", "applicability", "is_active"),
            required={"name", "applicability"},
            family="colors",
        )
        values["name"] = normalize_color_name(str(values["name"]))
        values["applicability"] = normalize_color_applicability(
            str(values["applicability"])
        )
        current_applicability = current.get("applicability")
        if (
            current_applicability is not None
            and values["applicability"] != current_applicability
        ):
            references = context.get("_color_product_references", {}).get(
                uuid.UUID(str(current["id"])),
                {},
            )
            ensure_color_applicability_change_allowed(
                current=str(current_applicability),
                requested=str(values["applicability"]),
                body_products_count=int(references.get("body", 0)),
                interior_products_count=int(references.get("interior", 0)),
            )
    except SpecialEquipmentColorValidationError as exc:
        issues.append(
            _row_issue(
                row,
                "COLOR_INVALID",
                str(exc),
                entity_code=code,
                column_name=(
                    "Применимость" if exc.field == "applicability" else "Название"
                ),
            )
        )
        return None
    except SpecialEquipmentColorConflictError as exc:
        issues.append(
            _row_issue(
                row,
                "COLOR_INVALID",
                str(exc),
                entity_code=code,
                column_name="Применимость",
            )
        )
        return None
    except (
        ImportContractError,
        SpecialEquipmentManagementValidationError,
        ValueError,
        TypeError,
    ) as exc:
        issues.append(
            _row_issue(
                row,
                "COLOR_INVALID",
                str(exc),
                entity_code=code,
                column_name="Применимость",
            )
        )
        return None
    return _entity_plan_row(family="colors", row=row, values=values)


def _normalize_attribute_option(
    *,
    plan: Mapping[str, JsonlRows],
    row: dict[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    attribute_code = str(row.get("attribute_code") or "").strip()
    attribute_id = _resolve_reference(
        family="attributes",
        code=attribute_code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
        row=row,
        issues=issues,
        not_found_code="ATTRIBUTE_NOT_FOUND",
        not_found_message="Не найдена характеристика варианта",
        entity_code=code,
        column_name="Код характеристики",
    )
    if attribute_id is None:
        return None
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="attribute_options", row=row, values={})
    definition = next(
        (
            planned["values"]
            for planned in plan["attributes"]
            if str(planned["code"]) == attribute_code
            and planned["operation"] != "DELETE"
        ),
        context.get("attributes", {}).get(attribute_code),
    )
    if definition is None or definition.get("data_type") != "select":
        issues.append(
            _row_issue(
                row,
                "ATTRIBUTE_OPTION_REQUIRES_SELECT",
                "Варианты разрешены только для характеристики-списка",
                entity_code=code,
                column_name="Код характеристики",
            )
        )
        return None
    try:
        current = context.get("attribute_options", {}).get(
            str(row["_identity_key"]), {}
        )
        values = _merge_values(
            row=row,
            current=current,
            mode=mode,
            fields=("name", "sort_order", "is_active"),
            required={"name"},
            family="attribute_options",
        )
        values["sort_order"] = _nonnegative_int(values.get("sort_order", 0))
        values["attribute_id"] = attribute_id
    except (ImportContractError, ValueError, TypeError) as exc:
        issues.append(
            _row_issue(row, "ATTRIBUTE_OPTION_INVALID", str(exc), entity_code=code)
        )
        return None
    return _entity_plan_row(family="attribute_options", row=row, values=values)


def _normalize_category_relations(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        parent_code = str(row.get("parent_category_code") or "").strip()
        child_code = str(row.get("child_category_code") or "").strip()
        parent_id = _resolve_reference(
            family="categories",
            code=parent_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="CATEGORY_RELATION_TARGET_NOT_FOUND",
            not_found_message="Родительская или дочерняя категория не найдена",
            entity_code=child_code or parent_code,
            column_name="Код родительской категории",
        )
        if parent_id is None:
            continue
        child_id = _resolve_reference(
            family="categories",
            code=child_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="CATEGORY_RELATION_TARGET_NOT_FOUND",
            not_found_message="Родительская или дочерняя категория не найдена",
            entity_code=child_code or parent_code,
            column_name="Код дочерней категории",
        )
        if child_id is None:
            continue
        try:
            sort_order = _nonnegative_int(row.get("sort_order", 0))
        except (ImportContractError, ValueError, TypeError) as exc:
            issues.append(
                _row_issue(
                    row,
                    "CATEGORY_RELATION_INVALID",
                    str(exc),
                    entity_code=child_code,
                )
            )
            continue
        normalized.append(
            _link_plan_row(
                row,
                values={
                    "parent_id": parent_id,
                    "child_id": child_id,
                    "sort_order": sort_order,
                },
                aggregate_kind="category",
                aggregate_code=child_code,
            )
        )
    if mode is ImportMode.FULL_SNAPSHOT:
        final_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
        final_category_ids: set[uuid.UUID] = set()
    else:
        final_edges = set(context.get("category_relations", set()))
        final_category_ids = {
            uuid.UUID(str(record["id"]))
            for record in context.get("categories", {}).values()
        }
    for code, category_id in identity["categories"].items():
        category_row = next(
            (row for row in plan["categories"] if str(row["code"]) == code),
            None,
        )
        if category_row is not None and category_row["operation"] == "DELETE":
            final_category_ids.discard(category_id)
        else:
            final_category_ids.add(category_id)
    for row in normalized:
        edge = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            final_edges.discard(edge)
        else:
            final_edges.add(edge)
    try:
        CategoryGraph.from_edges(
            category_ids=final_category_ids,
            edges=final_edges,
        )
    except SpecialEquipmentCatalogError as exc:
        for row in normalized:
            issues.append(
                _row_issue(
                    row,
                    "CATEGORY_GRAPH_INVALID",
                    str(exc),
                    entity_code=str(row["_aggregate_code"]),
                )
            )
        return
    plan["category_relations"].extend(normalized)


def _normalize_modification_categories(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    by_modification: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        modification_code = str(row.get("modification_code") or "").strip()
        category_code = str(row.get("category_code") or "").strip()
        modification_id = _resolve_reference(
            family="modifications",
            code=modification_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODIFICATION_CATEGORY_TARGET_NOT_FOUND",
            not_found_message="Модификация или категория не найдена",
            entity_code=modification_code,
            column_name="Код модификации",
        )
        if modification_id is None:
            continue
        category_id = _resolve_reference(
            family="categories",
            code=category_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODIFICATION_CATEGORY_TARGET_NOT_FOUND",
            not_found_message="Модификация или категория не найдена",
            entity_code=modification_code,
            column_name="Код категории",
        )
        if category_id is None:
            continue
        try:
            raw_primary = row.get("is_primary")
            raw_sort_order = row.get("sort_order")
            values = {
                "modification_id": modification_id,
                "category_id": category_id,
                "sort_order": (
                    None
                    if raw_sort_order is None or str(raw_sort_order).strip() == ""
                    else _nonnegative_int(raw_sort_order)
                ),
                "is_primary": (
                    raw_primary
                    if isinstance(raw_primary, bool)
                    else parse_bool(raw_primary, nullable=True)
                ),
            }
        except (ImportContractError, ValueError, TypeError) as exc:
            issues.append(
                _row_issue(
                    row,
                    "MODIFICATION_CATEGORY_INVALID",
                    str(exc),
                    entity_code=modification_code,
                )
            )
            continue
        by_modification[modification_code].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="modification",
                aggregate_code=modification_code,
            )
        )

    raw_existing_details = context.get("_modification_category_details", {})
    for modification_code, links in by_modification.items():
        modification_id = uuid.UUID(str(links[0]["values"]["modification_id"]))
        existing_details = (
            raw_existing_details.get(modification_id)
            or raw_existing_details.get(str(modification_id))
            or {}
        )
        effective: dict[uuid.UUID, dict[str, Any]] = {}
        if mode is not ImportMode.FULL_SNAPSHOT:
            for raw_category_id, detail in existing_details.items():
                category_id = uuid.UUID(str(raw_category_id))
                effective[category_id] = {
                    "operation": "SET",
                    "values": {
                        "modification_id": modification_id,
                        "category_id": category_id,
                        "sort_order": int(detail["sort_order"]),
                        "is_primary": bool(detail["is_primary"]),
                    },
                    "_sheet_code": links[0]["_sheet_code"],
                    "_row_number": links[0]["_row_number"],
                    "_aggregate_kind": "modification",
                    "_aggregate_code": modification_code,
                }

        seen_categories: set[uuid.UUID] = set()
        has_duplicate = False
        for row in links:
            category_id = uuid.UUID(str(row["values"]["category_id"]))
            if category_id in seen_categories:
                has_duplicate = True
                issues.append(
                    _row_issue(
                        row,
                        "MODIFICATION_CATEGORY_DUPLICATE",
                        "Категория модификации указана в книге несколько раз",
                        entity_code=modification_code,
                    )
                )
                continue
            seen_categories.add(category_id)
            if row["operation"] == "DELETE":
                effective.pop(category_id, None)
                continue
            previous = effective.get(category_id)
            sort_order = row["values"]["sort_order"]
            if sort_order is None:
                sort_order = (
                    int(previous["values"]["sort_order"])
                    if previous is not None
                    else max(
                        (
                            int(item["values"]["sort_order"])
                            for item in effective.values()
                        ),
                        default=-1,
                    )
                    + 1
                )
            is_primary = row["values"]["is_primary"]
            if is_primary is None:
                is_primary = (
                    bool(previous["values"]["is_primary"])
                    if previous is not None
                    else False
                )
            effective[category_id] = {
                **row,
                "values": {
                    **row["values"],
                    "sort_order": sort_order,
                    "is_primary": is_primary,
                },
            }
        if has_duplicate:
            continue

        explicit_primary = [
            row
            for row in links
            if row["operation"] != "DELETE" and row["values"]["is_primary"] is True
        ]
        if len(explicit_primary) > 1:
            for row in explicit_primary:
                issues.append(
                    _row_issue(
                        row,
                        "MODIFICATION_PRIMARY_CATEGORY_CONFLICT",
                        "У модификации может быть только одна основная категория",
                        entity_code=modification_code,
                    )
                )
            continue
        active = list(effective.values())
        if explicit_primary:
            explicit_primary_id = uuid.UUID(
                str(explicit_primary[0]["values"]["category_id"])
            )
            for row in active:
                row["values"]["is_primary"] = (
                    uuid.UUID(str(row["values"]["category_id"])) == explicit_primary_id
                )
        current_primary = [row for row in active if row["values"]["is_primary"]]
        if len(current_primary) > 1:
            issues.append(
                _row_issue(
                    links[0],
                    "MODIFICATION_PRIMARY_CATEGORY_CONFLICT",
                    "У модификации может быть только одна основная категория",
                    entity_code=modification_code,
                )
            )
            continue
        active.sort(
            key=lambda row: (
                row["values"]["sort_order"],
                row["_row_number"],
                str(row["values"]["category_id"]),
            )
        )
        if active and not current_primary:
            had_existing_primary = any(
                bool(detail["is_primary"]) for detail in existing_details.values()
            )
            if had_existing_primary:
                issues.append(
                    _row_issue(
                        links[0],
                        "MODIFICATION_PRIMARY_CATEGORY_REQUIRED",
                        (
                            "При удалении или снятии основной категории "
                            "необходимо явно выбрать новую"
                        ),
                        entity_code=modification_code,
                    )
                )
                continue
            active[0]["values"]["is_primary"] = True
        for index, row in enumerate(active):
            row["values"]["sort_order"] = index
            row["operation"] = "SET"
            row["_aggregate_kind"] = "modification"
            row["_aggregate_code"] = modification_code
        if active:
            plan["modification_categories"].extend(active)
        elif links:
            plan["modification_categories"].append(links[0])


def _normalize_category_attributes(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        category_code = str(row.get("category_code") or "").strip()
        attribute_code = str(row.get("attribute_code") or "").strip()
        group_code = str(row.get("group_code") or "").strip()
        category_id = _resolve_reference(
            family="categories",
            code=category_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="CATEGORY_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Категория, характеристика или указанная группа не найдена",
            entity_code=category_code,
            column_name="Код категории",
        )
        if category_id is None:
            continue
        attribute_id = _resolve_reference(
            family="attributes",
            code=attribute_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="CATEGORY_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Категория, характеристика или указанная группа не найдена",
            entity_code=category_code,
            column_name="Код характеристики",
        )
        if attribute_id is None:
            continue
        group_id: uuid.UUID | None = None
        if group_code:
            group_id = _resolve_reference(
                family="attribute_groups",
                code=group_code,
                identity=identity,
                valid_codes=valid_codes,
                context=context,
                mode=mode,
                row=row,
                issues=issues,
                not_found_code="CATEGORY_ATTRIBUTE_TARGET_NOT_FOUND",
                not_found_message="Категория, характеристика или указанная группа не найдена",
                entity_code=category_code,
                column_name="Код группы",
            )
            if group_id is None:
                continue
        values: dict[str, Any] = {
            "category_id": category_id,
            "attribute_id": attribute_id,
        }
        try:
            if row["operation"] != "DELETE":
                normalized_row = {
                    **row,
                    "group_id": group_id,
                    "is_visible": row.get("is_card_visible"),
                }
                clear_fields = set(row.get("_clear_fields") or ())
                if "group_code" in clear_fields:
                    clear_fields.remove("group_code")
                    clear_fields.add("group_id")
                if "is_card_visible" in clear_fields:
                    clear_fields.remove("is_card_visible")
                    clear_fields.add("is_visible")
                normalized_row["_clear_fields"] = sorted(clear_fields)
                current = context.get("category_attributes", {}).get(
                    (category_id, attribute_id), {}
                )
                merged = _merge_values(
                    row=normalized_row,
                    current=current,
                    mode=mode,
                    fields=(
                        "group_id",
                        "is_required",
                        "is_filterable",
                        "is_visible",
                        "sort_order",
                    ),
                    required={
                        "is_required",
                        "is_filterable",
                        "is_visible",
                        "sort_order",
                    },
                )
                values.update(
                    group_id=merged["group_id"],
                    is_required=_required_bool(merged["is_required"]),
                    is_filterable=_required_bool(merged["is_filterable"]),
                    is_visible=_required_bool(merged["is_visible"]),
                    sort_order=_nonnegative_int(merged["sort_order"]),
                )
        except (ImportContractError, ValueError, TypeError) as exc:
            issues.append(
                _row_issue(
                    row,
                    "CATEGORY_ATTRIBUTE_INVALID",
                    str(exc),
                    entity_code=category_code,
                )
            )
            continue
        plan["category_attributes"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="category",
                aggregate_code=category_code,
            )
        )


def _normalize_modification_values(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    mode: ImportMode = ImportMode.PATCH,
) -> None:
    trim_value_keys = _persisted_trim_value_keys_by_modification(
        context=context,
        mode=mode,
    )
    attributes = {
        **context.get("attributes", {}),
        **{
            str(row["code"]): row["values"]
            for row in plan["attributes"]
            if row["operation"] != "DELETE"
        },
    }
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        modification_code = str(row.get("modification_code") or "").strip()
        attribute_code = str(row.get("attribute_code") or "").strip()
        modification_id = _resolve_reference(
            family="modifications",
            code=modification_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODIFICATION_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Модификация или характеристика не найдена",
            entity_code=modification_code,
            column_name="Код модификации",
        )
        if modification_id is None:
            continue
        attribute_id = _resolve_reference(
            family="attributes",
            code=attribute_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODIFICATION_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Модификация или характеристика не найдена",
            entity_code=modification_code,
            column_name="Код характеристики",
        )
        if attribute_id is None:
            continue
        values: dict[str, Any] = {
            "modification_id": modification_id,
            "attribute_id": attribute_id,
        }
        if row["operation"] != "DELETE":
            if (modification_id, attribute_id) in trim_value_keys:
                issues.append(
                    _row_issue(
                        row,
                        "ATTRIBUTE_ALREADY_ASSIGNED_IN_TRIM",
                        "Характеристика уже заполнена в комплектации модификации",
                        entity_code=modification_code,
                        column_name="Код характеристики",
                    )
                )
                continue
            if public_special_equipment_attribute_code(attribute_code) is None:
                issues.append(
                    _row_issue(
                        row,
                        "MODIFICATION_ATTRIBUTE_VALUE_INVALID",
                        "Attribute code is reserved for private or internal data",
                        entity_code=modification_code,
                    )
                )
                continue
            definition = attributes.get(attribute_code)
            if definition is None:
                issues.append(
                    _row_issue(
                        row,
                        "ATTRIBUTE_NOT_FOUND",
                        "Характеристика не найдена",
                        entity_code=modification_code,
                    )
                )
                continue
            try:
                values.update(
                    _typed_attribute_value(
                        row=row,
                        definition=definition,
                        identity=identity,
                        context=context,
                        mode=mode,
                    )
                )
            except ReferenceNotInSnapshotError:
                issues.append(
                    _row_issue(
                        row,
                        REFERENCE_NOT_IN_SNAPSHOT,
                        REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                        entity_code=modification_code,
                        column_name="Код варианта",
                    )
                )
                continue
            except (ImportContractError, ValueError, TypeError) as exc:
                issues.append(
                    _row_issue(
                        row,
                        "MODIFICATION_ATTRIBUTE_VALUE_INVALID",
                        str(exc),
                        entity_code=modification_code,
                    )
                )
                continue
        plan["modification_attribute_values"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="modification",
                aggregate_code=modification_code,
            )
        )


def _baseline_link_keys(
    family: str,
    context: Mapping[str, Any],
    mode: ImportMode,
) -> set[Any]:
    if mode is ImportMode.FULL_SNAPSHOT:
        return set()
    raw = context.get(family, set())
    if isinstance(raw, dict):
        return set(raw.keys())
    return set(raw)


def _effective_link_keys(
    family: str,
    *,
    plan: Mapping[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    left_field: str,
    right_field: str,
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    baseline = _baseline_link_keys(family, context, mode)
    result = {
        (uuid.UUID(str(left)), uuid.UUID(str(right)))
        for left, right in baseline
    }
    for row in plan.get(family, ()):
        values = row.get("values") or {}
        if left_field in values and right_field in values:
            marker = (
                uuid.UUID(str(values[left_field])),
                uuid.UUID(str(values[right_field])),
            )
            if row.get("operation") == "DELETE":
                result.discard(marker)
            else:
                result.add(marker)
    return result


def _effective_modification_value_keys(
    *,
    plan: Mapping[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    return _effective_link_keys(
        "modification_attribute_values",
        plan=plan,
        context=context,
        mode=mode,
        left_field="modification_id",
        right_field="attribute_id",
    )


def _persisted_trim_value_keys_by_modification(
    *,
    context: Mapping[str, Any],
    mode: ImportMode,
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    if mode is ImportMode.FULL_SNAPSHOT:
        return set()
    modification_by_trim = {
        uuid.UUID(str(record["id"])): uuid.UUID(str(record["modification_id"]))
        for record in context.get("trims", {}).values()
    }
    return {
        (modification_by_trim[uuid.UUID(str(trim_id))], uuid.UUID(str(attribute_id)))
        for trim_id, attribute_id in _baseline_link_keys(
            "trim_attribute_values", context, mode
        )
        if uuid.UUID(str(trim_id)) in modification_by_trim
    }


def _normalize_trim_attributes(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    modification_values = _effective_modification_value_keys(
        plan=plan,
        context=context,
        mode=mode,
    )
    graph, rules_by_category, categories_by_modification = (
        _effective_category_contract(plan=plan, context=context, mode=mode)
    )
    allowed_pairs: dict[
        uuid.UUID, frozenset[tuple[uuid.UUID, uuid.UUID | None]]
    ] = {}
    conflicting_attributes: dict[uuid.UUID, frozenset[uuid.UUID]] = {}
    for contract_modification_id, category_ids in categories_by_modification.items():
        contract = resolve_trim_attribute_contract(
            graph=graph,
            category_ids=category_ids,
            rules_by_category=rules_by_category,
        )
        allowed_pairs[contract_modification_id] = contract.allowed_pairs
        conflicting_attributes[contract_modification_id] = (
            contract.conflicting_attribute_ids
        )
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        modification_code = str(row.get("modification_code") or "").strip()
        trim_code = str(row.get("trim_code") or "").strip()
        trim_key = f"{modification_code}:{trim_code}"
        attribute_code = str(row.get("attribute_code") or "").strip()
        group_code = str(row.get("group_code") or "").strip()
        modification_id = _resolve_reference(
            family="modifications",
            code=modification_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Комплектация, характеристика или группа не найдена",
            entity_code=trim_key,
            column_name="Код модификации",
        )
        if modification_id is None:
            continue
        trim_id = _resolve_reference(
            family="trims",
            code=trim_key,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Комплектация, характеристика или группа не найдена",
            entity_code=trim_key,
            column_name="Код комплектации",
        )
        if trim_id is None:
            continue
        attribute_id = _resolve_reference(
            family="attributes",
            code=attribute_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_TARGET_NOT_FOUND",
            not_found_message="Комплектация, характеристика или группа не найдена",
            entity_code=trim_key,
            column_name="Код характеристики",
        )
        if attribute_id is None:
            continue
        group_id: uuid.UUID | None = None
        if group_code:
            group_id = _resolve_reference(
                family="attribute_groups",
                code=group_code,
                identity=identity,
                valid_codes=valid_codes,
                context=context,
                mode=mode,
                row=row,
                issues=issues,
                not_found_code="TRIM_ATTRIBUTE_TARGET_NOT_FOUND",
                not_found_message="Комплектация, характеристика или группа не найдена",
                entity_code=trim_key,
                column_name="Код группы",
            )
            if group_id is None:
                continue
        modification_id = cast("uuid.UUID", modification_id)
        trim_id = cast("uuid.UUID", trim_id)
        attribute_id = cast("uuid.UUID", attribute_id)
        if attribute_id in conflicting_attributes.get(modification_id, set()):
            issues.append(
                _row_issue(
                    row,
                    "CATEGORY_ATTRIBUTE_GROUP_CONFLICT",
                    "Характеристика назначена разным группам в категориях модификации",
                    entity_code=trim_key,
                    column_name="Код характеристики",
                )
            )
            continue
        if (attribute_id, group_id) not in allowed_pairs.get(modification_id, set()):
            issues.append(
                _row_issue(
                    row,
                    "ATTRIBUTE_NOT_AVAILABLE_FOR_TRIM",
                    "Характеристика недоступна в категориях модификации",
                    entity_code=trim_key,
                    column_name="Код характеристики",
                )
            )
            continue
        if (modification_id, attribute_id) in modification_values:
            issues.append(
                _row_issue(
                    row,
                    "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION",
                    "Характеристика уже заполнена на уровне модификации",
                    entity_code=trim_key,
                    column_name="Код характеристики",
                )
            )
            continue
        values: dict[str, Any] = {
            "trim_id": trim_id,
            "attribute_id": attribute_id,
        }
        try:
            if row["operation"] != "DELETE":
                normalized_row = {**row, "group_id": group_id}
                clear_fields = set(row.get("_clear_fields") or ())
                if "group_code" in clear_fields:
                    clear_fields.remove("group_code")
                    clear_fields.add("group_id")
                normalized_row["_clear_fields"] = sorted(clear_fields)
                current = context.get("trim_attributes", {}).get(
                    (trim_id, attribute_id),
                    {},
                )
                merged = _merge_values(
                    row=normalized_row,
                    current=current,
                    mode=mode,
                    fields=(
                        "group_id",
                        "is_required",
                        "is_filterable",
                        "sort_order",
                    ),
                    required={"is_required", "is_filterable", "sort_order"},
                )
                values.update(
                    group_id=merged["group_id"],
                    is_required=_required_bool(merged["is_required"]),
                    is_filterable=_required_bool(merged["is_filterable"]),
                    sort_order=_nonnegative_int(merged["sort_order"]),
                )
        except (ImportContractError, ValueError, TypeError) as exc:
            issues.append(
                _row_issue(
                    row,
                    "TRIM_ATTRIBUTE_INVALID",
                    str(exc),
                    entity_code=trim_key,
                    column_name="Порядок",
                )
            )
            continue
        plan["trim_attributes"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="trim",
                aggregate_code=trim_key,
            )
        )


def _normalize_superstructure_attributes(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    attributes = {
        **context.get("attributes", {}),
        **{
            str(row["code"]): {**row["values"], "id": row["id"]}
            for row in plan["attributes"]
            if row["operation"] != "DELETE"
        },
    }
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    card_counts: dict[uuid.UUID, int] = defaultdict(int)

    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        s_code = str(row.get("superstructure_code") or "").strip()
        group_code = str(row.get("group_code") or "").strip()
        attr_code = str(row.get("attribute_code") or "").strip()

        s_id = _resolve_reference(
            family="superstructures",
            code=s_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="SUPERSTRUCTURE_NOT_FOUND",
            not_found_message="Тип надстройки не найден",
            entity_code=s_code,
            column_name="Код надстройки",
        )
        if s_id is None:
            continue

        if not group_code:
            issues.append(
                _row_issue(
                    row,
                    "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
                    "Код группы обязателен для характеристики надстройки",
                    entity_code=s_code,
                    column_name="Код группы",
                )
            )
            continue

        group_id = _resolve_reference(
            family="attribute_groups",
            code=group_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
            not_found_message="Группа характеристики не найдена",
            entity_code=s_code,
            column_name="Код группы",
        )
        if group_id is None:
            continue

        attr_id = _resolve_reference(
            family="attributes",
            code=attr_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="SUPERSTRUCTURE_NOT_FOUND",
            not_found_message="Характеристика не найдена",
            entity_code=s_code,
            column_name="Код характеристики",
        )
        if attr_id is None:
            continue

        pair = (s_id, attr_id)
        if pair in seen:
            issues.append(
                _row_issue(
                    row,
                    "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
                    "Характеристика не может быть назначена типу надстройки повторно",
                    entity_code=s_code,
                    column_name="Код характеристики",
                )
            )
            continue
        seen.add(pair)

        # Rule C3: attribute must belong to group_id
        attr_def = attributes.get(attr_code)
        if attr_def is not None:
            attr_group_id = attr_def.get("attribute_group_id")
            if attr_group_id is not None and uuid.UUID(str(attr_group_id)) != group_id:
                issues.append(
                    _row_issue(
                        row,
                        "SUPERSTRUCTURE_ATTRIBUTE_GROUP_MISMATCH",
                        "Характеристика не принадлежит указанной группе",
                        entity_code=s_code,
                        column_name="Код группы",
                    )
                )
                continue

        values: dict[str, Any] = {
            "superstructure_id": s_id,
            "attribute_id": attr_id,
        }
        if row["operation"] != "DELETE":
            raw_card_vis = row.get("is_card_visible")
            if raw_card_vis is None:
                raw_card_vis = row.get("is_visible")
            is_visible = parse_bool(raw_card_vis) if raw_card_vis is not None else False
            if is_visible:
                card_counts[s_id] += 1
                if card_counts[s_id] > 6:
                    issues.append(
                        _row_issue(
                            row,
                            "SUPERSTRUCTURE_CARD_LIMIT_EXCEEDED",
                            "Количество характеристик с признаком «В карточке» не может превышать 6",
                            entity_code=s_code,
                            column_name="В карточке",
                        )
                    )
                    continue

            is_required = parse_bool(row.get("is_required", False))
            is_filterable = parse_bool(row.get("is_filterable", False))
            sort_order = _nonnegative_int(row.get("sort_order", 0))

            values.update(
                group_id=group_id,
                is_required=is_required,
                is_visible=is_visible,
                is_filterable=is_filterable,
                sort_order=sort_order,
            )

        plan["superstructure_attributes"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="superstructure",
                aggregate_code=s_code,
            )
        )


def _normalize_superstructure_categories(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
    _normalize_simple_links(
        plan=plan,
        rows=rows,
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
        family="superstructure_categories",
        left=("superstructures", "superstructure_code", "superstructure_id"),
        right=("categories", "category_code", "category_id"),
        aggregate_kind="superstructure",
    )


def _effective_trim_attribute_keys(
    *,
    plan: Mapping[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    return _effective_link_keys(
        "trim_attributes",
        plan=plan,
        context=context,
        mode=mode,
        left_field="trim_id",
        right_field="attribute_id",
    )


def _normalize_trim_values(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    allowed_links = _effective_trim_attribute_keys(
        plan=plan,
        context=context,
        mode=mode,
    )
    attributes = {
        **context.get("attributes", {}),
        **{
            str(row["code"]): row["values"]
            for row in plan["attributes"]
            if row["operation"] != "DELETE"
        },
    }
    modification_values = _effective_modification_value_keys(
        plan=plan,
        context=context,
        mode=mode,
    )
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        modification_code = str(row.get("modification_code") or "").strip()
        trim_code = str(row.get("trim_code") or "").strip()
        trim_key = f"{modification_code}:{trim_code}"
        attribute_code = str(row.get("attribute_code") or "").strip()
        modification_id = _resolve_reference(
            family="modifications",
            code=modification_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_VALUE_TARGET_NOT_FOUND",
            not_found_message="Комплектация или характеристика не найдена",
            entity_code=trim_key,
            column_name="Код модификации",
        )
        if modification_id is None:
            continue
        trim_id = _resolve_reference(
            family="trims",
            code=trim_key,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_VALUE_TARGET_NOT_FOUND",
            not_found_message="Комплектация или характеристика не найдена",
            entity_code=trim_key,
            column_name="Код комплектации",
        )
        if trim_id is None:
            continue
        attribute_id = _resolve_reference(
            family="attributes",
            code=attribute_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="TRIM_ATTRIBUTE_VALUE_TARGET_NOT_FOUND",
            not_found_message="Комплектация или характеристика не найдена",
            entity_code=trim_key,
            column_name="Код характеристики",
        )
        if attribute_id is None:
            continue
        if (
            row["operation"] != "DELETE"
            and (modification_id, attribute_id) in modification_values
        ):
            issues.append(
                _row_issue(
                    row,
                    "ATTRIBUTE_ALREADY_USED_IN_MODIFICATION",
                    "Характеристика уже заполнена на уровне модификации",
                    entity_code=trim_key,
                    column_name="Код характеристики",
                )
            )
            continue
        marker = (trim_id, attribute_id)
        if marker not in allowed_links:
            issues.append(
                _row_issue(
                    row,
                    "TRIM_ATTRIBUTE_VALUE_NOT_ASSIGNED",
                    "Значение разрешено только для характеристики комплектации",
                    entity_code=trim_key,
                    column_name="Код характеристики",
                )
            )
            continue
        values: dict[str, Any] = {
            "trim_id": trim_id,
            "attribute_id": attribute_id,
        }
        if row["operation"] != "DELETE":
            definition = attributes.get(attribute_code)
            if definition is None:
                issues.append(
                    _row_issue(
                        row,
                        "ATTRIBUTE_NOT_FOUND",
                        "Характеристика не найдена",
                        entity_code=trim_key,
                        column_name="Код характеристики",
                    )
                )
                continue
            try:
                values.update(
                    _typed_attribute_value(
                        row=row,
                        definition=definition,
                        identity=identity,
                        context=context,
                        mode=mode,
                    )
                )
            except ReferenceNotInSnapshotError:
                issues.append(
                    _row_issue(
                        row,
                        REFERENCE_NOT_IN_SNAPSHOT,
                        REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                        entity_code=trim_key,
                        column_name="Код варианта",
                    )
                )
                continue
            except (ImportContractError, ValueError, TypeError) as exc:
                issues.append(
                    _row_issue(
                        row,
                        "TRIM_ATTRIBUTE_VALUE_INVALID",
                        str(exc),
                        entity_code=trim_key,
                        column_name=(
                            "Код варианта"
                            if definition.get("data_type") == "select"
                            else "Значение"
                        ),
                    )
                )
                continue
        plan["trim_attribute_values"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="trim",
                aggregate_code=trim_key,
            )
        )


def _typed_attribute_value(
    *,
    row: Mapping[str, Any],
    definition: Mapping[str, Any],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    context: Mapping[str, Any],
    mode: ImportMode,
) -> dict[str, Any]:
    data_type = str(definition["data_type"])
    raw_value = row.get("value")
    option_code = str(row.get("option_code") or "").strip()
    if data_type == "select":
        if not option_code or raw_value not in {None, ""}:
            raise ImportContractError("Для списка заполняется только код варианта")
        attribute_code = str(row.get("attribute_code") or "").strip()
        key = f"{attribute_code}:{option_code}"
        option_id = identity.get("attribute_options", {}).get(key)
        if option_id is None and mode is not ImportMode.FULL_SNAPSHOT:
            option = context.get("attribute_options", {}).get(key)
            option_id = uuid.UUID(str(option["id"])) if option else None
        if option_id is None:
            if mode is ImportMode.FULL_SNAPSHOT and key in context.get(
                "attribute_options", {}
            ):
                raise ReferenceNotInSnapshotError()
            raise ImportContractError("Вариант характеристики не найден")
        return {"option_id": option_id}
    if option_code:
        raise ImportContractError(
            "Код варианта разрешён только для характеристики-списка"
        )
    if raw_value is None or str(raw_value).strip() == "":
        raise ImportContractError("Значение характеристики обязательно")
    if data_type == "number":
        return {"value_number": _decimal(raw_value, scale=4)}
    if data_type == "boolean":
        return {"value_boolean": parse_bool(raw_value)}
    value = str(raw_value).strip()
    if len(value.encode("utf-8")) > 2000:
        raise ImportContractError("Текст характеристики слишком длинный")
    return {"value_text": value}


def _normalize_product_categories(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> dict[str, list[uuid.UUID]]:
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
    _normalize_simple_links(
        plan=plan,
        rows=rows,
        identity=identity,
        valid_codes=valid_codes,
        mode=mode,
        context=context,
        issues=issues,
        family="product_categories",
        left=("products", "product_code", "product_id"),
        right=("categories", "category_code", "category_id"),
        aggregate_kind="product",
    )
    result: dict[str, list[uuid.UUID]] = defaultdict(list)
    if mode is not ImportMode.FULL_SNAPSHOT:
        reverse_products = {
            uuid.UUID(str(record["id"])): code
            for code, record in context.get("products", {}).items()
        }
        for product_id, category_id in context.get("product_categories", set()):
            if product_code := reverse_products.get(product_id):
                result[product_code].append(category_id)
    for row in plan["product_categories"]:
        product_code = str(row["_aggregate_code"])
        category_id = uuid.UUID(str(row["values"]["category_id"]))
        if row["operation"] == "DELETE":
            result[product_code] = [
                value for value in result[product_code] if value != category_id
            ]
        elif category_id not in result[product_code]:
            result[product_code].append(category_id)
    return result


def _normalize_product_chassis_values(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    product_categories: Mapping[str, list[uuid.UUID]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    graph, rules_by_category, _ = _effective_category_contract(
        plan=plan, context=context, mode=mode
    )
    attributes = {
        **context.get("attributes", {}),
        **{
            str(row["code"]): {**row["values"], "id": row["id"]}
            for row in plan["attributes"]
            if row["operation"] != "DELETE"
        },
    }
    products = {
        **context.get("products", {}),
        **{
            str(row["code"]): {**row["values"], "id": row["id"]}
            for row in plan["products"]
            if row["operation"] != "DELETE"
        },
    }
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        p_code = str(row.get("product_code") or "").strip()
        attr_code = str(row.get("attribute_code") or "").strip()

        p_id = _resolve_reference(
            family="products",
            code=p_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="PRODUCT_NOT_FOUND",
            not_found_message="Объявление не найдено",
            entity_code=p_code,
            column_name="Код объявления",
        )
        if p_id is None:
            continue

        p_data = products.get(p_code)
        if p_data is None or p_data.get("superstructure_id") is None:
            issues.append(
                _row_issue(
                    row,
                    "KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY",
                    "Характеристики шасси разрешены только для комплекта техники",
                    entity_code=p_code,
                    column_name="Код объявления",
                )
            )
            continue

        # Rule Sh4: kit with chassis modification cannot have chassis values
        if p_data.get("modification_id") is not None:
            issues.append(
                _row_issue(
                    row,
                    "KIT_CHASSIS_VALUES_WITH_MODIFICATION",
                    "При выбранной модификации шасси собственные характеристики шасси не сохраняются",
                    entity_code=p_code,
                    column_name="Код объявления",
                )
            )
            continue

        attr_id = _resolve_reference(
            family="attributes",
            code=attr_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="ATTRIBUTE_NOT_FOUND",
            not_found_message="Характеристика не найдена",
            entity_code=p_code,
            column_name="Код характеристики",
        )
        if attr_id is None:
            continue

        pair = (p_id, attr_id)
        if pair in seen:
            issues.append(
                _row_issue(
                    row,
                    "IDENTICAL_DUPLICATE",
                    "Характеристика шасси повторена в файле",
                    entity_code=p_code,
                    column_name="Код характеристики",
                )
            )
            continue
        seen.add(pair)

        # Rule Sh3: attribute must be in effective category rules
        cats = product_categories.get(p_code, [])
        if not cats and p_code in context.get("products", {}):
            cats = [
                uuid.UUID(str(c))
                for c in context.get("_product_categories", {}).get(p_id, ())
            ]
        allowed_attrs = {
            rule.attribute_id
            for cat_id in cats
            for rule in effective_attribute_rules(
                graph=graph,
                category_id=cat_id,
                rules_by_category=rules_by_category,
            )
        }
        if attr_id not in allowed_attrs:
            issues.append(
                _row_issue(
                    row,
                    "KIT_CHASSIS_ATTRIBUTE_NOT_IN_CATEGORY",
                    "Указаны характеристики шасси, не входящие в правила категорий",
                    entity_code=p_code,
                    column_name="Код характеристики",
                )
            )
            continue

        values: dict[str, Any] = {
            "product_id": p_id,
            "attribute_id": attr_id,
        }
        if row["operation"] != "DELETE":
            definition = attributes.get(attr_code)
            if definition is None:
                issues.append(
                    _row_issue(
                        row,
                        "ATTRIBUTE_NOT_FOUND",
                        "Характеристика не найдена",
                        entity_code=p_code,
                        column_name="Код характеристики",
                    )
                )
                continue
            try:
                values.update(
                    _typed_attribute_value(
                        row=row,
                        definition=definition,
                        identity=identity,
                        context=context,
                        mode=mode,
                    )
                )
            except (ImportContractError, ValueError, TypeError) as exc:
                issues.append(
                    _row_issue(
                        row,
                        "PRODUCT_CHASSIS_VALUE_INVALID",
                        str(exc),
                        entity_code=p_code,
                        column_name=(
                            "Код варианта"
                            if definition.get("data_type") == "select"
                            else "Значение"
                        ),
                    )
                )
                continue

        plan["product_chassis_values"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="product",
                aggregate_code=p_code,
            )
        )


def _normalize_product_superstructure_values(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> None:
    attributes = {
        **context.get("attributes", {}),
        **{
            str(row["code"]): {**row["values"], "id": row["id"]}
            for row in plan["attributes"]
            if row["operation"] != "DELETE"
        },
    }
    products = {
        **context.get("products", {}),
        **{
            str(row["code"]): {**row["values"], "id": row["id"]}
            for row in plan["products"]
            if row["operation"] != "DELETE"
        },
    }
    superstructure_attributes = {
        **context.get("superstructure_attributes", {}),
        **{
            (
                uuid.UUID(str(row["values"]["superstructure_id"])),
                uuid.UUID(str(row["values"]["attribute_id"])),
            ): row["values"]
            for row in plan["superstructure_attributes"]
            if row["operation"] != "DELETE"
        },
    }
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        p_code = str(row.get("product_code") or "").strip()
        attr_code = str(row.get("attribute_code") or "").strip()

        p_id = _resolve_reference(
            family="products",
            code=p_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="PRODUCT_NOT_FOUND",
            not_found_message="Объявление не найдено",
            entity_code=p_code,
            column_name="Код объявления",
        )
        if p_id is None:
            continue

        p_data = products.get(p_code)
        if p_data is None or p_data.get("superstructure_id") is None:
            issues.append(
                _row_issue(
                    row,
                    "SUPERSTRUCTURE_NOT_FOUND",
                    "Значения надстроек разрешены только для комплекта техники",
                    entity_code=p_code,
                    column_name="Код объявления",
                )
            )
            continue

        s_id = uuid.UUID(str(p_data["superstructure_id"]))
        attr_id = _resolve_reference(
            family="attributes",
            code=attr_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="ATTRIBUTE_NOT_FOUND",
            not_found_message="Характеристика не найдена",
            entity_code=p_code,
            column_name="Код характеристики",
        )
        if attr_id is None:
            continue

        pair = (p_id, attr_id)
        if pair in seen:
            issues.append(
                _row_issue(
                    row,
                    "IDENTICAL_DUPLICATE",
                    "Значение надстройки повторено в файле",
                    entity_code=p_code,
                    column_name="Код характеристики",
                )
            )
            continue
        seen.add(pair)

        # Rule N3: attribute must be assigned to superstructure type
        if (s_id, attr_id) not in superstructure_attributes:
            issues.append(
                _row_issue(
                    row,
                    "SUPERSTRUCTURE_NOT_FOUND",
                    "Указаны характеристики надстройки, не назначенные выбранному типу",
                    entity_code=p_code,
                    column_name="Код характеристики",
                )
            )
            continue

        values: dict[str, Any] = {
            "product_id": p_id,
            "attribute_id": attr_id,
            "superstructure_id": s_id,
        }
        if row["operation"] != "DELETE":
            definition = attributes.get(attr_code)
            if definition is None:
                issues.append(
                    _row_issue(
                        row,
                        "ATTRIBUTE_NOT_FOUND",
                        "Характеристика не найдена",
                        entity_code=p_code,
                        column_name="Код характеристики",
                    )
                )
                continue
            try:
                values.update(
                    _typed_attribute_value(
                        row=row,
                        definition=definition,
                        identity=identity,
                        context=context,
                        mode=mode,
                    )
                )
            except (ImportContractError, ValueError, TypeError) as exc:
                issues.append(
                    _row_issue(
                        row,
                        "PRODUCT_SUPERSTRUCTURE_VALUE_INVALID",
                        str(exc),
                        entity_code=p_code,
                        column_name=(
                            "Код варианта"
                            if definition.get("data_type") == "select"
                            else "Значение"
                        ),
                    )
                )
                continue

        plan["product_superstructure_values"].append(
            _link_plan_row(
                row,
                values=values,
                aggregate_kind="product",
                aggregate_code=p_code,
            )
        )


def _normalize_simple_links(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    family: str,
    left: tuple[str, str, str],
    right: tuple[str, str, str],
    aggregate_kind: str,
) -> None:
    left_family, left_code_field, left_id_field = left
    right_family, right_code_field, right_id_field = right
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        left_code = str(row.get(left_code_field) or "").strip()
        right_code = str(row.get(right_code_field) or "").strip()
        left_id = _resolve_reference(
            family=left_family,
            code=left_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code=f"{family.upper()}_TARGET_NOT_FOUND",
            not_found_message="Связанная запись не найдена",
            entity_code=left_code or right_code,
        )
        if left_id is None:
            continue
        right_id = _resolve_reference(
            family=right_family,
            code=right_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code=f"{family.upper()}_TARGET_NOT_FOUND",
            not_found_message="Связанная запись не найдена",
            entity_code=left_code or right_code,
        )
        if right_id is None:
            continue
        marker = (left_id, right_id)
        if marker in seen:
            issues.append(
                _row_issue(
                    row,
                    "DUPLICATE_LINK",
                    "Связь повторяется в книге",
                    entity_code=left_code,
                )
            )
            continue
        seen.add(marker)
        plan[family].append(
            _link_plan_row(
                row,
                values={left_id_field: left_id, right_id_field: right_id},
                aggregate_kind=aggregate_kind,
                aggregate_code=left_code,
            )
        )


def _normalize_offering_links(
    *,
    plan: dict[str, JsonlRows],
    rows: list[dict[str, Any]],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    family: str = "product_attachments",
    mode: ImportMode = ImportMode.PATCH,
) -> None:
    left_code_field = "product_code"
    right_code_field = "attachment_product_code"
    left_id_field = "product_id"
    right_id_field = "attachment_product_id"
    seen: set[tuple[uuid.UUID, uuid.UUID]] = set()
    seen_positions: set[tuple[uuid.UUID, int]] = set()
    for row in rows:
        if row.get("operation") == "UPSERT":
            row["operation"] = "ADD" if mode is ImportMode.APPEND else "SET"
        left_code = str(row.get(left_code_field) or "").strip()
        right_code = str(row.get(right_code_field) or "").strip()

        # Rule K2: kits cannot participate in compatibility
        left_product = context.get("products", {}).get(left_code)
        right_product = context.get("products", {}).get(right_code)
        left_is_kit = (left_product.get("superstructure_id") is not None) if left_product else False
        right_is_kit = (right_product.get("superstructure_id") is not None) if right_product else False
        for p_row in plan["products"]:
            if str(p_row.get("code")) == left_code:
                left_is_kit = p_row.get("values", {}).get("superstructure_id") is not None
            elif str(p_row.get("code")) == right_code:
                right_is_kit = p_row.get("values", {}).get("superstructure_id") is not None
        if left_is_kit or right_is_kit:
            issues.append(
                _row_issue(
                    row,
                    "KIT_COMPATIBILITY_FORBIDDEN",
                    "Комплекты не могут участвовать в совместимых надстройках",
                    entity_code=left_code or right_code,
                    column_name="Код объявления",
                )
            )
            continue

        left_id = _resolved_id(
            family="products",
            code=left_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
        )
        right_id = _resolved_id(
            family="products",
            code=right_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
        )
        try:
            if left_id is None or right_id is None:
                if mode is ImportMode.FULL_SNAPSHOT and (
                    left_code in context.get("products", {})
                    or right_code in context.get("products", {})
                ):
                    raise ReferenceNotInSnapshotError()
                raise ImportContractError("Связанное объявление не найдено")
            if left_id == right_id:
                raise ImportContractError("Объявление нельзя связать с самим собой")
            marker = (left_id, right_id)
            if marker in seen:
                raise ImportContractError("Связь повторяется в книге")
            values: dict[str, Any] = {
                left_id_field: left_id,
                right_id_field: right_id,
            }
            if row["operation"] != "DELETE":
                position = _nonnegative_int(row.get("position"))
                position_marker = (left_id, position)
                if position_marker in seen_positions:
                    raise ImportContractError("Позиция повторяется внутри объявления")
                seen_positions.add(position_marker)
                values["position"] = position
            seen.add(marker)
            plan[family].append(
                _link_plan_row(
                    row,
                    values=values,
                    aggregate_kind="product",
                    aggregate_code=left_code,
                )
            )
        except ReferenceNotInSnapshotError:
            issues.append(
                _row_issue(
                    row,
                    REFERENCE_NOT_IN_SNAPSHOT,
                    REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                    entity_code=left_code,
                )
            )
            continue
        except (ImportContractError, TypeError, ValueError) as exc:
            issues.append(
                _row_issue(
                    row,
                    f"{family.upper()}_INVALID",
                    str(exc),
                    entity_code=left_code or right_code,
                )
            )


def _validate_component_plan(
    **_kwargs: Any,
) -> None:
    """Composites are dropped; no-op."""
    return


def _synchronize_component_inheritance_plan(
    **_kwargs: Any,
) -> None:
    """Composites are dropped; no-op."""
    return


def _validate_offering_classification(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> None:
    """Validate the final category-derived offering graph before persistence."""

    relations = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(parent_id)), uuid.UUID(str(child_id)))
            for parent_id, child_id in context.get("category_relations", set())
        }
    )
    for row in plan["category_relations"]:
        marker = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            relations.discard(marker)
        else:
            relations.add(marker)
    category_ids = {
        uuid.UUID(str(row["id"]))
        for row in context.get("categories", {}).values()
    } if mode is not ImportMode.FULL_SNAPSHOT else set()
    for row in plan["categories"]:
        category_id = uuid.UUID(str(row["id"]))
        if row["operation"] == "DELETE":
            category_ids.discard(category_id)
        else:
            category_ids.add(category_id)
    for parent_id, child_id in relations:
        category_ids.add(parent_id)
        category_ids.add(child_id)
    graph = CategoryGraph.from_edges(category_ids=category_ids, edges=relations)
    attachment_ids: set[uuid.UUID] = set(
        _planned_attachment_ids(
            context=context,
            plan=plan,
            mode=mode,
            graph=graph,
        )
    )

    modification_categories: dict[uuid.UUID, set[uuid.UUID]] = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            uuid.UUID(str(modification_id)): {
                uuid.UUID(str(category_id)) for category_id in values
            }
            for modification_id, values in context.get(
                "_modification_category_details", {}
            ).items()
        }
    )
    for row in plan["modification_categories"]:
        modification_id = uuid.UUID(str(row["values"]["modification_id"]))
        category_id = uuid.UUID(str(row["values"]["category_id"]))
        target = modification_categories.setdefault(modification_id, set())
        if row["operation"] == "DELETE":
            target.discard(category_id)
        else:
            target.add(category_id)
    product_categories = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(product_id)), uuid.UUID(str(category_id)))
            for product_id, category_id in context.get("product_categories", set())
        }
    )
    for row in plan["product_categories"]:
        marker = (
            uuid.UUID(str(row["values"]["product_id"])),
            uuid.UUID(str(row["values"]["category_id"])),
        )
        if row["operation"] == "DELETE":
            product_categories.discard(marker)
        else:
            product_categories.add(marker)
    product_modifications: dict[uuid.UUID, uuid.UUID] = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            uuid.UUID(str(row["id"])): uuid.UUID(str(row["modification_id"]))
            for row in context.get("products", {}).values()
            if row.get("modification_id") is not None
        }
    )
    for row in plan["products"]:
        product_id = uuid.UUID(str(row["id"]))
        if row["operation"] == "DELETE":
            product_modifications.pop(product_id, None)
        elif row["values"].get("modification_id") is not None:
            product_modifications[product_id] = uuid.UUID(
                str(row["values"]["modification_id"])
            )
    direct_by_product: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for product_id, category_id in product_categories:
        direct_by_product[product_id].add(category_id)

    def classification(product_id: uuid.UUID) -> str:
        category_ids = set(direct_by_product.get(product_id, ()))
        modification_id = product_modifications.get(product_id)
        if modification_id is not None:
            category_ids.update(modification_categories.get(modification_id, ()))
        has_attachment = bool(category_ids & attachment_ids)
        has_ordinary = bool(category_ids - attachment_ids)
        if has_attachment and has_ordinary:
            return "mixed"
        if has_attachment:
            return "attachment"
        return "ordinary"

    mixed_ids = {
        product_id
        for product_id in product_modifications
        if classification(product_id) == "mixed"
    }
    if mixed_ids:
        structural_rows = [
            *plan["categories"],
            *plan["category_relations"],
            *plan["modification_categories"],
        ]
        if structural_rows:
            issues.append(
                _row_issue(
                    structural_rows[0],
                    "MIXED_ATTACHMENT_CLASSIFICATION",
                    "Изменение создаёт смешанную принадлежность товара к обычной ветви и ветви надстроек",
                    entity_code=str(structural_rows[0]["_aggregate_code"]),
                )
            )
            plan["categories"].replace(())
            plan["category_relations"].replace(())
            plan["modification_categories"].replace(())
        plan["product_categories"].replace(
            row
            for row in plan["product_categories"]
            if uuid.UUID(str(row["values"]["product_id"])) not in mixed_ids
        )

    attachment_links = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            (uuid.UUID(str(product_id)), uuid.UUID(str(attachment_id)))
            for product_id, attachment_id in context.get("product_attachments", set())
        }
    )
    attachment_plan_by_marker: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {}
    invalid_attachment_roots: set[uuid.UUID] = set()
    for row in plan["product_attachments"]:
        product_id = uuid.UUID(str(row["values"]["product_id"]))
        attachment_id = uuid.UUID(str(row["values"]["attachment_product_id"]))
        marker = (product_id, attachment_id)
        attachment_plan_by_marker[marker] = row
        if row["operation"] == "DELETE":
            attachment_links.discard(marker)
        else:
            attachment_links.add(marker)
    product_rows_by_id = {uuid.UUID(str(row["id"])): row for row in plan["products"]}
    product_category_rows_by_id: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["product_categories"]:
        product_category_rows_by_id.setdefault(
            uuid.UUID(str(row["values"]["product_id"])), row
        )
    modification_rows_by_id: dict[uuid.UUID, dict[str, Any]] = {}
    for row in plan["modification_categories"]:
        modification_rows_by_id.setdefault(
            uuid.UUID(str(row["values"]["modification_id"])), row
        )
    structural_rows = [*plan["categories"], *plan["category_relations"]]
    invalid_product_changes: set[uuid.UUID] = set()
    invalid_modification_changes: set[uuid.UUID] = set()
    for product_id, attachment_id in sorted(
        attachment_links, key=lambda marker: (str(marker[0]), str(marker[1]))
    ):
        if (
            product_id not in product_modifications
            or attachment_id not in product_modifications
            or classification(product_id) != "ordinary"
            or classification(attachment_id) != "attachment"
        ):
            invalid_attachment_roots.add(product_id)
            involved_ids = {product_id, attachment_id}
            invalid_product_changes.update(
                involved_ids
                & (product_rows_by_id.keys() | product_category_rows_by_id.keys())
            )
            for involved_id in involved_ids:
                involved_modification_id = product_modifications.get(involved_id)
                if involved_modification_id in modification_rows_by_id:
                    invalid_modification_changes.add(involved_modification_id)
            representative = (
                attachment_plan_by_marker.get((product_id, attachment_id))
                or next(
                    (
                        product_rows_by_id.get(involved_id)
                        or product_category_rows_by_id.get(involved_id)
                        for involved_id in involved_ids
                        if product_rows_by_id.get(involved_id)
                        or product_category_rows_by_id.get(involved_id)
                    ),
                    None,
                )
                or next(
                    (
                        modification_rows_by_id.get(
                            product_modifications.get(involved_id, uuid.UUID(int=0))
                        )
                        for involved_id in involved_ids
                        if product_modifications.get(involved_id)
                        in modification_rows_by_id
                    ),
                    None,
                )
                or (structural_rows[0] if structural_rows else None)
            )
            if representative is None:
                continue
            issues.append(
                _row_issue(
                    representative,
                    "INVALID_ATTACHMENT_CLASSIFICATION",
                    "Совместимость разрешена только между обычной техникой и надстройкой",
                    entity_code=str(representative["_aggregate_code"]),
                )
            )
    if invalid_attachment_roots:
        plan["product_attachments"].replace(
            row
            for row in plan["product_attachments"]
            if uuid.UUID(str(row["values"]["product_id"]))
            not in invalid_attachment_roots
        )
    if invalid_product_changes:
        plan["products"].replace(
            row
            for row in plan["products"]
            if uuid.UUID(str(row["id"])) not in invalid_product_changes
        )
        plan["product_categories"].replace(
            row
            for row in plan["product_categories"]
            if uuid.UUID(str(row["values"]["product_id"]))
            not in invalid_product_changes
        )
    if invalid_modification_changes:
        plan["modification_categories"].replace(
            row
            for row in plan["modification_categories"]
            if uuid.UUID(str(row["values"]["modification_id"]))
            not in invalid_modification_changes
        )
    if invalid_attachment_roots and structural_rows:
        plan["categories"].replace(())
        plan["category_relations"].replace(())


def _validate_published_product_final_state(
    *,
    plan: dict[str, JsonlRows],
    context: Mapping[str, Any],
    mode: ImportMode,
    issues: V2IssueCollector,
) -> None:
    """Reject structural aggregates that invalidate an existing publication."""

    structural_families = (
        "marks",
        "models",
        "modifications",
        "categories",
        "category_relations",
        "attribute_groups",
        "attributes",
        "attribute_options",
        "category_attributes",
        "modification_categories",
        "modification_attribute_values",
    )
    structural_rows = [row for family in structural_families for row in plan[family]]
    if not structural_rows:
        return

    entities = _effective_catalog_entities(context=context, plan=plan, mode=mode)
    products: dict[uuid.UUID, dict[str, Any]] = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            uuid.UUID(str(record["id"])): dict(record)
            for record in context.get("products", {}).values()
        }
    )
    for row in plan["products"]:
        product_id = uuid.UUID(str(row["id"]))
        if row["operation"] == "DELETE":
            products.pop(product_id, None)
        else:
            products[product_id] = {
                **products.get(product_id, {}),
                **dict(row["values"]),
                "id": product_id,
                "code": str(row["code"]),
            }

    direct_categories: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    if mode is not ImportMode.FULL_SNAPSHOT:
        for product_id, category_id in context.get("product_categories", set()):
            direct_categories[uuid.UUID(str(product_id))].add(
                uuid.UUID(str(category_id))
            )
    for row in plan["product_categories"]:
        product_id = uuid.UUID(str(row["values"]["product_id"]))
        category_id = uuid.UUID(str(row["values"]["category_id"]))
        if row["operation"] == "DELETE":
            direct_categories[product_id].discard(category_id)
        else:
            direct_categories[product_id].add(category_id)
    _graph, _rules, categories_by_modification = _effective_category_contract(
        plan=plan,
        context=context,
        mode=mode,
    )

    rows_by_entity_id: dict[uuid.UUID, dict[str, Any]] = {}
    for family in ("marks", "models", "modifications", "categories"):
        for row in plan[family]:
            rows_by_entity_id[uuid.UUID(str(row["id"]))] = row
    fallback = structural_rows[0]
    rejected_aggregates: set[tuple[str, str]] = set()
    for product in products.values():
        if product.get("publication_status") != "published":
            continue
        raw_mod_id = product.get("modification_id")
        modification_id = uuid.UUID(str(raw_mod_id)) if raw_mod_id else None
        category_ids = set(direct_categories.get(product["id"], ()))
        reason: str | None = None
        representative = None
        modification = None
        if modification_id is not None:
            modification = entities["modifications"].get(modification_id)
            category_ids.update(categories_by_modification.get(modification_id, ()))
            representative = rows_by_entity_id.get(modification_id)
            if modification is None or not modification.get("is_active"):
                reason = "цепочка марки, модели и модификации неактивна"
            else:
                model_id = uuid.UUID(str(modification["model_id"]))
                model = entities["models"].get(model_id)
                mark = (
                    entities["marks"].get(uuid.UUID(str(model["mark_id"])))
                    if model is not None
                    else None
                )
                if (
                    model is None
                    or mark is None
                    or not model.get("is_active")
                    or not mark.get("is_active")
                ):
                    reason = "цепочка марки, модели и модификации неактивна"
                    representative = (
                        rows_by_entity_id.get(model_id)
                        or (
                            rows_by_entity_id.get(uuid.UUID(str(model["mark_id"])))
                            if model is not None
                            else None
                        )
                        or representative
                    )
        else:
            raw_model_id = product.get("model_id")
            kit_model_id: uuid.UUID | None = (
                uuid.UUID(str(raw_model_id)) if raw_model_id else None
            )
            model = entities["models"].get(kit_model_id) if kit_model_id else None
            mark = (
                entities["marks"].get(uuid.UUID(str(model["mark_id"])))
                if model is not None
                else None
            )
            representative = (
                rows_by_entity_id.get(kit_model_id) if kit_model_id is not None else None
            )
            if (
                model is None
                or mark is None
                or not model.get("is_active")
                or not mark.get("is_active")
            ):
                reason = "цепочка марки и модели неактивна"
                representative = (
                    (rows_by_entity_id.get(kit_model_id) if kit_model_id is not None else None)
                    or (
                        rows_by_entity_id.get(uuid.UUID(str(model["mark_id"])))
                        if model is not None
                        else None
                    )
                    or representative
                )
        if reason is None and (
            not category_ids
            or any(
                category_id not in entities["categories"]
                or not entities["categories"][category_id].get("is_active")
                for category_id in category_ids
            )
        ):
            reason = "не выбрана активная категория"
            representative = next(
                (
                    rows_by_entity_id[category_id]
                    for category_id in category_ids
                    if category_id in rows_by_entity_id
                ),
                representative,
            )
        manufacture_year = product.get("manufacture_year")
        if (
            reason is None
            and modification_id is not None
            and modification is not None
            and manufacture_year is not None
            and (
                (
                    modification.get("year_from") is not None
                    and manufacture_year < modification["year_from"]
                )
                or (
                    modification.get("year_to") is not None
                    and manufacture_year > modification["year_to"]
                )
            )
        ):
            reason = "год выпуска не входит в период выпуска модификации"
            representative = rows_by_entity_id.get(modification_id, representative)
        if reason is None and modification_id is not None:
            required = _required_attributes_for_categories(
                context=context,
                category_ids=category_ids,
            )
            present = _attributes_for_modification(
                context=context,
                modification_id=modification_id,
            )
            if not required.issubset(present):
                reason = "не заполнены обязательные характеристики"
        if reason is None:
            continue
        representative = representative or fallback
        aggregate_key = (
            str(representative.get("_aggregate_kind") or ""),
            str(representative.get("_aggregate_code") or ""),
        )
        if aggregate_key in rejected_aggregates:
            continue
        rejected_aggregates.add(aggregate_key)
        issues.append(
            _row_issue(
                representative,
                "PUBLISHED_PRODUCT_INVALIDATED",
                f"Изменение делает опубликованное объявление недопустимым: {reason}",
                entity_code=aggregate_key[1],
            )
        )
    if not rejected_aggregates:
        return
    for family in structural_families:
        plan[family].replace(
            row
            for row in plan[family]
            if (
                str(row.get("_aggregate_kind") or ""),
                str(row.get("_aggregate_code") or ""),
            )
            not in rejected_aggregates
        )


def _effective_entity_by_id(
    *,
    context: Mapping[str, Any],
    family: str,
    entity_id: uuid.UUID,
) -> Mapping[str, Any] | None:
    effective = context.get("_effective_catalog_entities")
    if isinstance(effective, Mapping):
        records = effective.get(family, {})
        if isinstance(records, Mapping):
            record = records.get(entity_id)
            if isinstance(record, Mapping):
                return record
    if context.get("_import_mode") in {
        ImportMode.FULL_SNAPSHOT,
        ImportMode.FULL_SNAPSHOT.value,
    }:
        return None
    return next(
        (
            record
            for record in context.get(family, {}).values()
            if uuid.UUID(str(record["id"])) == entity_id
        ),
        None,
    )


def _resolve_product_trim_id(
    *,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    modification_code: str,
    modification_id: uuid.UUID,
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
) -> uuid.UUID | None:
    clear_fields = set(row.get("_clear_fields") or ())
    raw_code = row.get("trim_code")
    blank = raw_code is None or not str(raw_code).strip()
    if "trim_code" in clear_fields:
        return None
    if mode is ImportMode.PATCH and row["operation"] == "SET" and blank:
        current_id = current.get("trim_id")
        return uuid.UUID(str(current_id)) if current_id is not None else None
    if blank:
        return None
    try:
        trim_code = validate_entity_code(str(raw_code))
    except ImportContractError as exc:
        raise _ProductFieldImportContractError("Код комплектации", str(exc)) from exc
    trim_key = f"{modification_code}:{trim_code}"
    trim_id = _resolved_id(
        family="trims",
        code=trim_key,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
    )
    if trim_id is None:
        if mode is ImportMode.FULL_SNAPSHOT and trim_key in context.get("trims", {}):
            raise _ProductFieldImportContractError(
                "Код комплектации",
                REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                code=REFERENCE_NOT_IN_SNAPSHOT,
            )
        raise _ProductFieldImportContractError(
            "Код комплектации", "Комплектация не найдена"
        )
    trim = _effective_entity_by_id(
        context=context,
        family="trims",
        entity_id=trim_id,
    )
    if (
        trim is None
        or not bool(trim.get("is_active"))
        or uuid.UUID(str(trim["modification_id"])) != modification_id
    ):
        raise _ProductFieldImportContractError(
            "Код комплектации",
            "Комплектация должна быть активной и принадлежать выбранной модификации",
        )
    return trim_id


def _resolve_product_color_id(
    *,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    code_field: str,
    id_field: str,
    column_name: str,
    required_applicability: Literal["body", "interior"],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
) -> uuid.UUID | None:
    clear_fields = set(row.get("_clear_fields") or ())
    raw_code = row.get(code_field)
    blank = raw_code is None or not str(raw_code).strip()
    current_raw_id = current.get(id_field)
    current_id = uuid.UUID(str(current_raw_id)) if current_raw_id is not None else None
    if code_field in clear_fields:
        return None
    if mode is ImportMode.PATCH and row["operation"] == "SET" and blank:
        return current_id
    if blank:
        return None
    try:
        color_code = normalize_color_code(str(raw_code), name=str(raw_code))
    except SpecialEquipmentColorValidationError as exc:
        raise _ProductFieldImportContractError(column_name, str(exc)) from exc
    color_id = _resolved_id(
        family="colors",
        code=color_code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
    )
    if color_id is None:
        if mode is ImportMode.FULL_SNAPSHOT and color_code in context.get("colors", {}):
            raise _ProductFieldImportContractError(
                column_name,
                REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                code=REFERENCE_NOT_IN_SNAPSHOT,
            )
        raise _ProductFieldImportContractError(column_name, "Цвет не найден")
    color = _effective_entity_by_id(
        context=context,
        family="colors",
        entity_id=color_id,
    )
    if color is None:
        raise _ProductFieldImportContractError(column_name, "Цвет не найден")
    try:
        ensure_product_color_assignment_allowed(
            current_color_id=current_id,
            field_present=True,
            requested_color_id=color_id,
            is_active=bool(color.get("is_active")),
            color_applicability=str(color.get("applicability") or ""),
            required_applicability=required_applicability,
            field=id_field,
        )
    except SpecialEquipmentColorValidationError as exc:
        raise _ProductFieldImportContractError(column_name, str(exc)) from exc
    return color_id


_PRODUCT_COMPARE_FIELDS: tuple[str, ...] = (
    "seller_company_id",
    "trim_id",
    "body_color_id",
    "interior_color_id",
    "warehouse_id",
    "modification_id",
    "manufacture_year",
    "description",
    "price",
    "special_price",
    "price_on_request",
    "price_from",
    "currency_code",
    "owners_count",
    "no_vin",
    "vin",
    "mileage_km",
    "engine_hours",
    "publication_status",
    "sale_status",
    "published_at",
)


def _normalize_cmp_val(val: Any) -> Any:
    if val is None or val == "":
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        s = val.strip()
        return s if s else None
    return val


def _product_attributes_changed(
    *, values: Mapping[str, Any], current: Mapping[str, Any]
) -> bool:
    for field in _PRODUCT_COMPARE_FIELDS:
        v1 = _normalize_cmp_val(values.get(field))
        v2 = _normalize_cmp_val(current.get(field))
        if v1 != v2:
            return True
    return False


def _attach_product_images_action(
    *,
    values: dict[str, Any],
    row: Mapping[str, Any],
    mode: ImportMode,
    code: str,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
) -> bool:
    clear_fields = set(row.get("_clear_fields") or ())
    current_images = list(context.get("product_images", {}).get(code, []))
    values["_current_images"] = [
        {
            "id": str(img["id"]),
            "storage_key": img["storage_key"],
            "source_ref": img.get("source_ref"),
            "sort_order": img["sort_order"],
            "is_primary": img["is_primary"],
        }
        for img in current_images
    ]

    if "image_source_url" in clear_fields:
        values["_images_action"] = "clear"
        values["_image_action"] = "clear"
        values["_image_sources"] = []
        return True

    raw_url = row.get("image_source_url")
    if raw_url is None or not str(raw_url).strip():
        if mode is ImportMode.PATCH and row.get("operation") == "SET":
            values["_images_action"] = "keep"
        else:
            values["_images_action"] = "clear"
            values["_image_action"] = "clear"
        values["_image_sources"] = []
        return True

    parsed = parse_image_source_urls(
        str(raw_url),
        allowed_hosts=settings.special_equipment_image_source_hosts,
        limit=50,
    )
    if any(issue.code == "PRODUCT_IMAGE_CLEAR_MIXED" for issue in parsed.issues):
        issues.append(
            _row_issue(
                row,
                "PRODUCT_IMAGE_CLEAR_MIXED",
                "Значение «Очистить» нельзя совмещать со ссылками на изображение",
                entity_code=code,
                column_name="Ссылка на изображение",
            )
        )
        return False

    if parsed.is_clear:
        values["_images_action"] = "clear"
        values["_image_action"] = "clear"
        values["_image_sources"] = []
        return True

    for issue in parsed.issues:
        issues.append(
            _row_issue(
                row,
                issue.code,
                issue.message,
                severity=IssueSeverity.WARNING,
                entity_code=code,
                column_name="Ссылка на изображение",
            )
        )

    if not parsed.refs:
        values["_images_action"] = "replace"
        values["_image_action"] = "replace"
        values["_image_source_url"] = str(raw_url).strip()
        values["_image_sources"] = []
        return True

    current_refs = [
        img.get("source_ref")
        for img in current_images
        if img.get("source_ref") is not None
    ]
    file_refs = [ref.source_ref for ref in parsed.refs]
    gallery_matches = (
        len(current_images) == len(parsed.refs)
        and all(img.get("source_ref") is not None for img in current_images)
        and current_refs == file_refs
    )
    if gallery_matches:
        values["_images_action"] = "keep"
    else:
        values["_images_action"] = "replace"
        values["_image_action"] = "replace"
        values["_image_source_url"] = parsed.refs[0].raw_url

    values["_image_sources"] = [
        {
            "source_ref": ref.source_ref,
            "raw_url": ref.raw_url,
            "position": ref.position,
        }
        for ref in parsed.refs
    ]
    return True


def _resolve_kit_source_details(
    *,
    source_product: dict[str, Any],
    context: Mapping[str, Any],
    is_from_workbook: bool,
) -> tuple[uuid.UUID | None, uuid.UUID | None, str, str]:
    if is_from_workbook:
        values = source_product.get("values", {})
        source_mod_id = values.get("modification_id")
        source_model_id = values.get("model_id")
    else:
        source_mod_id = (
            uuid.UUID(str(source_product["modification_id"]))
            if source_product.get("modification_id")
            else None
        )
        source_model_id = (
            uuid.UUID(str(source_product["model_id"]))
            if source_product.get("model_id")
            else None
        )

    mod_record: dict[str, Any] | None = None
    if source_mod_id is not None:
        for m in context.get("modifications", {}).values():
            if uuid.UUID(str(m["id"])) == source_mod_id:
                mod_record = m
                break
    if mod_record is not None and source_model_id is None:
        source_model_id = uuid.UUID(str(mod_record["model_id"]))

    model_record: dict[str, Any] | None = None
    if source_model_id is not None:
        for m in context.get("models", {}).values():
            if uuid.UUID(str(m["id"])) == source_model_id:
                model_record = m
                break

    mark_record: dict[str, Any] | None = None
    if model_record is not None and model_record.get("mark_id") is not None:
        mark_id = uuid.UUID(str(model_record["mark_id"]))
        for mk in context.get("marks", {}).values():
            if uuid.UUID(str(mk["id"])) == mark_id:
                mark_record = mk
                break

    name = str(model_record["name"]) if model_record and model_record.get("name") else ""
    mfr = str(mark_record["name"]) if mark_record and mark_record.get("name") else ""
    return source_model_id, source_mod_id, name, mfr


def _normalize_product(  # noqa: PLR0911
    *,
    row: dict[str, Any],
    categories: list[uuid.UUID],
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    mode: ImportMode,
    context: Mapping[str, Any],
    issues: V2IssueCollector,
    attachment_category_ids: frozenset[uuid.UUID] | None = None,
    workbook_ordinary_products: Mapping[str, dict[str, Any]] | None = None,
    workbook_kit_codes: set[str] | None = None,
    product_categories: Mapping[str, list[uuid.UUID]] | None = None,
    planned_superstructure_categories: set[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> dict[str, Any] | None:
    code = str(row["_code"])
    if row["operation"] == "DELETE":
        return _entity_plan_row(family="products", row=row, values={})
    current = context.get("products", {}).get(code, {})
    s_code = str(row.get("superstructure_code") or "").strip()
    has_model = bool(str(row.get("model_code") or "").strip()) or bool(
        current.get("model_id")
    )
    has_kit_fields = any(
        bool(str(row.get(f) or "").strip())
        for f in (
            "superstructure_model_code",
            "superstructure_modification_code",
            "superstructure_source_code",
            "superstructure_name",
            "superstructure_manufacturer",
        )
    )
    is_kit = bool(s_code) and (has_model or has_kit_fields)
    is_standalone_superstructure = bool(s_code) and not is_kit

    if current:
        was_kit = bool(
            current.get("model_id") is not None
            and current.get("superstructure_id") is not None
        )
        if was_kit != is_kit:
            issues.append(
                _row_issue(
                    row,
                    "PRODUCT_KIND_IMMUTABLE",
                    "Тип объявления (обычное или комплект) не может быть изменён",
                    entity_code=code,
                    column_name="Код надстройки",
                )
            )
            return None

    if not is_kit:
        for kit_col, kit_col_name in (
            ("model_code", "Код модели"),
            ("superstructure_model_code", "Код модели надстройки"),
            ("superstructure_modification_code", "Код модификации надстройки"),
            ("superstructure_source_code", "Код объявления надстройки"),
            ("superstructure_name", "Название надстройки"),
            ("superstructure_manufacturer", "Производитель надстройки"),
            ("chassis_vin", "VIN шасси"),
        ):
            if str(row.get(kit_col) or "").strip():
                issues.append(
                    _row_issue(
                        row,
                        "PRODUCT_KIND_CONFLICT",
                        f"Поле «{kit_col_name}» допустимо только для комплекта техники",
                        entity_code=code,
                        column_name=kit_col_name,
                    )
                )
                return None

        modification_code = str(row.get("modification_code") or "").strip()
        modification_id = _resolve_reference(
            family="modifications",
            code=modification_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODIFICATION_NOT_FOUND",
            not_found_message="Модификация объявления не найдена",
            entity_code=code,
            column_name="Код модификации",
        )
        if modification_id is None:
            return None

        if is_standalone_superstructure:
            superstructure_id = _resolve_reference(
                family="superstructures",
                code=s_code,
                identity=identity,
                valid_codes=valid_codes,
                context=context,
                mode=mode,
                row=row,
                issues=issues,
                not_found_code="SUPERSTRUCTURE_NOT_FOUND",
                not_found_message="Тип надстройки не найден",
                entity_code=code,
                column_name="Код надстройки",
            )
            if superstructure_id is None:
                return None
        else:
            superstructure_id = None

        model_id = None
        superstructure_model_id = None
        superstructure_modification_id = None
        superstructure_source_product_id = None
        superstructure_name = None
        superstructure_manufacturer = None
    else:
        superstructure_id = _resolve_reference(
            family="superstructures",
            code=s_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="SUPERSTRUCTURE_NOT_FOUND",
            not_found_message="Тип надстройки не найден",
            entity_code=code,
            column_name="Код надстройки",
        )
        if superstructure_id is None:
            return None

        chassis_model_code = str(row.get("model_code") or "").strip()
        if not chassis_model_code:
            issues.append(
                _row_issue(
                    row,
                    "PRODUCT_KIND_CONFLICT",
                    "Для комплекта техники обязателен код модели шасси",
                    entity_code=code,
                    column_name="Код модели",
                )
            )
            return None
        model_id = _resolve_reference(
            family="models",
            code=chassis_model_code,
            identity=identity,
            valid_codes=valid_codes,
            context=context,
            mode=mode,
            row=row,
            issues=issues,
            not_found_code="MODEL_NOT_FOUND",
            not_found_message="Модель шасси не найдена",
            entity_code=code,
            column_name="Код модели",
        )
        if model_id is None:
            return None

        chassis_mod_code = str(row.get("modification_code") or "").strip()
        modification_code = chassis_mod_code
        modification_id = None
        if chassis_mod_code:
            modification_id = _resolve_reference(
                family="modifications",
                code=chassis_mod_code,
                identity=identity,
                valid_codes=valid_codes,
                context=context,
                mode=mode,
                row=row,
                issues=issues,
                not_found_code="MODIFICATION_NOT_FOUND",
                not_found_message="Модификация шасси не найдена",
                entity_code=code,
                column_name="Код модификации",
            )
            if modification_id is None:
                return None
            mod_rec = context.get("modifications", {}).get(chassis_mod_code)
            if mod_rec is not None and uuid.UUID(str(mod_rec["model_id"])) != model_id:
                issues.append(
                    _row_issue(
                        row,
                        "KIT_CHASSIS_MODIFICATION_MODEL_MISMATCH",
                        "Модификация шасси должна принадлежать выбранной модели шасси",
                        entity_code=code,
                        column_name="Код модификации",
                    )
                )
                return None

        if str(row.get("trim_code") or "").strip():
            issues.append(
                _row_issue(
                    row,
                    "PRODUCT_KIND_CONFLICT",
                    "Комплектация не может быть указана для комплекта техники",
                    entity_code=code,
                    column_name="Код комплектации",
                )
            )
            return None

        clear_fields = set(row.get("_clear_fields") or ())
        source_code_cleared = "superstructure_source_code" in clear_fields
        raw_source_code = str(row.get("superstructure_source_code") or "").strip()

        is_linked_source = bool(raw_source_code) or (
            mode is ImportMode.PATCH
            and row.get("operation") == "SET"
            and not source_code_cleared
            and not raw_source_code
            and current.get("superstructure_source_product_id") is not None
        )

        conflict_cols = [
            ("superstructure_model_code", "Код модели надстройки"),
            ("superstructure_modification_code", "Код модификации надстройки"),
            ("superstructure_name", "Название надстройки"),
            ("superstructure_manufacturer", "Производитель надстройки"),
        ]

        if is_linked_source:
            if raw_source_code:
                for col_key, col_title in conflict_cols:
                    if str(row.get(col_key) or "").strip():
                        issues.append(
                            _row_issue(
                                row,
                                KIT_SUPERSTRUCTURE_SOURCE_CONFLICT,
                                f"Поле «{col_title}» не допускается при указании ссылки на объявление-надстройку",
                                entity_code=code,
                                column_name=col_title,
                            )
                        )
                        return None

                if raw_source_code == code:
                    issues.append(
                        _row_issue(
                            row,
                            KIT_SUPERSTRUCTURE_SOURCE_INVALID,
                            "Комплект техники не может ссылаться на самого себя",
                            entity_code=code,
                            column_name="Код объявления надстройки",
                        )
                    )
                    return None

                source_product: dict[str, Any] | None = None
                source_is_from_workbook = False
                if (
                    workbook_ordinary_products is not None
                    and raw_source_code in workbook_ordinary_products
                ):
                    source_product = workbook_ordinary_products[raw_source_code]
                    source_is_from_workbook = True
                elif raw_source_code in context.get("products", {}):
                    source_product = context["products"][raw_source_code]
                    source_is_from_workbook = False

                if source_product is None:
                    if workbook_kit_codes and raw_source_code in workbook_kit_codes:
                        issues.append(
                            _row_issue(
                                row,
                                KIT_SUPERSTRUCTURE_SOURCE_INVALID,
                                "Объявление-надстройка не может быть комплектом техники",
                                entity_code=code,
                                column_name="Код объявления надстройки",
                            )
                        )
                        return None
                    issues.append(
                        _row_issue(
                            row,
                            "PRODUCT_NOT_FOUND",
                            "Объявление-надстройка не найдено",
                            entity_code=code,
                            column_name="Код объявления надстройки",
                        )
                    )
                    return None

                is_source_kit = (
                    bool(workbook_kit_codes and raw_source_code in workbook_kit_codes)
                    if source_is_from_workbook
                    else source_product.get("superstructure_id") is not None
                )
                if is_source_kit:
                    issues.append(
                        _row_issue(
                            row,
                            KIT_SUPERSTRUCTURE_SOURCE_INVALID,
                            "Объявление-надстройка не может быть комплектом техники",
                            entity_code=code,
                            column_name="Код объявления надстройки",
                        )
                    )
                    return None

                source_status = str(
                    (
                        source_product.get("values", {}).get("publication_status")
                        if source_is_from_workbook
                        else source_product.get("publication_status")
                    )
                    or "draft"
                )
                if source_status not in ("draft", "published"):
                    issues.append(
                        _row_issue(
                            row,
                            KIT_SUPERSTRUCTURE_SOURCE_INVALID,
                            "Объявление-надстройка должно иметь статус «Черновик» или «Опубликовано»",
                            entity_code=code,
                            column_name="Код объявления надстройки",
                        )
                    )
                    return None

                if source_is_from_workbook:
                    source_cats = (product_categories or {}).get(raw_source_code, [])
                else:
                    source_id_uuid = uuid.UUID(str(source_product["id"]))
                    source_cats = [
                        c
                        for (p, c) in context.get("product_categories", set())
                        if p == source_id_uuid
                    ]

                if attachment_category_ids is not None and not any(
                    c in attachment_category_ids for c in source_cats
                ):
                    issues.append(
                        _row_issue(
                            row,
                            KIT_SUPERSTRUCTURE_SOURCE_INVALID,
                            "Объявление-надстройка должно входить в ветку надстроек",
                            entity_code=code,
                            column_name="Код объявления надстройки",
                        )
                    )
                    return None

                source_id = (
                    uuid.UUID(str(source_product["_id"]))
                    if source_is_from_workbook
                    else uuid.UUID(str(source_product["id"]))
                )
                (
                    res_model_id,
                    res_mod_id,
                    res_name,
                    res_mfr,
                ) = _resolve_kit_source_details(
                    source_product=source_product,
                    context=context,
                    is_from_workbook=source_is_from_workbook,
                )
                superstructure_source_product_id = source_id
                superstructure_model_id = res_model_id
                superstructure_modification_id = res_mod_id
                superstructure_name = res_name
                superstructure_manufacturer = res_mfr
            else:
                for col_key, col_title in conflict_cols:
                    if str(row.get(col_key) or "").strip():
                        issues.append(
                            _row_issue(
                                row,
                                KIT_SUPERSTRUCTURE_SOURCE_CONFLICT,
                                f"Поле «{col_title}» не допускается при наличии ссылки на объявление-надстройку",
                                entity_code=code,
                                column_name=col_title,
                            )
                        )
                        return None
                superstructure_source_product_id = uuid.UUID(
                    str(current["superstructure_source_product_id"])
                )
                superstructure_model_id = (
                    uuid.UUID(str(current["superstructure_model_id"]))
                    if current.get("superstructure_model_id")
                    else None
                )
                superstructure_modification_id = (
                    uuid.UUID(str(current["superstructure_modification_id"]))
                    if current.get("superstructure_modification_id")
                    else None
                )
                superstructure_name = current.get("superstructure_name")
                superstructure_manufacturer = current.get("superstructure_manufacturer")
        else:
            superstructure_source_product_id = None
            s_model_code = str(row.get("superstructure_model_code") or "").strip()
            if (
                not s_model_code
                and mode is ImportMode.PATCH
                and row.get("operation") == "SET"
                and current.get("superstructure_model_id")
            ):
                superstructure_model_id = uuid.UUID(str(current["superstructure_model_id"]))
            elif not s_model_code:
                issues.append(
                    _row_issue(
                        row,
                        KIT_SUPERSTRUCTURE_MODEL_REQUIRED,
                        "Для комплекта техники обязателен код модели надстройки",
                        entity_code=code,
                        column_name="Код модели надстройки",
                    )
                )
                return None
            else:
                superstructure_model_id = _resolve_reference(
                    family="models",
                    code=s_model_code,
                    identity=identity,
                    valid_codes=valid_codes,
                    context=context,
                    mode=mode,
                    row=row,
                    issues=issues,
                    not_found_code="MODEL_NOT_FOUND",
                    not_found_message="Модель надстройки не найдена",
                    entity_code=code,
                    column_name="Код модели надстройки",
                )
                if superstructure_model_id is None:
                    return None

            s_mod_code = str(row.get("superstructure_modification_code") or "").strip()
            superstructure_modification_id = None
            if s_mod_code:
                superstructure_modification_id = _resolve_reference(
                    family="modifications",
                    code=s_mod_code,
                    identity=identity,
                    valid_codes=valid_codes,
                    context=context,
                    mode=mode,
                    row=row,
                    issues=issues,
                    not_found_code="MODIFICATION_NOT_FOUND",
                    not_found_message="Модификация надстройки не найдена",
                    entity_code=code,
                    column_name="Код модификации надстройки",
                )
                if superstructure_modification_id is None:
                    return None
                s_mod_rec = context.get("modifications", {}).get(s_mod_code)
                if (
                    s_mod_rec is not None
                    and uuid.UUID(str(s_mod_rec["model_id"])) != superstructure_model_id
                ):
                    issues.append(
                        _row_issue(
                            row,
                            KIT_SUPERSTRUCTURE_MODIFICATION_MODEL_MISMATCH,
                            "Модификация надстройки должна принадлежать выбранной модели надстройки",
                            entity_code=code,
                            column_name="Код модификации надстройки",
                        )
                    )
                    return None
            elif (
                mode is ImportMode.PATCH
                and row.get("operation") == "SET"
                and "superstructure_modification_code" not in clear_fields
                and not s_model_code
                and current.get("superstructure_modification_id")
            ):
                superstructure_modification_id = uuid.UUID(
                    str(current["superstructure_modification_id"])
                )

            s_name = str(row.get("superstructure_name") or "").strip()
            s_mfr = str(row.get("superstructure_manufacturer") or "").strip()
            if (
                not s_name
                and mode is ImportMode.PATCH
                and row.get("operation") == "SET"
                and "superstructure_name" not in clear_fields
            ):
                s_name = str(current.get("superstructure_name") or "").strip()
            if (
                not s_mfr
                and mode is ImportMode.PATCH
                and row.get("operation") == "SET"
                and "superstructure_manufacturer" not in clear_fields
            ):
                s_mfr = str(current.get("superstructure_manufacturer") or "").strip()

            if not s_name:
                issues.append(
                    _row_issue(
                        row,
                        "PRODUCT_KIND_CONFLICT",
                        "Название надстройки обязательно для комплекта",
                        entity_code=code,
                        column_name="Название надстройки",
                    )
                )
                return None
            if not s_mfr:
                issues.append(
                    _row_issue(
                        row,
                        "PRODUCT_KIND_CONFLICT",
                        "Производитель надстройки обязателен для комплекта",
                        entity_code=code,
                        column_name="Производитель надстройки",
                    )
                )
                return None
            superstructure_name = s_name
            superstructure_manufacturer = s_mfr

        if attachment_category_ids is None:
            cat_items = context.get("categories", {})
            edges = {
                (uuid.UUID(str(p)), uuid.UUID(str(c)))
                for p, c in context.get("category_relations", set())
            }
            all_cat_ids = {uuid.UUID(str(rec["id"])) for rec in cat_items.values()}
            for p, c in edges:
                all_cat_ids.add(p)
                all_cat_ids.add(c)
            g = CategoryGraph.from_edges(category_ids=all_cat_ids, edges=edges)
            att_roots = [
                uuid.UUID(str(rec["id"]))
                for rec in cat_items.values()
                if rec.get("is_attachment_category") and uuid.UUID(str(rec["id"])) in g.category_ids
            ]
            attachment_category_ids = attachment_branch_ids(graph=g, attachment_roots=att_roots)

        if any(cat_id in attachment_category_ids for cat_id in categories):
            issues.append(
                _row_issue(
                    row,
                    "KIT_ATTACHMENT_CATEGORY",
                    "Категории комплекта техники не могут входить в ветку надстроек",
                    entity_code=code,
                    column_name="Код",
                )
            )
            return None

    try:
        values = _merge_values(
            row=row,
            current=current,
            mode=mode,
            fields=(
                "seller_inn",
                "warehouse_id",
                "condition",
                "manufacture_year",
                "description",
                "price",
                "special_price",
                "price_on_request",
                "price_from",
                "currency_code",
                "owners_count",
                "no_vin",
                "vin",
                "chassis_vin",
                "superstructure_vin",
                "mileage_km",
                "engine_hours",
                "publication_status",
                "sale_status",
                "published_at",
            ),
            required={"condition"},
            family="products",
        )
        if current:
            for field in ("price_on_request", "price_from"):
                if field not in row:
                    values[field] = current.get(field)
        clear_fields = set(row.get("_clear_fields") or ())
        seller_inn = str(values.pop("seller_inn", "") or "").strip()
        seller = context.get("companies", {}).get(seller_inn) if seller_inn else None
        if seller_inn and (seller is None or not seller.get("is_active")):
            raise ImportContractError("Активный продавец с таким ИНН не найден")
        if seller is not None:
            values["seller_company_id"] = uuid.UUID(str(seller["id"]))
        elif (
            mode is ImportMode.PATCH
            and row["operation"] == "SET"
            and "seller_inn" not in clear_fields
            and current.get("seller_company_id") is not None
        ):
            values["seller_company_id"] = uuid.UUID(str(current["seller_company_id"]))
        else:
            values["seller_company_id"] = None
        if is_kit:
            values["trim_id"] = None
        else:
            assert modification_id is not None
            values["trim_id"] = _resolve_product_trim_id(
                row=row,
                current=current,
                modification_code=modification_code,
                modification_id=modification_id,
                identity=identity,
                valid_codes=valid_codes,
                mode=mode,
                context=context,
            )
        values["body_color_id"] = _resolve_product_color_id(
            row=row,
            current=current,
            code_field="body_color_code",
            id_field="body_color_id",
            column_name="Код цвета кузова",
            required_applicability="body",
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
        )
        values["interior_color_id"] = _resolve_product_color_id(
            row=row,
            current=current,
            code_field="interior_color_code",
            id_field="interior_color_id",
            column_name="Код цвета салона",
            required_applicability="interior",
            identity=identity,
            valid_codes=valid_codes,
            mode=mode,
            context=context,
        )
        values["warehouse_id"] = None
        values["modification_id"] = modification_id
        values["model_id"] = model_id
        values["superstructure_id"] = superstructure_id
        values["superstructure_model_id"] = superstructure_model_id
        values["superstructure_modification_id"] = superstructure_modification_id
        values["superstructure_source_product_id"] = superstructure_source_product_id
        values["superstructure_name"] = superstructure_name
        values["superstructure_manufacturer"] = superstructure_manufacturer
        values["slug"] = generate_catalog_slug(code)
        values["manufacture_year"] = _optional_year(values.get("manufacture_year"))
        if modification_id is not None:
            directory_chain_active, modification = _product_directory_state(
                context=context,
                modification_id=modification_id,
            )
            if modification is None:
                raise ImportContractError("Модификация объявления не найдена")
            manufacture_year = values["manufacture_year"]
            if manufacture_year is not None and (
                (
                    modification.get("year_from") is not None
                    and manufacture_year < modification["year_from"]
                )
                or (
                    modification.get("year_to") is not None
                    and manufacture_year > modification["year_to"]
                )
            ):
                raise ImportContractError(
                    "Год выпуска не входит в период выпуска модификации"
                )
        else:
            directory_chain_active = True
            modification = None
        values["price"] = _optional_decimal(values.get("price"), scale=2)
        raw_price_on_request = row.get("price_on_request")
        request_mode_blank = raw_price_on_request is None or (
            isinstance(raw_price_on_request, str)
            and not raw_price_on_request.strip()
        )
        preserves_patch_mode = (
            mode is ImportMode.PATCH
            and row["operation"] == "SET"
            and bool(current)
        )
        if (
            "price_on_request" in row
            and request_mode_blank
            and not preserves_patch_mode
        ):
            values["price_on_request"] = values["price"] is None
        else:
            values["price_on_request"] = bool(
                values.get("price_on_request", False)
            )
        values["price_from"] = _optional_decimal(
            values.get("price_from"), scale=2
        )
        try:
            ensure_price_on_request_mode_change(
                current=bool(current.get("price_on_request", False)),
                requested=bool(values["price_on_request"]),
                published_at=current.get("published_at"),
            )
        except ProductPriceOnRequestModeLockedError as exc:
            raise _ProductFieldImportContractError(
                "Цена по запросу", str(exc)
            ) from exc
        if not values["price_on_request"]:
            values["price_from"] = None
        try:
            values["special_price"] = _optional_decimal(
                values.get("special_price"), scale=2
            )
            ensure_product_commercial_terms(
                price=values["price"],
                special_price=values["special_price"],
                price_on_request=bool(values["price_on_request"]),
                price_from=values["price_from"],
            )
        except (
            ImportContractError,
            SpecialEquipmentManagementValidationError,
        ) as exc:
            message = str(exc)
            column_name = (
                "Цена"
                if "Обычная цена" in message
                else (
                    "Специальная цена"
                    if "Специальная цена" in message
                    else "Цена от"
                )
            )
            raise _ProductFieldImportContractError(
                column_name, message
            ) from exc
        values["currency_code"] = str(values.get("currency_code") or "RUB").upper()
        if values["currency_code"] != "RUB":
            raise ImportContractError("Поддерживается только валюта RUB")
        values["owners_count"] = _optional_nonnegative_int(values.get("owners_count"))
        values["no_vin"] = bool(values.get("no_vin", False))
        incoming_vin = row.get("vin")
        incoming_chassis_vin = row.get("chassis_vin")
        incoming_superstructure_vin = row.get("superstructure_vin")
        if values["no_vin"]:
            if (
                (incoming_vin is not None and str(incoming_vin).strip())
                or (
                    incoming_chassis_vin is not None
                    and str(incoming_chassis_vin).strip()
                )
                or (
                    incoming_superstructure_vin is not None
                    and str(incoming_superstructure_vin).strip()
                )
            ):
                raise _ProductFieldImportContractError(
                    "Нет VIN",
                    "При установленном признаке «Нет VIN» поле VIN должно быть пустым (все поля VIN должны оставаться пустыми)",
                    code="VIN_MUST_BE_EMPTY",
                )
            values["vin"] = None
            values["chassis_vin"] = None
            values["superstructure_vin"] = None
        else:
            raw_vin = values.get("vin")
            values["vin"] = (
                str(raw_vin).strip()
                if raw_vin is not None and str(raw_vin).strip()
                else None
            )
            raw_chassis_vin = values.get("chassis_vin")
            values["chassis_vin"] = (
                str(raw_chassis_vin).strip()
                if raw_chassis_vin is not None and str(raw_chassis_vin).strip()
                else None
            )
            raw_superstructure_vin = values.get("superstructure_vin")
            values["superstructure_vin"] = (
                str(raw_superstructure_vin).strip()
                if raw_superstructure_vin is not None and str(raw_superstructure_vin).strip()
                else None
            )

            if values["vin"] and len(values["vin"]) > 17:
                raise ImportContractError("Длина VIN не должна превышать 17 символов")
            if values["chassis_vin"] and len(values["chassis_vin"]) > 32:
                raise ImportContractError("Длина VIN шасси не должна превышать 32 символов")
            if values["superstructure_vin"] and len(values["superstructure_vin"]) > 32:
                raise ImportContractError(
                    "Длина VIN надстройки не должна превышать 32 символов"
                )

            if is_kit and not values["chassis_vin"]:
                raise _ProductFieldImportContractError(
                    "VIN шасси",
                    "Для комплекта техники обязателен VIN шасси при отсутствии признака «Нет VIN»",
                    code="CHASSIS_VIN_REQUIRED_FOR_KIT",
                )

        if is_standalone_superstructure and superstructure_id is not None:
            raw_sup_cats = context.get("superstructure_categories", ())
            sup_cat_pairs = (
                raw_sup_cats.keys()
                if isinstance(raw_sup_cats, dict)
                else raw_sup_cats
            )
            allowed_cats = {
                cid
                for (sid, cid) in sup_cat_pairs
                if sid == superstructure_id
            }
            if planned_superstructure_categories:
                allowed_cats |= {
                    cid
                    for (sid, cid) in planned_superstructure_categories
                    if sid == superstructure_id
                }
            if (
                allowed_cats
                and categories
                and not any(cid in allowed_cats for cid in categories)
            ):
                raise _ProductFieldImportContractError(
                    "Категории",
                    "Категория объявления не входит в список разрешенных категорий выбранного типа надстройки",
                )

        ensure_condition_owners(
            condition=cast("EquipmentCondition", str(values["condition"])),
            owners_count=values["owners_count"],
        )
        ensure_vin_choice(vin=values["vin"], no_vin=values["no_vin"])
        if (
            values.get("sale_status") == "on_order"
            and not values["price_on_request"]
            and (values["special_price"] or values["price"]) is None
        ):
            raise ImportContractError(
                "Для статуса «Под заказ» требуется положительная цена"
            )
        values["published_at"] = _optional_datetime(values.get("published_at"))
        if values.get("publication_status") == "published":
            if values["seller_company_id"] is None:
                raise ImportContractError(
                    "Для публикации объявления требуется продавец"
                )
            if values["published_at"] is None:
                raise ImportContractError(
                    "Для публикации объявления требуется дата публикации"
                )
            if not _product_categories_are_active(
                context=context,
                category_ids=categories,
            ):
                raise ImportContractError(
                    "Товар нельзя опубликовать: выбрана неактивная категория"
                )
            if not directory_chain_active:
                raise ImportContractError(
                    "Товар нельзя опубликовать: "
                    "цепочка марки, модели и модификации неактивна"
                )
        metric_by_category = {
            uuid.UUID(str(record["id"])): cast(
                "UsageMetric",
                str(record["usage_metric"]),
            )
            for record in context.get("categories", {}).values()
        }
        category_metric_overlay = context.get("_planned_category_metrics", {})
        metric_by_category.update(category_metric_overlay)
        metric = ensure_single_usage_metric(
            category_ids=categories,
            metric_by_category=metric_by_category,
        )
        values["mileage_km"] = _optional_nonnegative_int(values.get("mileage_km"))
        values["engine_hours"] = _optional_nonnegative_int(values.get("engine_hours"))
        ensure_condition_usage(
            condition=cast("EquipmentCondition", str(values["condition"])),
            usage_metric=metric,
            mileage_km=values["mileage_km"],
            engine_hours=values["engine_hours"],
        )
        if not _attach_product_images_action(
            values=values,
            row=row,
            mode=mode,
            code=code,
            context=context,
            issues=issues,
        ):
            return None
        if (
            row["operation"] == "SET"
            and current
            and values.get("_images_action") == "keep"
            and not _product_attributes_changed(values=values, current=current)
        ):
            row["operation"] = "NOOP"
        if values.get("publication_status") == "published" and modification_id is not None:
            required_attributes = _required_attributes_for_categories(
                context=context,
                category_ids=categories,
            )
            actual_attributes = _attributes_for_modification(
                context=context,
                modification_id=modification_id,
            )
            missing_attributes = required_attributes - actual_attributes
            if missing_attributes:
                raise ImportContractError(
                    "У модификации не заполнены обязательные характеристики: "
                    + ", ".join(sorted(map(str, missing_attributes)))
                )
    except (_ProductFieldImportContractError, ReferenceNotInSnapshotError) as exc:
        issues.append(
            _row_issue(
                row,
                exc.code,
                str(exc),
                entity_code=code,
                column_name=getattr(exc, "column_name", None),
            )
        )
        return None
    except (
        ImportContractError,
        SpecialEquipmentCatalogError,
        SpecialEquipmentManagementValidationError,
        ValueError,
        TypeError,
    ) as exc:
        issues.append(_row_issue(row, "PRODUCT_INVALID", str(exc), entity_code=code))
        return None
    plan_row = _entity_plan_row(family="products", row=row, values=values)
    plan_row["_warehouse_assignment_explicit"] = False
    return plan_row


def _product_categories_are_active(
    *,
    context: Mapping[str, Any],
    category_ids: Iterable[uuid.UUID],
) -> bool:
    records = context.get("_effective_catalog_entities")
    if isinstance(records, Mapping):
        categories = records.get("categories", {})
    else:
        categories = {
            uuid.UUID(str(record["id"])): record
            for record in context.get("categories", {}).values()
        }
    return all(
        category_id in categories and bool(categories[category_id].get("is_active"))
        for category_id in category_ids
    )


def _product_directory_state(
    *,
    context: Mapping[str, Any],
    modification_id: uuid.UUID,
) -> tuple[bool, Mapping[str, Any] | None]:
    records = context.get("_effective_catalog_entities")
    if not isinstance(records, Mapping):
        records = {
            family: {
                uuid.UUID(str(record["id"])): record
                for record in context.get(family, {}).values()
            }
            for family in ("marks", "models", "modifications")
        }
    modifications = records.get("modifications", {})
    models = records.get("models", {})
    marks = records.get("marks", {})
    modification = modifications.get(modification_id)
    if not isinstance(modification, Mapping):
        return False, None
    model = models.get(modification.get("model_id"))
    if not isinstance(model, Mapping):
        return False, modification
    mark = marks.get(model.get("mark_id"))
    if not isinstance(mark, Mapping):
        return False, modification
    return (
        all(
            (
                modification.get("is_active"),
                model.get("is_active"),
                mark.get("is_active"),
            )
        ),
        modification,
    )


def _required_attributes_for_categories(
    *,
    context: Mapping[str, Any],
    category_ids: Iterable[uuid.UUID],
) -> set[uuid.UUID]:
    mode = ImportMode(str(context.get("_import_mode") or ImportMode.PATCH.value))
    edges = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else set(context.get("category_relations", set()))
    )
    for row in context.get("_planned_category_relations", ()):
        edge = (
            uuid.UUID(str(row["values"]["parent_id"])),
            uuid.UUID(str(row["values"]["child_id"])),
        )
        if row["operation"] == "DELETE":
            edges.discard(edge)
        else:
            edges.add(edge)

    rules = (
        {}
        if mode is ImportMode.FULL_SNAPSHOT
        else dict(context.get("category_attributes", {}))
    )
    for row in context.get("_planned_category_attributes", ()):
        key = (
            uuid.UUID(str(row["values"]["category_id"])),
            uuid.UUID(str(row["values"]["attribute_id"])),
        )
        if row["operation"] == "DELETE":
            rules.pop(key, None)
        else:
            rules[key] = row["values"]

    parents: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for parent_id, child_id in edges:
        parents[child_id].add(parent_id)
    relevant = set(category_ids)
    pending = list(relevant)
    while pending:
        child_id = pending.pop()
        for parent_id in parents.get(child_id, ()):
            if parent_id not in relevant:
                relevant.add(parent_id)
                pending.append(parent_id)
    return {
        attribute_id
        for (category_id, attribute_id), rule in rules.items()
        if category_id in relevant and bool(rule["is_required"])
    }


def _attributes_for_modification(
    *,
    context: Mapping[str, Any],
    modification_id: uuid.UUID,
) -> set[uuid.UUID]:
    mode = ImportMode(str(context.get("_import_mode") or ImportMode.PATCH.value))
    values = (
        set()
        if mode is ImportMode.FULL_SNAPSHOT
        else {
            attribute_id
            for current_modification_id, attribute_id in context.get(
                "modification_attribute_values",
                set(),
            )
            if current_modification_id == modification_id
        }
    )
    for row in context.get("_planned_modification_attribute_values", ()):
        if uuid.UUID(str(row["values"]["modification_id"])) != modification_id:
            continue
        attribute_id = uuid.UUID(str(row["values"]["attribute_id"]))
        if row["operation"] == "DELETE":
            values.discard(attribute_id)
        else:
            values.add(attribute_id)
    return values


def _resolved_id(
    *,
    family: str,
    code: str,
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    context: Mapping[str, Any],
    mode: ImportMode | None = None,
) -> uuid.UUID | None:
    if not code:
        return None
    if mode is ImportMode.FULL_SNAPSHOT and code not in valid_codes.get(family, set()):
        return None
    if code in context.get(family, {}):
        return uuid.UUID(str(context[family][code]["id"]))
    if code in valid_codes.get(family, set()):
        return identity.get(family, {}).get(code)
    return None


def _resolve_reference(
    *,
    family: str,
    code: str,
    identity: Mapping[str, Mapping[str, uuid.UUID]],
    valid_codes: Mapping[str, set[str]],
    context: Mapping[str, Any],
    mode: ImportMode,
    row: Mapping[str, Any],
    issues: V2IssueCollector,
    not_found_code: str,
    not_found_message: str,
    column_name: str | None = None,
    entity_code: str | None = None,
) -> uuid.UUID | None:
    if not code:
        issues.append(
            _row_issue(
                row,
                not_found_code,
                not_found_message,
                column_name=column_name,
                entity_code=entity_code,
            )
        )
        return None
    resolved = _resolved_id(
        family=family,
        code=code,
        identity=identity,
        valid_codes=valid_codes,
        context=context,
        mode=mode,
    )
    if resolved is not None:
        return resolved
    if mode is ImportMode.FULL_SNAPSHOT and code in context.get(family, {}):
        issues.append(
            _row_issue(
                row,
                REFERENCE_NOT_IN_SNAPSHOT,
                REFERENCE_NOT_IN_SNAPSHOT_MESSAGE,
                column_name=column_name,
                entity_code=entity_code,
            )
        )
        return None
    issues.append(
        _row_issue(
            row,
            not_found_code,
            not_found_message,
            column_name=column_name,
            entity_code=entity_code,
        )
    )
    return None


def _merge_values(
    *,
    row: Mapping[str, Any],
    current: Mapping[str, Any],
    mode: ImportMode,
    fields: tuple[str, ...],
    required: set[str],
    family: str | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    clear_fields = set(row.get("_clear_fields") or ())
    field_defaults = dict(defaults or {})
    if "is_active" not in field_defaults and "is_active" in fields:
        field_defaults["is_active"] = True

    for field in fields:
        incoming = row.get(field)
        blank = incoming is None or (isinstance(incoming, str) and not incoming.strip())
        operation = row.get("operation")
        has_default = field in field_defaults
        default_val = field_defaults.get(field)

        if has_default:
            if field in clear_fields:
                value = default_val
            elif blank:
                if operation == "ADD":
                    value = default_val
                elif mode is ImportMode.PATCH or mode is ImportMode.FULL_SNAPSHOT:
                    curr_val = current.get(field)
                    value = curr_val if curr_val is not None else default_val
                else:
                    value = default_val
            else:
                value = incoming
        elif field in clear_fields:
            value = None
        elif mode is ImportMode.PATCH and operation in {"SET", "UPSERT"} and blank:
            value = current.get(field)
        else:
            value = incoming

        if (
            field in {"is_attachment_category", "is_active"}
            and value is not None
            and not isinstance(value, bool)
        ):
            try:
                value = parse_bool(value)
            except ImportContractError as exc:
                title = (
                    special_equipment_column_title(family, field)
                    if family
                    else None
                )
                raise ImportContractError(
                    str(exc),
                    column_name=title or exc.column_name,
                ) from exc

        if field in required and (
            value is None or (isinstance(value, str) and not value.strip())
        ):
            title = (
                special_equipment_column_title(family, field)
                if family
                else None
            )
            raise ImportContractError(
                f"Поле «{field}» обязательно",
                column_name=title,
            )
        values[field] = value
    return values


def _entity_plan_row(
    *, family: str, row: Mapping[str, Any], values: Mapping[str, Any]
) -> dict[str, Any]:
    code = str(row["_code"])
    aggregate_code = str(row["_identity_key"]) if family == "trims" else code
    return {
        "id": row["_id"],
        "code": code,
        "operation": row["operation"],
        "values": dict(values),
        "_sheet_code": row["_sheet_code"],
        "_row_number": row["_row_number"],
        "_aggregate_kind": _aggregate_kind_for_family(family),
        "_aggregate_code": aggregate_code,
    }


def _aggregate_kind_for_family(family: str) -> str:
    return {
        "modifications": "modification",
        "products": "product",
        "categories": "category",
    }.get(family, family.removesuffix("s"))


def _link_plan_row(
    row: Mapping[str, Any],
    *,
    values: Mapping[str, Any],
    aggregate_kind: str,
    aggregate_code: str,
) -> dict[str, Any]:
    return {
        "operation": row["operation"],
        "values": dict(values),
        "_sheet_code": row["_sheet_code"],
        "_row_number": row["_row_number"],
        "_aggregate_kind": aggregate_kind,
        "_aggregate_code": aggregate_code,
    }


def _preflight_required_columns(
    plan: dict[str, JsonlRows],
    *,
    issues: V2IssueCollector,
    valid_codes: dict[str, set[str]],
) -> None:
    not_null_columns = repo.get_v2_not_null_columns_without_default()
    rejected_by_family: dict[str, set[str]] = defaultdict(set)

    for family, required_cols in not_null_columns.items():
        if family not in plan or not required_cols:
            continue
        valid_rows: list[dict[str, Any]] = []
        for row in plan[family]:
            if row.get("operation") == "DELETE":
                valid_rows.append(row)
                continue
            values = row.get("values", {})
            missing_cols: list[str] = []
            for col in required_cols:
                if col == "code":
                    val = (
                        row.get("code")
                        if row.get("code") is not None
                        else values.get("code")
                    )
                else:
                    val = values.get(col)
                if val is None:
                    missing_cols.append(col)
            if missing_cols:
                aggregate_code = str(
                    row.get("_aggregate_code")
                    or row.get("code")
                    or ""
                )
                if aggregate_code:
                    rejected_by_family[family].add(aggregate_code)
                for col in missing_cols:
                    column_title = special_equipment_column_title(family, col) or col
                    issues.append(
                        ImportIssue(
                            sheet_code=str(
                                row.get("_sheet_code")
                                or DATA_SHEET_NAMES.get(family, family)
                            ),
                            row_number=(
                                int(row["_row_number"])
                                if row.get("_row_number") is not None
                                else None
                            ),
                            code="REQUIRED_FIELD_MISSING",
                            message=f"Не заполнено обязательное поле «{column_title}»",
                            severity=IssueSeverity.ERROR,
                            column_name=column_title,
                            entity_type=str(row.get("_aggregate_kind") or "") or None,
                            external_key=aggregate_code or None,
                        )
                    )
            else:
                valid_rows.append(row)
        if len(valid_rows) != len(plan[family]):
            plan[family].replace(valid_rows)

    for family, rejected_codes in rejected_by_family.items():
        if not rejected_codes:
            continue
        if family in valid_codes:
            valid_codes[family].difference_update(rejected_codes)
        root_family = {
            "modification_categories": "modifications",
            "modification_attribute_values": "modifications",
            "trim_attributes": "trims",
            "trim_attribute_values": "trims",
            "superstructure_categories": "superstructures",
            "superstructure_attributes": "superstructures",
            "product_categories": "products",
            "product_chassis_values": "products",
            "product_superstructure_values": "products",
            "product_attachments": "products",
            "category_relations": "categories",
            "category_attributes": "categories",
        }.get(family, family)
        if root_family in valid_codes:
            valid_codes[root_family].difference_update(rejected_codes)
        if root_family in plan:
            plan[root_family].replace(
                row
                for row in plan[root_family]
                if str(row.get("_aggregate_code") or row.get("code") or "") not in rejected_codes
            )
        if root_family == "categories":
            for link_fam in ("category_attributes", "category_relations"):
                if link_fam in plan:
                    plan[link_fam].replace(
                        row
                        for row in plan[link_fam]
                        if str(row.get("_aggregate_code") or "") not in rejected_codes
                    )
        if root_family == "superstructures":
            for link_fam in ("superstructure_attributes", "superstructure_categories"):
                if link_fam in plan:
                    plan[link_fam].replace(
                        row
                        for row in plan[link_fam]
                        if str(row.get("_aggregate_code") or "") not in rejected_codes
                    )


def _prune_rejected_aggregate_links(
    plan: dict[str, JsonlRows],
    *,
    valid_codes: Mapping[str, set[str]],
    context: Mapping[str, Any],
    submitted_root_codes: Mapping[str, set[str]],
) -> None:
    for family, root_family in (
        ("modification_categories", "modifications"),
        ("modification_attribute_values", "modifications"),
        ("superstructure_categories", "superstructures"),
        ("superstructure_attributes", "superstructures"),
        ("product_categories", "products"),
        ("product_chassis_values", "products"),
        ("product_superstructure_values", "products"),
        ("product_attachments", "products"),
    ):
        plan[family].replace(
            row
            for row in plan[family]
            if str(row["_aggregate_code"]) in valid_codes.get(root_family, set())
            or (
                str(row["_aggregate_code"]) in context.get(root_family, {})
                and str(row["_aggregate_code"])
                not in submitted_root_codes.get(root_family, set())
            )
        )


def _build_summary(
    *,
    raw_rows: Mapping[str, list[dict[str, Any]]],
    plan: Mapping[str, JsonlRows],
    issues: V2IssueCollector,
    mode: ImportMode,
) -> dict[str, Any]:
    actions = Counter(
        str(row["operation"]).lower() for rows in plan.values() for row in rows
    )
    accepted = sum(len(rows) for rows in plan.values())
    destructive = actions["delete"]
    changes = _summary_changes(plan)
    counts: dict[str, dict[str, int]] = {}
    for family, rows in plan.items():
        family_actions = Counter(str(row["operation"]) for row in rows)
        counts[family] = {
            "create": family_actions["ADD"],
            "update": family_actions["SET"],
            "archive": 0,
            "remove": family_actions["DELETE"],
            "noop": family_actions["NOOP"],
            "rejected": 0,
        }
    return {
        "rows": {family: len(rows) for family, rows in raw_rows.items()},
        "acceptedRows": accepted,
        "rejectedRows": issues.error_count,
        "errors": issues.error_count,
        "warnings": issues.warning_count,
        "issuesTotal": issues.total_count,
        "issuesStored": len(issues),
        "issuesTruncated": issues.is_truncated,
        "actions": dict(actions),
        "destructiveCount": destructive,
        "destructivePercent": round(destructive * 100 / max(accepted, 1), 2),
        "requiresDestructiveConfirmation": (
            destructive > 0 or mode is ImportMode.FULL_SNAPSHOT
        ),
        "operationCounts": counts,
        "changes": changes,
        "changesTotal": accepted,
        "changesStored": len(changes),
        "changesTruncated": accepted > len(changes),
        "commerceImpact": {
            "favorites": 0,
            "cart_items": 0,
            "leasing_applications": 0,
            "purchase_orders": 0,
            "reservations": 0,
        },
        "imageSummary": {
            "requested": 0,
            "transferred": 0,
            "reused": 0,
            "optionalFailures": 0,
            "blockingFailures": 0,
        },
        "mode": mode.value,
    }


def _summary_changes(plan: Mapping[str, Iterable[Mapping[str, Any]]]) -> list[dict[str, Any]]:
    generic = [
        {
            "entityType": family,
            "entityCode": str(
                row.get("_aggregate_code") or row.get("code") or ""
            ),
            "operation": str(row["operation"]),
            "field": None,
            "before": None,
            "after": row["operation"] != "DELETE",
        }
        for family, rows in plan.items()
        for row in rows
        if row["operation"] != "NOOP"
    ]
    warehouse = [
        {
            "entityType": "products",
            "entityCode": str(row["_aggregate_code"]),
            "operation": str(row["operation"]),
            "field": "warehouse_id",
            "before": row.get("_warehouse_before"),
            "after": row.get("values", {}).get("warehouse_id"),
        }
        for row in plan.get("products", ())
        if row.get("_warehouse_target_applied") and row["operation"] != "NOOP"
    ]
    return (warehouse + generic)[:50]


def rebuild_summary_for_plan(
    summary: Mapping[str, Any], plan: Mapping[str, JsonlRows], mode: ImportMode
) -> dict[str, Any]:
    """Rebuild all preview values derived from the actual persisted plan."""
    actions = Counter(str(row["operation"]).lower() for rows in plan.values() for row in rows)
    accepted = sum(len(rows) for rows in plan.values())
    destructive = actions["delete"]
    changes = _summary_changes(plan)
    counts = {}
    for family, rows in plan.items():
        family_actions = Counter(str(row["operation"]) for row in rows)
        counts[family] = {
            "create": family_actions["ADD"],
            "update": family_actions["SET"],
            "archive": 0,
            "remove": family_actions["DELETE"],
            "noop": family_actions["NOOP"],
            "rejected": 0,
        }
    return {
        **summary,
        "acceptedRows": accepted,
        "actions": dict(actions),
        "destructiveCount": destructive,
        "destructivePercent": round(destructive * 100 / max(accepted, 1), 2),
        "requiresDestructiveConfirmation": destructive > 0 or mode is ImportMode.FULL_SNAPSHOT,
        "operationCounts": counts,
        "changes": changes,
        "changesTotal": accepted,
        "changesStored": len(changes),
        "changesTruncated": accepted > len(changes),
    }


def _required_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(parse_bool(value))


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ImportContractError("Ожидается неотрицательное целое число")
    parsed = int(value)
    if parsed < 0:
        raise ImportContractError("Значение не может быть отрицательным")
    return parsed


def _optional_year(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = int(value)
    if not 1900 <= parsed <= 2200:
        raise ImportContractError("Год должен быть в диапазоне 1900–2200")
    return parsed


def _optional_nonnegative_int(value: Any) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return _nonnegative_int(value)


def _decimal(value: Any, *, scale: int) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ImportContractError("Некорректное числовое значение") from exc
    quantum = Decimal(1).scaleb(-scale)
    if parsed < 0 or parsed.quantize(quantum) != parsed:
        raise ImportContractError(
            f"Число должно быть неотрицательным, не более {scale} знаков после запятой"
        )
    return parsed


def _optional_decimal(value: Any, *, scale: int) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _decimal(value, scale=scale)


def _optional_datetime(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ImportContractError("Дата должна содержать часовой пояс")
    return parsed.isoformat()


def _comparable_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def _manifest_issue(code: str) -> ImportIssue:
    return ImportIssue(
        sheet_code="Параметры",
        code=code,
        message="Параметры книги не соответствуют заданию импорта",
    )


def _row_issue(
    row: Mapping[str, Any],
    code: str,
    message: str,
    *,
    severity: IssueSeverity = IssueSeverity.ERROR,
    entity_code: str | None = None,
    column_name: str | None = None,
) -> ImportIssue:
    return ImportIssue(
        sheet_code=str(row.get("_sheet_code") or "Книга"),
        row_number=(
            int(row["_row_number"]) if row.get("_row_number") is not None else None
        ),
        code=code,
        message=message[:1000],
        severity=severity,
        column_name=column_name,
        entity_type=str(row.get("_aggregate_kind") or "") or None,
        external_key=entity_code,
    )
