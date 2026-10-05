"""Factories for the corrected special-equipment test catalog."""

from __future__ import annotations

from uuid import UUID, uuid4

from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
)


def special_equipment_directory(
    *,
    mark_name: str,
    model_name: str,
    modification_name: str,
    mark_id: UUID | None = None,
    model_id: UUID | None = None,
    modification_id: UUID | None = None,
) -> tuple[
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
]:
    """Return one explicit Mark → Model → Modification chain."""

    suffix = uuid4().hex
    resolved_mark_id = mark_id or uuid4()
    resolved_model_id = model_id or uuid4()
    resolved_modification_id = modification_id or uuid4()
    mark = SpecialEquipmentMark(
        id=resolved_mark_id,
        code=f"mark-{suffix}",
        name=mark_name,
        slug=f"mark-{suffix}",
    )
    model = SpecialEquipmentModel(
        id=resolved_model_id,
        mark_id=resolved_mark_id,
        code=f"model-{suffix}",
        name=model_name,
        slug=f"model-{suffix}",
    )
    modification = SpecialEquipmentModification(
        id=resolved_modification_id,
        model_id=resolved_model_id,
        code=f"modification-{suffix}",
        name=modification_name,
        slug=f"modification-{suffix}",
    )
    return mark, model, modification
