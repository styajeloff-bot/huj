"""Repository operations for special equipment catalog cascade delete."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.special_equipment_cascade_delete import (
    TYPE_TO_DELETE_KEY,
    CascadeGraphSnapshot,
    CascadePlan,
    DistributorBlocker,
    EntityRef,
    KitSourceBlocker,
    KitSourceBlockerItem,
    KitSourceProductRef,
    ProductBlocker,
    ProductBlockerDocument,
    SupportProgramBlocker,
    SupportProgramBlockerReference,
)
from domain.special_equipment_management import SpecialEquipmentManagementNotFoundError
from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleAllocation,
    LeasingApplication,
)
from infrastructure.models.companies import Company, DistributorBrand
from infrastructure.models.exchange import ExchangeCartItem, ExchangeRequest
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import (
    SpecialEquipmentAttribute,
    SpecialEquipmentAttributeGroup,
    SpecialEquipmentAttributeOption,
    SpecialEquipmentCatalogDeletionLog,
    SpecialEquipmentCategory,
    SpecialEquipmentCategoryAttribute,
    SpecialEquipmentCategoryRelation,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationAttributeValue,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductAttachment,
    SpecialEquipmentProductCategory,
    SpecialEquipmentProductImage,
    SpecialEquipmentSuperstructure,
    SpecialEquipmentSuperstructureAttribute,
    SpecialEquipmentTrim,
    SpecialEquipmentTrimAttribute,
    SpecialEquipmentTrimAttributeValue,
)
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentCartItem,
    SpecialEquipmentFavorite,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.models.special_equipment_import import (
    SpecialEquipmentCatalogState,
    SpecialEquipmentExternalRef,
)
from infrastructure.models.special_equipment_registry import (
    SpecialEquipmentCatalogMutationReceipt,
    SpecialEquipmentMediaCleanupJob,
)
from infrastructure.models.support import SupportProgram, SupportProgramMark
from infrastructure.models.users import UserFavorite
from infrastructure.models.vehicles import (
    VehicleWarehouseTransfer,
    Warehouse,
    WarehouseAccessRule,
    WarehouseMark,
)

_CATALOG_ADVISORY_LOCK = 21808

_MODEL_BY_DELETE_KEY: dict[str, Any] = {
    "marks": SpecialEquipmentMark,
    "models": SpecialEquipmentModel,
    "modifications": SpecialEquipmentModification,
    "trims": SpecialEquipmentTrim,
    "superstructures": SpecialEquipmentSuperstructure,
    "categories": SpecialEquipmentCategory,
    "attribute_groups": SpecialEquipmentAttributeGroup,
    "attributes": SpecialEquipmentAttribute,
    "options": SpecialEquipmentAttributeOption,
    "colors": SpecialEquipmentColor,
    "products": SpecialEquipmentProduct,
}


async def lock_catalog_for_mutation(session: AsyncSession) -> None:
    """Serialize writes with management peers and import apply."""
    await session.execute(
        sa.select(sa.func.pg_advisory_xact_lock(_CATALOG_ADVISORY_LOCK))
    )
    await session.execute(
        sa.select(SpecialEquipmentCatalogState.singleton)
        .where(SpecialEquipmentCatalogState.singleton.is_(True))
        .with_for_update()
    )


async def get_catalog_revision(
    session: AsyncSession, *, for_update: bool = False
) -> int:
    """Fetch current catalog revision."""
    query = sa.select(SpecialEquipmentCatalogState.revision).where(
        SpecialEquipmentCatalogState.singleton.is_(True)
    )
    if for_update:
        query = query.with_for_update()
    rev = await session.scalar(query)
    return int(rev or 0)


async def increment_catalog_revision(session: AsyncSession) -> int:
    """Increment catalog revision atomically and return the new revision."""
    revision = (
        await session.execute(
            sa.update(SpecialEquipmentCatalogState)
            .where(SpecialEquipmentCatalogState.singleton.is_(True))
            .values(
                revision=SpecialEquipmentCatalogState.revision + 1,
                updated_at=sa.func.now(),
                updated_by=None,
            )
            .returning(SpecialEquipmentCatalogState.revision)
        )
    ).scalar_one()
    return int(revision)


async def enqueue_media_cleanup(session: AsyncSession, storage_key: str) -> None:
    """Enqueue a media storage key for background deletion."""
    await session.execute(
        insert(SpecialEquipmentMediaCleanupJob)
        .values(storage_key=storage_key)
        .on_conflict_do_update(
            index_elements=["storage_key"],
            set_={
                "status": "pending",
                "next_attempt_at": datetime.now(UTC),
                "lease_owner": None,
                "lease_until": None,
                "completed_at": None,
            },
        )
    )


async def _resolve_root(
    session: AsyncSession, norm_type: str, root_id: uuid.UUID
) -> EntityRef:
    """Resolve and return root entity reference, or raise if not found."""
    model = _MODEL_BY_DELETE_KEY.get(norm_type)
    if model is None:
        raise ValueError(f"Неподдерживаемый тип корня: {norm_type}")

    row = await session.scalar(sa.select(model).where(model.id == root_id))
    if row is None:
        raise SpecialEquipmentManagementNotFoundError("Ресурс не найден")

    code = getattr(row, "code", None)
    name = getattr(row, "name", None)
    if name is None:
        name = getattr(row, "vin", None) or code

    singular = norm_type.rstrip("s")
    if norm_type == "categories":
        singular = "category"
    elif norm_type == "attribute_groups":
        singular = "attribute_group"

    return EntityRef(type=singular, id=root_id, code=code, name=name)


async def _load_product_neighborhood(
    session: AsyncSession,
    graph: CascadeGraphSnapshot,
    initial_product_ids: set[uuid.UUID],
) -> None:
    """Gather composite ad connections, cart counts, favorite counts, and categories for products."""
    known_ids = set(initial_product_ids)
    if not known_ids:
        return

    # Categories
    p_cats = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductCategory.product_id,
                SpecialEquipmentProductCategory.category_id,
            ).where(SpecialEquipmentProductCategory.product_id.in_(known_ids))
        )
    ).all()
    for pid, cat_id in p_cats:
        graph.product_category_ids.setdefault(pid, set()).add(cat_id)

    # Carts
    se_carts = (
        await session.execute(
            sa.select(
                SpecialEquipmentCartItem.product_id,
                sa.func.count(SpecialEquipmentCartItem.id),
            )
            .where(SpecialEquipmentCartItem.product_id.in_(known_ids))
            .group_by(SpecialEquipmentCartItem.product_id)
        )
    ).all()
    for pid, cnt in se_carts:
        graph.product_cart_counts[pid] = graph.product_cart_counts.get(pid, 0) + cnt

    ex_carts = (
        await session.execute(
            sa.select(
                ExchangeCartItem.product_id,
                sa.func.count(ExchangeCartItem.id),
            )
            .where(ExchangeCartItem.product_id.in_(known_ids))
            .group_by(ExchangeCartItem.product_id)
        )
    ).all()
    for pid, cnt in ex_carts:
        graph.product_cart_counts[pid] = graph.product_cart_counts.get(pid, 0) + cnt

    # Favorites
    se_favs = (
        await session.execute(
            sa.select(
                SpecialEquipmentFavorite.product_id,
                sa.func.count(SpecialEquipmentFavorite.user_id),
            )
            .where(SpecialEquipmentFavorite.product_id.in_(known_ids))
            .group_by(SpecialEquipmentFavorite.product_id)
        )
    ).all()
    for pid, cnt in se_favs:
        graph.product_favorite_counts[pid] = (
            graph.product_favorite_counts.get(pid, 0) + cnt
        )

    user_favs = (
        await session.execute(
            sa.select(
                UserFavorite.product_id,
                sa.func.count(UserFavorite.id),
            )
            .where(UserFavorite.product_id.in_(known_ids))
            .group_by(UserFavorite.product_id)
        )
    ).all()
    for pid, cnt in user_favs:
        graph.product_favorite_counts[pid] = (
            graph.product_favorite_counts.get(pid, 0) + cnt
        )

    # Kit source references
    kit_sources = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.code,
                SpecialEquipmentProduct.vin,
                SpecialEquipmentProduct.superstructure_source_product_id,
            ).where(
                SpecialEquipmentProduct.superstructure_source_product_id.in_(known_ids)
            )
        )
    ).all()
    for kid, kcode, kvin, source_id in kit_sources:
        if source_id is not None:
            graph.kit_sources_by_source_product_id.setdefault(source_id, []).append(
                KitSourceBlockerItem(
                    id=kid,
                    code=kcode,
                    title=kvin or kcode,
                )
            )


async def _load_graph_marks(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_mark(root_id, code=root_ref.code or "", name=root_ref.name or "")
    wh_cnt = (
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(WarehouseMark)
            .where(WarehouseMark.mark_id == root_id)
        )
        or 0
    )
    graph.warehouse_mark_counts[root_id] = wh_cnt
    war_cnt = (
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(WarehouseAccessRule)
            .where(WarehouseAccessRule.brand_id == root_id)
        )
        or 0
    )
    graph.warehouse_access_rule_mark_counts[root_id] = war_cnt

    models = (
        await session.execute(
            sa.select(SpecialEquipmentModel).where(
                SpecialEquipmentModel.mark_id == root_id
            )
        )
    ).scalars().all()
    model_ids = {m.id for m in models}
    for m in models:
        graph.add_model(m.id, mark_id=m.mark_id, code=m.code, name=m.name)

    if not model_ids:
        return

    mods = (
        await session.execute(
            sa.select(SpecialEquipmentModification).where(
                SpecialEquipmentModification.model_id.in_(model_ids)
            )
        )
    ).scalars().all()
    mod_ids = {mod.id for mod in mods}
    for mod in mods:
        graph.add_modification(
            mod.id, model_id=mod.model_id, code=mod.code, name=mod.name
        )

    if not mod_ids:
        return

    await _load_modifications_content(session, graph, mod_ids)


async def _load_modifications_content(
    session: AsyncSession, graph: CascadeGraphSnapshot, mod_ids: set[uuid.UUID]
) -> None:
    mod_cats = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationCategory.modification_id,
                SpecialEquipmentModificationCategory.category_id,
            ).where(
                SpecialEquipmentModificationCategory.modification_id.in_(mod_ids)
            )
        )
    ).all()
    for mid, cid in mod_cats:
        graph.modification_category_ids.setdefault(mid, set()).add(cid)

    mod_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
            ).where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(mod_ids)
            )
        )
    ).all()
    for mid, aid, oid in mod_vals:
        graph.modification_attribute_values.setdefault(mid, {})[aid] = oid

    trims = (
        await session.execute(
            sa.select(SpecialEquipmentTrim).where(
                SpecialEquipmentTrim.modification_id.in_(mod_ids)
            )
        )
    ).scalars().all()
    trim_ids = {t.id for t in trims}
    for t in trims:
        graph.add_trim(
            t.id,
            modification_id=t.modification_id,
            code=t.code,
            name=t.name,
        )

    if trim_ids:
        trim_vals = (
            await session.execute(
                sa.select(
                    SpecialEquipmentTrimAttributeValue.trim_id,
                    SpecialEquipmentTrimAttributeValue.attribute_id,
                    SpecialEquipmentTrimAttributeValue.option_id,
                ).where(SpecialEquipmentTrimAttributeValue.trim_id.in_(trim_ids))
            )
        ).all()
        for tid, aid, oid in trim_vals:
            graph.trim_attribute_values.setdefault(tid, {})[aid] = oid

    prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                sa.or_(
                    SpecialEquipmentProduct.modification_id.in_(mod_ids),
                    SpecialEquipmentProduct.superstructure_modification_id.in_(mod_ids),
                )
            )
        )
    ).scalars().all()
    for p in prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            body_color_id=p.body_color_id,
            interior_color_id=p.interior_color_id,
            superstructure_id=p.superstructure_id,
            superstructure_model_id=p.superstructure_model_id,
            superstructure_modification_id=p.superstructure_modification_id,
            superstructure_source_product_id=p.superstructure_source_product_id,
            code=p.code,
            name=p.vin or p.code,
        )
    await _load_product_neighborhood(session, graph, {p.id for p in prods})


async def _load_graph_models(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_model(
        root_id, mark_id=uuid.UUID(int=0), code=root_ref.code or "", name=root_ref.name or ""
    )
    mods = (
        await session.execute(
            sa.select(SpecialEquipmentModification).where(
                SpecialEquipmentModification.model_id == root_id
            )
        )
    ).scalars().all()
    mod_ids = {mod.id for mod in mods}
    for mod in mods:
        graph.add_modification(
            mod.id, model_id=mod.model_id, code=mod.code, name=mod.name
        )

    s_prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.superstructure_model_id == root_id
            )
        )
    ).scalars().all()
    for p in s_prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            body_color_id=p.body_color_id,
            interior_color_id=p.interior_color_id,
            superstructure_id=p.superstructure_id,
            superstructure_model_id=p.superstructure_model_id,
            superstructure_modification_id=p.superstructure_modification_id,
            superstructure_source_product_id=p.superstructure_source_product_id,
            code=p.code,
            name=p.vin or p.code,
        )
    if s_prods:
        await _load_product_neighborhood(session, graph, {p.id for p in s_prods})

    if mod_ids:
        await _load_modifications_content(session, graph, mod_ids)


async def _load_graph_superstructures(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, _root_ref: EntityRef
) -> None:
    s = (
        await session.execute(
            sa.select(SpecialEquipmentSuperstructure).where(
                SpecialEquipmentSuperstructure.id == root_id
            )
        )
    ).scalar_one_or_none()
    if s is not None:
        graph.add_superstructure(
            s.id,
            code=s.code,
            name=s.name,
        )
    prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.superstructure_id == root_id
            )
        )
    ).scalars().all()
    for p in prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            body_color_id=p.body_color_id,
            interior_color_id=p.interior_color_id,
            superstructure_id=p.superstructure_id,
            superstructure_model_id=p.superstructure_model_id,
            superstructure_modification_id=p.superstructure_modification_id,
            superstructure_source_product_id=p.superstructure_source_product_id,
            code=p.code,
            name=p.vin or p.code,
        )
    await _load_product_neighborhood(session, graph, {p.id for p in prods})


async def _load_graph_modifications(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_modification(
        root_id, model_id=uuid.UUID(int=0), code=root_ref.code or "", name=root_ref.name or ""
    )
    await _load_modifications_content(session, graph, {root_id})


async def _load_graph_trims(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_trim(
        root_id, modification_id=uuid.UUID(int=0), code=root_ref.code or "", name=root_ref.name or ""
    )
    trim_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttributeValue.attribute_id,
                SpecialEquipmentTrimAttributeValue.option_id,
            ).where(SpecialEquipmentTrimAttributeValue.trim_id == root_id)
        )
    ).all()
    for aid, oid in trim_vals:
        graph.trim_attribute_values.setdefault(root_id, {})[aid] = oid

    prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.trim_id == root_id
            )
        )
    ).scalars().all()
    for p in prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            code=p.code,
            name=p.vin or p.code,
        )


async def _load_graph_categories(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID
) -> None:
    cte_query = sa.text(
        """
        WITH RECURSIVE cat_tree AS (
            SELECT child_id AS id FROM special_equipment_category_relations WHERE parent_id = :root_id
            UNION
            SELECT r.child_id FROM special_equipment_category_relations r
            JOIN cat_tree ct ON r.parent_id = ct.id
        )
        SELECT id FROM cat_tree
        """
    )
    child_ids = set(
        (await session.execute(cte_query, {"root_id": root_id})).scalars().all()
    )
    all_cat_ids = child_ids | {root_id}

    warehouse_categories = (await session.execute(
        sa.select(Warehouse.category_id, sa.func.count(Warehouse.id))
        .where(Warehouse.category_id.in_(all_cat_ids))
        .group_by(Warehouse.category_id)
    )).all()
    for category_id, warehouse_count in warehouse_categories:
        if category_id is not None:
            graph.warehouse_category_counts[category_id] = warehouse_count

    cats = (
        await session.execute(
            sa.select(SpecialEquipmentCategory).where(
                SpecialEquipmentCategory.id.in_(all_cat_ids)
            )
        )
    ).scalars().all()
    for c in cats:
        graph.add_category(c.id, code=c.code, name=c.name)

    cat_parents = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryRelation.parent_id,
                SpecialEquipmentCategoryRelation.child_id,
            ).where(SpecialEquipmentCategoryRelation.child_id.in_(all_cat_ids))
        )
    ).all()
    for pid, cid in cat_parents:
        graph.category_parent_ids.setdefault(cid, set()).add(pid)

    cat_attrs = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.attribute_id,
            ).where(SpecialEquipmentCategoryAttribute.category_id.in_(all_cat_ids))
        )
    ).all()
    for cid, aid in cat_attrs:
        graph.category_attributes.setdefault(cid, set()).add(aid)

    mod_cats = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationCategory.modification_id,
            ).where(SpecialEquipmentModificationCategory.category_id.in_(all_cat_ids))
        )
    ).scalars().all()
    mod_ids = set(mod_cats)

    if mod_ids:
        await _load_category_modifications(session, graph, mod_ids, all_cat_ids)

    # Products directly linked to categories
    direct_prod_cats = (
        await session.execute(
            sa.select(
                SpecialEquipmentProductCategory.product_id,
            ).where(SpecialEquipmentProductCategory.category_id.in_(all_cat_ids))
        )
    ).scalars().all()
    direct_pids = set(direct_prod_cats)
    if direct_pids:
        direct_prods = (
            await session.execute(
                sa.select(SpecialEquipmentProduct).where(
                    SpecialEquipmentProduct.id.in_(direct_pids)
                )
            )
        ).scalars().all()
        for p in direct_prods:
            if p.id not in graph.products:
                graph.add_product(
                    p.id,
                    modification_id=p.modification_id,
                    trim_id=p.trim_id,
                    body_color_id=p.body_color_id,
                    interior_color_id=p.interior_color_id,
                    code=p.code,
                    name=p.vin or p.code,
                )

        all_direct_p_cats = (
            await session.execute(
                sa.select(
                    SpecialEquipmentProductCategory.product_id,
                    SpecialEquipmentProductCategory.category_id,
                ).where(SpecialEquipmentProductCategory.product_id.in_(direct_pids))
            )
        ).all()
        for pid, cid in all_direct_p_cats:
            graph.product_category_ids.setdefault(pid, set()).add(cid)

    await _load_product_neighborhood(session, graph, set(graph.products.keys()))


async def _load_category_modifications(
    session: AsyncSession,
    graph: CascadeGraphSnapshot,
    mod_ids: set[uuid.UUID],
    all_cat_ids: set[uuid.UUID],
) -> None:
    mods = (
        await session.execute(
            sa.select(SpecialEquipmentModification).where(
                SpecialEquipmentModification.id.in_(mod_ids)
            )
        )
    ).scalars().all()
    for m in mods:
        graph.add_modification(
            m.id, model_id=m.model_id, code=m.code, name=m.name
        )

    all_mod_cats = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationCategory.modification_id,
                SpecialEquipmentModificationCategory.category_id,
            ).where(SpecialEquipmentModificationCategory.modification_id.in_(mod_ids))
        )
    ).all()
    surviving_candidate_cats: set[uuid.UUID] = set()
    for mid, cid in all_mod_cats:
        graph.modification_category_ids.setdefault(mid, set()).add(cid)
        if cid not in all_cat_ids:
            surviving_candidate_cats.add(cid)

    if surviving_candidate_cats:
        anc_query = sa.text(
            """
            WITH RECURSIVE anc_tree AS (
                SELECT parent_id, child_id FROM special_equipment_category_relations
                WHERE child_id = ANY(:surviving_ids)
                UNION
                SELECT r.parent_id, r.child_id FROM special_equipment_category_relations r
                JOIN anc_tree a ON r.child_id = a.parent_id
            )
            SELECT parent_id, child_id FROM anc_tree
            """
        )
        anc_rels = (
            await session.execute(
                anc_query, {"surviving_ids": list(surviving_candidate_cats)}
            )
        ).all()
        all_surviving_tree = set(surviving_candidate_cats)
        for pid, cid in anc_rels:
            all_surviving_tree.add(pid)
            graph.category_parent_ids.setdefault(cid, set()).add(pid)

        surv_attrs = (
            await session.execute(
                sa.select(
                    SpecialEquipmentCategoryAttribute.category_id,
                    SpecialEquipmentCategoryAttribute.attribute_id,
                ).where(SpecialEquipmentCategoryAttribute.category_id.in_(all_surviving_tree))
            )
        ).all()
        for cid, aid in surv_attrs:
            graph.category_attributes.setdefault(cid, set()).add(aid)

    mod_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
            ).where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(mod_ids)
            )
        )
    ).all()
    for mid, aid, oid in mod_vals:
        graph.modification_attribute_values.setdefault(mid, {})[aid] = oid

    trims = (
        await session.execute(
            sa.select(SpecialEquipmentTrim).where(
                SpecialEquipmentTrim.modification_id.in_(mod_ids)
            )
        )
    ).scalars().all()
    trim_ids = {t.id for t in trims}
    for t in trims:
        graph.add_trim(
            t.id, modification_id=t.modification_id, code=t.code, name=t.name
        )

    if trim_ids:
        trim_assigns = (
            await session.execute(
                sa.select(
                    SpecialEquipmentTrimAttribute.trim_id,
                    SpecialEquipmentTrimAttribute.attribute_id,
                ).where(SpecialEquipmentTrimAttribute.trim_id.in_(trim_ids))
            )
        ).all()
        for tid, aid in trim_assigns:
            graph.trim_attributes.setdefault(tid, set()).add(aid)

        trim_vals = (
            await session.execute(
                sa.select(
                    SpecialEquipmentTrimAttributeValue.trim_id,
                    SpecialEquipmentTrimAttributeValue.attribute_id,
                    SpecialEquipmentTrimAttributeValue.option_id,
                ).where(SpecialEquipmentTrimAttributeValue.trim_id.in_(trim_ids))
            )
        ).all()
        for tid, aid, oid in trim_vals:
            graph.trim_attribute_values.setdefault(tid, {})[aid] = oid

    prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                SpecialEquipmentProduct.modification_id.in_(mod_ids)
            )
        )
    ).scalars().all()
    for p in prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            body_color_id=p.body_color_id,
            interior_color_id=p.interior_color_id,
            code=p.code,
            name=p.vin or p.code,
        )


async def _load_graph_attribute_groups(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_attribute_group(
        root_id, code=root_ref.code or "", name=root_ref.name or ""
    )
    attrs = (
        await session.execute(
            sa.select(
                SpecialEquipmentAttribute.id,
                SpecialEquipmentAttribute.attribute_group_id,
            ).where(SpecialEquipmentAttribute.attribute_group_id == root_id)
        )
    ).all()
    for aid, gid in attrs:
        graph.attribute_group_ids[aid] = gid

    cat_attrs = (
        await session.execute(
            sa.select(
                SpecialEquipmentCategoryAttribute.category_id,
                SpecialEquipmentCategoryAttribute.attribute_id,
                SpecialEquipmentCategoryAttribute.group_id,
            ).where(SpecialEquipmentCategoryAttribute.group_id == root_id)
        )
    ).all()
    for cid, aid, gid in cat_attrs:
        graph.category_attribute_group_ids[(cid, aid)] = gid

    trim_attrs = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttribute.trim_id,
                SpecialEquipmentTrimAttribute.attribute_id,
                SpecialEquipmentTrimAttribute.group_id,
            ).where(SpecialEquipmentTrimAttribute.group_id == root_id)
        )
    ).all()
    for tid, aid, gid in trim_attrs:
        graph.trim_attribute_group_ids[(tid, aid)] = gid


async def _load_graph_attributes(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_attribute(root_id, code=root_ref.code or "", name=root_ref.name or "")
    opts = (
        await session.execute(
            sa.select(SpecialEquipmentAttributeOption).where(
                SpecialEquipmentAttributeOption.attribute_id == root_id
            )
        )
    ).scalars().all()
    for o in opts:
        graph.add_option(
            o.id, attribute_id=o.attribute_id, code=o.code, name=o.name
        )

    mod_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
            ).where(
                SpecialEquipmentModificationAttributeValue.attribute_id
                == root_id
            )
        )
    ).all()
    for mid, aid, oid in mod_vals:
        graph.modification_attribute_values.setdefault(mid, {})[aid] = oid

    trim_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttributeValue.trim_id,
                SpecialEquipmentTrimAttributeValue.attribute_id,
                SpecialEquipmentTrimAttributeValue.option_id,
            ).where(SpecialEquipmentTrimAttributeValue.attribute_id == root_id)
        )
    ).all()
    for tid, aid, oid in trim_vals:
        graph.trim_attribute_values.setdefault(tid, {})[aid] = oid


async def _load_graph_options(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID
) -> None:
    opt = await session.scalar(
        sa.select(SpecialEquipmentAttributeOption).where(
            SpecialEquipmentAttributeOption.id == root_id
        )
    )
    if opt:
        graph.add_option(
            opt.id,
            attribute_id=opt.attribute_id,
            code=opt.code,
            name=opt.name,
        )

    mod_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentModificationAttributeValue.modification_id,
                SpecialEquipmentModificationAttributeValue.attribute_id,
                SpecialEquipmentModificationAttributeValue.option_id,
            ).where(SpecialEquipmentModificationAttributeValue.option_id == root_id)
        )
    ).all()
    for mid, aid, oid in mod_vals:
        graph.modification_attribute_values.setdefault(mid, {})[aid] = oid

    trim_vals = (
        await session.execute(
            sa.select(
                SpecialEquipmentTrimAttributeValue.trim_id,
                SpecialEquipmentTrimAttributeValue.attribute_id,
                SpecialEquipmentTrimAttributeValue.option_id,
            ).where(SpecialEquipmentTrimAttributeValue.option_id == root_id)
        )
    ).all()
    for tid, aid, oid in trim_vals:
        graph.trim_attribute_values.setdefault(tid, {})[aid] = oid


async def _load_graph_colors(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID, root_ref: EntityRef
) -> None:
    graph.add_color(root_id, code=root_ref.code or "", name=root_ref.name or "")
    prods = (
        await session.execute(
            sa.select(SpecialEquipmentProduct).where(
                sa.or_(
                    SpecialEquipmentProduct.body_color_id == root_id,
                    SpecialEquipmentProduct.interior_color_id == root_id,
                )
            )
        )
    ).scalars().all()
    for p in prods:
        graph.add_product(
            p.id,
            modification_id=p.modification_id,
            trim_id=p.trim_id,
            body_color_id=p.body_color_id,
            interior_color_id=p.interior_color_id,
            code=p.code,
            name=p.vin or p.code,
        )


async def _load_graph_products(
    session: AsyncSession, graph: CascadeGraphSnapshot, root_id: uuid.UUID
) -> None:
    prod = await session.scalar(
        sa.select(SpecialEquipmentProduct).where(
            SpecialEquipmentProduct.id == root_id
        )
    )
    if prod:
        graph.add_product(
            prod.id,
            modification_id=prod.modification_id,
            trim_id=prod.trim_id,
            body_color_id=prod.body_color_id,
            interior_color_id=prod.interior_color_id,
            superstructure_id=prod.superstructure_id,
            superstructure_model_id=prod.superstructure_model_id,
            superstructure_modification_id=prod.superstructure_modification_id,
            superstructure_source_product_id=prod.superstructure_source_product_id,
            code=prod.code,
            name=prod.vin or prod.code,
        )
        await _load_product_neighborhood(session, graph, {root_id})


async def load_cascade_graph(
    session: AsyncSession, root_type: str, root_id: uuid.UUID
) -> tuple[EntityRef, CascadeGraphSnapshot]:
    """Load the required catalog subgraph neighborhood for cascade deletion planning."""
    norm_type = TYPE_TO_DELETE_KEY.get(root_type.lower().replace("-", "_"))
    if not norm_type:
        raise ValueError(f"Неподдерживаемый тип сущности: {root_type}")

    root_ref = await _resolve_root(session, norm_type, root_id)
    graph = CascadeGraphSnapshot()

    loaders = {
        "marks": lambda: _load_graph_marks(session, graph, root_id, root_ref),
        "models": lambda: _load_graph_models(session, graph, root_id, root_ref),
        "modifications": lambda: _load_graph_modifications(session, graph, root_id, root_ref),
        "trims": lambda: _load_graph_trims(session, graph, root_id, root_ref),
        "superstructures": lambda: _load_graph_superstructures(session, graph, root_id, root_ref),
        "categories": lambda: _load_graph_categories(session, graph, root_id),
        "attribute_groups": lambda: _load_graph_attribute_groups(session, graph, root_id, root_ref),
        "attributes": lambda: _load_graph_attributes(session, graph, root_id, root_ref),
        "options": lambda: _load_graph_options(session, graph, root_id),
        "colors": lambda: _load_graph_colors(session, graph, root_id, root_ref),
        "products": lambda: _load_graph_products(session, graph, root_id),
    }

    loader = loaders.get(norm_type)
    if loader is not None:
        await loader()

    return root_ref, graph


async def _load_application_blocker_docs(
    session: AsyncSession,
    product_ids: set[uuid.UUID],
    docs_by_product: dict[uuid.UUID, list[ProductBlockerDocument]],
) -> None:
    # 1. SpecialEquipmentApplicationItem
    app_items = (
        await session.execute(
            sa.select(
                SpecialEquipmentApplicationItem.product_id,
                LeasingApplication.id.label("app_id"),
                LeasingApplication.display_number,
                SpecialEquipmentApplicationItem.item_status,
                LeasingApplication.status.label("app_status"),
            )
            .join(
                LeasingApplication,
                LeasingApplication.id == SpecialEquipmentApplicationItem.application_id,
            )
            .where(SpecialEquipmentApplicationItem.product_id.in_(product_ids))
        )
    ).all()
    for pid, app_id, disp_num, item_status, app_status in app_items:
        docs_by_product.setdefault(pid, []).append(
            ProductBlockerDocument(
                type="application_item",
                id=app_id,
                number=disp_num or str(app_id)[:8],
                status=item_status or app_status or "active",
            )
        )

    # 2. ApplicationVehicle
    app_vehicles = (
        await session.execute(
            sa.select(
                ApplicationVehicle.product_id,
                LeasingApplication.id.label("app_id"),
                LeasingApplication.display_number,
                ApplicationVehicle.car_status,
                LeasingApplication.status.label("app_status"),
            )
            .join(
                LeasingApplication,
                LeasingApplication.id == ApplicationVehicle.application_id,
            )
            .where(
                ApplicationVehicle.product_id.in_(product_ids),
                ApplicationVehicle.product_id.is_not(None),
            )
        )
    ).all()
    for pid, app_id, disp_num, car_status, app_status in app_vehicles:
        if pid is not None and not any(
            d.id == app_id for d in docs_by_product.get(pid, [])
        ):
            docs_by_product.setdefault(pid, []).append(
                ProductBlockerDocument(
                    type="application_vehicle",
                    id=app_id,
                    number=disp_num or str(app_id)[:8],
                    status=car_status or app_status or "active",
                )
            )

    # 3. ApplicationVehicleAllocation
    app_allocs = (
        await session.execute(
            sa.select(
                ApplicationVehicleAllocation.product_id,
                LeasingApplication.id.label("app_id"),
                LeasingApplication.display_number,
                LeasingApplication.status.label("app_status"),
            )
            .join(
                ApplicationVehicle,
                ApplicationVehicle.id
                == ApplicationVehicleAllocation.application_vehicle_id,
            )
            .join(
                LeasingApplication,
                LeasingApplication.id == ApplicationVehicle.application_id,
            )
            .where(ApplicationVehicleAllocation.product_id.in_(product_ids))
        )
    ).all()
    for pid, app_id, disp_num, app_status in app_allocs:
        if not any(d.id == app_id for d in docs_by_product.get(pid, [])):
            docs_by_product.setdefault(pid, []).append(
                ProductBlockerDocument(
                    type="application_vehicle_allocation",
                    id=app_id,
                    number=disp_num or str(app_id)[:8],
                    status=app_status or "reserved",
                )
            )


async def _load_order_and_exchange_blocker_docs(
    session: AsyncSession,
    product_ids: set[uuid.UUID],
    docs_by_product: dict[uuid.UUID, list[ProductBlockerDocument]],
) -> None:
    # 4. SpecialEquipmentPurchaseOrder
    se_orders = (
        await session.execute(
            sa.select(
                SpecialEquipmentPurchaseOrder.product_id,
                SpecialEquipmentPurchaseOrder.id,
                SpecialEquipmentPurchaseOrder.status,
            ).where(SpecialEquipmentPurchaseOrder.product_id.in_(product_ids))
        )
    ).all()
    for pid, order_id, status in se_orders:
        docs_by_product.setdefault(pid, []).append(
            ProductBlockerDocument(
                type="purchase_order",
                id=order_id,
                number=str(order_id)[:8],
                status=status,
            )
        )

    # 5. SpecialEquipmentOrderItem
    se_items = (
        await session.execute(
            sa.select(
                SpecialEquipmentOrderItem.product_id,
                SpecialEquipmentPurchaseOrder.id,
                SpecialEquipmentPurchaseOrder.status,
            )
            .join(
                SpecialEquipmentPurchaseOrder,
                SpecialEquipmentPurchaseOrder.id
                == SpecialEquipmentOrderItem.purchase_order_id,
            )
            .where(SpecialEquipmentOrderItem.product_id.in_(product_ids))
        )
    ).all()
    for pid, order_id, status in se_items:
        if not any(d.id == order_id for d in docs_by_product.get(pid, [])):
            docs_by_product.setdefault(pid, []).append(
                ProductBlockerDocument(
                    type="purchase_order",
                    id=order_id,
                    number=str(order_id)[:8],
                    status=status,
                )
            )

    # 6. PurchaseOrder (legacy)
    legacy_pos = (
        await session.execute(
            sa.select(
                PurchaseOrder.product_id,
                PurchaseOrder.id,
                PurchaseOrder.status,
            ).where(PurchaseOrder.product_id.in_(product_ids))
        )
    ).all()
    for pid, order_id, status in legacy_pos:
        docs_by_product.setdefault(pid, []).append(
            ProductBlockerDocument(
                type="legacy_purchase_order",
                id=order_id,
                number=str(order_id)[:8],
                status=status,
            )
        )

    # 7. ExchangeRequest
    ex_reqs = (
        await session.execute(
            sa.select(
                ExchangeRequest.product_id,
                ExchangeRequest.id,
                ExchangeRequest.status,
                ExchangeRequest.batch_number,
                ExchangeRequest.batch_index,
            ).where(ExchangeRequest.product_id.in_(product_ids))
        )
    ).all()
    for pid, req_id, status, b_num, b_idx in ex_reqs:
        number_str = (
            f"{b_num}-{b_idx}"
            if b_num is not None and b_idx is not None
            else str(req_id)[:8]
        )
        docs_by_product.setdefault(pid, []).append(
            ProductBlockerDocument(
                type="exchange_request",
                id=req_id,
                number=number_str,
                status=status,
            )
        )


async def load_product_blockers(
    session: AsyncSession, product_ids: set[uuid.UUID], lock: bool = False
) -> list[ProductBlocker]:
    """Find any documents referencing candidate products that block deletion."""
    if not product_ids:
        return []

    if lock:
        await session.execute(
            sa.select(SpecialEquipmentProduct.id)
            .where(SpecialEquipmentProduct.id.in_(product_ids))
            .with_for_update()
        )

    docs_by_product: dict[uuid.UUID, list[ProductBlockerDocument]] = {}
    await _load_application_blocker_docs(session, product_ids, docs_by_product)
    await _load_order_and_exchange_blocker_docs(session, product_ids, docs_by_product)

    if not docs_by_product:
        return []

    blocked_pids = set(docs_by_product.keys())
    prods = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.code,
                SpecialEquipmentProduct.vin,
            ).where(SpecialEquipmentProduct.id.in_(blocked_pids))
        )
    ).all()

    result: list[ProductBlocker] = []
    for pid, code, vin in prods:
        p_ref = EntityRef(
            type="product",
            id=pid,
            code=code,
            name=vin or code,
        )
        result.append(
            ProductBlocker(
                product=p_ref,
                documents=docs_by_product[pid],
            )
        )
    return result


async def load_kit_source_blockers(
    session: AsyncSession, candidate_product_ids: set[uuid.UUID], lock: bool = False
) -> list[KitSourceBlocker]:
    """Find kits referencing candidate products as superstructure source that block deletion."""
    if not candidate_product_ids:
        return []

    stmt = (
        sa.select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.code,
            SpecialEquipmentProduct.vin,
            SpecialEquipmentProduct.superstructure_source_product_id,
        ).where(
            SpecialEquipmentProduct.superstructure_source_product_id.in_(candidate_product_ids),
            SpecialEquipmentProduct.id.not_in(candidate_product_ids),
        )
    )
    if lock:
        stmt = stmt.with_for_update()

    kit_rows = (await session.execute(stmt)).all()
    if not kit_rows:
        return []

    kits_by_source: dict[uuid.UUID, list[KitSourceBlockerItem]] = {}
    for kid, kcode, kvin, source_id in kit_rows:
        if source_id is not None:
            kits_by_source.setdefault(source_id, []).append(
                KitSourceBlockerItem(
                    id=kid,
                    code=kcode,
                    title=kvin or kcode,
                )
            )

    source_pids = set(kits_by_source.keys())
    source_rows = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.code,
                SpecialEquipmentProduct.vin,
            ).where(SpecialEquipmentProduct.id.in_(source_pids))
        )
    ).all()

    result: list[KitSourceBlocker] = []
    for spid, scode, svin in source_rows:
        result.append(
            KitSourceBlocker(
                product=KitSourceProductRef(
                    id=spid,
                    code=scode,
                    title=svin or scode,
                ),
                kits=kits_by_source[spid],
            )
        )
    return result


async def load_mark_distributor_blockers(
    session: AsyncSession, mark_id: uuid.UUID, lock: bool = False
) -> list[DistributorBlocker]:
    """Find distributor companies linked to mark preventing its deletion."""
    query = (
        sa.select(Company.id, Company.name, Company.inn)
        .join(DistributorBrand, DistributorBrand.distributor_company_id == Company.id)
        .where(DistributorBrand.brand_id == mark_id)
        .order_by(Company.name, Company.id)
    )
    if lock:
        query = query.with_for_update(read=True)

    rows = (await session.execute(query)).all()
    return [
        DistributorBlocker(
            company={
                "id": row.id,
                "name": row.name,
                "inn": row.inn,
            }
        )
        for row in rows
    ]


def _extract_support_program_refs(
    sp: SupportProgram,
    mark_ids: set[uuid.UUID],
    model_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    marks_map: dict[uuid.UUID, tuple[str, str]],
    models_map: dict[uuid.UUID, tuple[str, str]],
    trims_map: dict[uuid.UUID, tuple[str, str]],
    sp_marks_set: set[uuid.UUID],
) -> list[SupportProgramBlockerReference]:
    refs: list[SupportProgramBlockerReference] = []

    # Mark references
    if sp.mark_id and sp.mark_id in mark_ids:
        m_code, m_name = marks_map.get(sp.mark_id, ("", ""))
        refs.append(
            SupportProgramBlockerReference(
                type="mark",
                id=sp.mark_id,
                code=m_code,
                name=m_name,
            )
        )
    for sp_mark_id in sp_marks_set:
        if not any(r.id == sp_mark_id for r in refs):
            m_code, m_name = marks_map.get(sp_mark_id, ("", ""))
            refs.append(
                SupportProgramBlockerReference(
                    type="mark",
                    id=sp_mark_id,
                    code=m_code,
                    name=m_name,
                )
            )

    # Model references
    if sp.model_id and sp.model_id in model_ids:
        mo_code, mo_name = models_map.get(sp.model_id, ("", ""))
        refs.append(
            SupportProgramBlockerReference(
                type="model",
                id=sp.model_id,
                code=mo_code,
                name=mo_name,
            )
        )
    if sp.model_ids:
        for mid_str in sp.model_ids:
            try:
                mid_uuid = uuid.UUID(mid_str)
            except (ValueError, TypeError):
                continue
            if mid_uuid in model_ids and not any(r.id == mid_uuid for r in refs):
                mo_code, mo_name = models_map.get(mid_uuid, ("", ""))
                refs.append(
                    SupportProgramBlockerReference(
                        type="model",
                        id=mid_uuid,
                        code=mo_code,
                        name=mo_name,
                    )
                )

    # Trim references
    if sp.complectation_ids:
        for tid_str in sp.complectation_ids:
            try:
                tid_uuid = uuid.UUID(tid_str)
            except (ValueError, TypeError):
                continue
            if tid_uuid in trim_ids and not any(r.id == tid_uuid for r in refs):
                t_code, t_name = trims_map.get(tid_uuid, ("", ""))
                refs.append(
                    SupportProgramBlockerReference(
                        type="trim",
                        id=tid_uuid,
                        code=t_code,
                        name=t_name,
                    )
                )

    return refs


async def _load_support_program_target_maps(
    session: AsyncSession,
    mark_ids: set[uuid.UUID],
    model_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    program_ids: list[uuid.UUID],
) -> tuple[
    dict[uuid.UUID, tuple[str, str]],
    dict[uuid.UUID, tuple[str, str]],
    dict[uuid.UUID, tuple[str, str]],
    dict[uuid.UUID, set[uuid.UUID]],
]:
    marks_map: dict[uuid.UUID, tuple[str, str]] = {}
    if mark_ids:
        m_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentMark.id,
                    SpecialEquipmentMark.code,
                    SpecialEquipmentMark.name,
                ).where(SpecialEquipmentMark.id.in_(mark_ids))
            )
        ).all()
        marks_map = {row.id: (row.code, row.name) for row in m_rows}

    models_map: dict[uuid.UUID, tuple[str, str]] = {}
    if model_ids:
        mo_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentModel.id,
                    SpecialEquipmentModel.code,
                    SpecialEquipmentModel.name,
                ).where(SpecialEquipmentModel.id.in_(model_ids))
            )
        ).all()
        models_map = {row.id: (row.code, row.name) for row in mo_rows}

    trims_map: dict[uuid.UUID, tuple[str, str]] = {}
    if trim_ids:
        t_rows = (
            await session.execute(
                sa.select(
                    SpecialEquipmentTrim.id,
                    SpecialEquipmentTrim.code,
                    SpecialEquipmentTrim.name,
                ).where(SpecialEquipmentTrim.id.in_(trim_ids))
            )
        ).all()
        trims_map = {row.id: (row.code, row.name) for row in t_rows}

    sp_marks_map: dict[uuid.UUID, set[uuid.UUID]] = {}
    if mark_ids and program_ids:
        sp_mark_rows = (
            await session.execute(
                sa.select(
                    SupportProgramMark.support_program_id,
                    SupportProgramMark.mark_id,
                ).where(
                    SupportProgramMark.support_program_id.in_(program_ids),
                    SupportProgramMark.mark_id.in_(mark_ids),
                )
            )
        ).all()
        for row in sp_mark_rows:
            sp_marks_map.setdefault(row.support_program_id, set()).add(row.mark_id)

    return marks_map, models_map, trims_map, sp_marks_map


async def load_support_program_blockers(
    session: AsyncSession,
    mark_ids: set[uuid.UUID],
    model_ids: set[uuid.UUID],
    trim_ids: set[uuid.UUID],
    lock: bool = False,
) -> list[SupportProgramBlocker]:
    """Find any support programs referencing marks, models, or trims slated for deletion."""
    if not (mark_ids or model_ids or trim_ids):
        return []

    conditions: list[Any] = []
    if mark_ids:
        conditions.append(SupportProgram.mark_id.in_(mark_ids))
        conditions.append(
            SupportProgram.id.in_(
                sa.select(SupportProgramMark.support_program_id).where(
                    SupportProgramMark.mark_id.in_(mark_ids)
                )
            )
        )
    if model_ids:
        conditions.append(SupportProgram.model_id.in_(model_ids))
        conditions.append(
            SupportProgram.model_ids.overlap([str(m) for m in model_ids])
        )
    if trim_ids:
        conditions.append(
            SupportProgram.complectation_ids.overlap([str(t) for t in trim_ids])
        )

    query = (
        sa.select(SupportProgram)
        .where(sa.or_(*conditions))
        .order_by(SupportProgram.name, SupportProgram.id)
    )
    if lock:
        query = query.with_for_update(read=True)

    programs = (await session.execute(query)).scalars().all()
    if not programs:
        return []

    program_ids = [p.id for p in programs]
    marks_map, models_map, trims_map, sp_marks_map = (
        await _load_support_program_target_maps(
            session, mark_ids, model_ids, trim_ids, program_ids
        )
    )

    blockers: list[SupportProgramBlocker] = []
    for sp in programs:
        refs = _extract_support_program_refs(
            sp,
            mark_ids,
            model_ids,
            trim_ids,
            marks_map,
            models_map,
            trims_map,
            sp_marks_map.get(sp.id, set()),
        )
        if refs:
            blockers.append(
                SupportProgramBlocker(
                    program={
                        "id": sp.id,
                        "name": sp.name,
                        "is_active": sp.is_active,
                        "starts_at": sp.starts_at.isoformat() if sp.starts_at else None,
                        "ends_at": sp.ends_at.isoformat() if sp.ends_at else None,
                    },
                    references=refs,
                )
            )

    return blockers


async def _clear_fields(session: AsyncSession, plan: CascadePlan) -> None:
    # Colors
    color_ids = {c.id for c in plan.delete.get("colors", [])}
    if color_ids:
        await session.execute(
            sa.update(SpecialEquipmentProduct)
            .where(SpecialEquipmentProduct.body_color_id.in_(color_ids))
            .values(body_color_id=None)
        )
        await session.execute(
            sa.update(SpecialEquipmentProduct)
            .where(SpecialEquipmentProduct.interior_color_id.in_(color_ids))
            .values(interior_color_id=None)
        )

    # Trims cleared from surviving products
    trim_ids = {t.id for t in plan.delete.get("trims", [])}
    if trim_ids:
        await session.execute(
            sa.update(SpecialEquipmentProduct)
            .where(SpecialEquipmentProduct.trim_id.in_(trim_ids))
            .values(trim_id=None)
        )

    # Attribute groups cleared
    group_ids = {g.id for g in plan.delete.get("attribute_groups", [])}
    if group_ids:
        await session.execute(
            sa.update(SpecialEquipmentAttribute)
            .where(SpecialEquipmentAttribute.attribute_group_id.in_(group_ids))
            .values(attribute_group_id=None)
        )
        await session.execute(
            sa.update(SpecialEquipmentCategoryAttribute)
            .where(SpecialEquipmentCategoryAttribute.group_id.in_(group_ids))
            .values(group_id=None)
        )
        await session.execute(
            sa.update(SpecialEquipmentTrimAttribute)
            .where(SpecialEquipmentTrimAttribute.group_id.in_(group_ids))
            .values(group_id=None)
        )

    # Explicitly clear selected warehouse categories before removing the directory rows.
    category_ids = {c.id for c in plan.delete.get("categories", [])}
    if category_ids:
        await session.execute(
            sa.update(Warehouse).where(Warehouse.category_id.in_(category_ids)).values(category_id=None)
        )

    # Marks unlinked from warehouses
    mark_ids = {m.id for m in plan.delete.get("marks", [])}
    if mark_ids:
        await session.execute(
            sa.delete(WarehouseMark)
            .where(WarehouseMark.mark_id.in_(mark_ids))
        )
        await session.execute(
            sa.update(WarehouseAccessRule)
            .where(WarehouseAccessRule.brand_id.in_(mark_ids))
            .values(brand_id=None)
        )


async def _purge_products(
    session: AsyncSession,
    product_ids: set[uuid.UUID],
    media_storage_keys: set[str],
) -> None:
    if not product_ids:
        return

    # Carts
    cart_item_ids = set(
        (
            await session.execute(
                sa.select(SpecialEquipmentCartItem.id).where(
                    SpecialEquipmentCartItem.product_id.in_(product_ids)
                )
            )
        ).scalars().all()
    )
    if cart_item_ids:
        await session.execute(
            sa.update(SpecialEquipmentCartItem)
            .where(SpecialEquipmentCartItem.parent_item_id.in_(cart_item_ids))
            .values(parent_item_id=None)
        )
        await session.execute(
            sa.delete(SpecialEquipmentCartItem).where(
                SpecialEquipmentCartItem.id.in_(cart_item_ids)
            )
        )
    await session.execute(
        sa.delete(SpecialEquipmentCartItem).where(
            SpecialEquipmentCartItem.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(ExchangeCartItem).where(
            ExchangeCartItem.product_id.in_(product_ids)
        )
    )

    # Favorites
    await session.execute(
        sa.delete(SpecialEquipmentFavorite).where(
            SpecialEquipmentFavorite.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(UserFavorite).where(UserFavorite.product_id.in_(product_ids))
    )

    # Attachments & Components
    await session.execute(
        sa.delete(SpecialEquipmentProductAttachment).where(
            sa.or_(
                SpecialEquipmentProductAttachment.product_id.in_(product_ids),
                SpecialEquipmentProductAttachment.attachment_product_id.in_(
                    product_ids
                ),
            )
        )
    )

    # Images & Media collection
    img_keys = (
        await session.execute(
            sa.select(SpecialEquipmentProductImage.storage_key).where(
                SpecialEquipmentProductImage.product_id.in_(product_ids)
            )
        )
    ).scalars().all()
    media_storage_keys.update(img_keys)

    await session.execute(
        sa.delete(SpecialEquipmentProductCategory).where(
            SpecialEquipmentProductCategory.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(SpecialEquipmentProductImage).where(
            SpecialEquipmentProductImage.product_id.in_(product_ids)
        )
    )
    await session.execute(
        sa.delete(VehicleWarehouseTransfer).where(
            VehicleWarehouseTransfer.product_id.in_(product_ids)
        )
    )

    # Products
    await session.execute(
        sa.delete(SpecialEquipmentProduct).where(
            SpecialEquipmentProduct.id.in_(product_ids)
        )
    )


async def _prune_surviving_modification_attributes(
    session: AsyncSession,
) -> None:
    surviving_mods = (
        await session.execute(
            sa.select(SpecialEquipmentModificationCategory.modification_id)
            .distinct()
        )
    ).scalars().all()
    for sm_id in surviving_mods:
        remaining_cats = set(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentModificationCategory.category_id
                    ).where(
                        SpecialEquipmentModificationCategory.modification_id
                        == sm_id
                    )
                )
            ).scalars().all()
        )
        if not remaining_cats:
            continue

        anc_query = sa.text(
            """
            WITH RECURSIVE cat_anc AS (
                SELECT parent_id, child_id FROM special_equipment_category_relations
                WHERE child_id = ANY(:rem_cats)
                UNION
                SELECT r.parent_id, r.child_id FROM special_equipment_category_relations r
                JOIN cat_anc a ON r.child_id = a.parent_id
            )
            SELECT parent_id FROM cat_anc
            """
        )
        anc_cats = set(
            (
                await session.execute(
                    anc_query, {"rem_cats": list(remaining_cats)}
                )
            ).scalars().all()
        )
        effective_cats = remaining_cats | anc_cats

        allowed_attrs = set(
            (
                await session.execute(
                    sa.select(
                        SpecialEquipmentCategoryAttribute.attribute_id
                    ).where(
                        SpecialEquipmentCategoryAttribute.category_id.in_(
                            effective_cats
                        )
                    )
                )
            ).scalars().all()
        )

        await session.execute(
            sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.modification_id
                == sm_id,
                SpecialEquipmentModificationAttributeValue.attribute_id.not_in(
                    allowed_attrs
                ),
            )
        )

        sm_trims = (
            await session.execute(
                sa.select(SpecialEquipmentTrim.id).where(
                    SpecialEquipmentTrim.modification_id == sm_id
                )
            )
        ).scalars().all()
        if sm_trims:
            await session.execute(
                sa.delete(SpecialEquipmentTrimAttributeValue).where(
                    SpecialEquipmentTrimAttributeValue.trim_id.in_(sm_trims),
                    SpecialEquipmentTrimAttributeValue.attribute_id.not_in(
                        allowed_attrs
                    ),
                )
            )
            await session.execute(
                sa.delete(SpecialEquipmentTrimAttribute).where(
                    SpecialEquipmentTrimAttribute.trim_id.in_(sm_trims),
                    SpecialEquipmentTrimAttribute.attribute_id.not_in(
                        allowed_attrs
                    ),
                )
            )


async def _purge_hierarchy(
    session: AsyncSession, plan: CascadePlan, media_storage_keys: set[str]
) -> None:
    # Trims
    trim_ids = {t.id for t in plan.delete.get("trims", [])}
    if trim_ids:
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttributeValue).where(
                SpecialEquipmentTrimAttributeValue.trim_id.in_(trim_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttribute).where(
                SpecialEquipmentTrimAttribute.trim_id.in_(trim_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrim).where(SpecialEquipmentTrim.id.in_(trim_ids))
        )

    # Superstructures
    superstructure_ids = {s.id for s in plan.delete.get("superstructures", [])}
    if superstructure_ids:
        await session.execute(
            sa.delete(SpecialEquipmentSuperstructureAttribute).where(
                SpecialEquipmentSuperstructureAttribute.superstructure_id.in_(
                    superstructure_ids
                )
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentSuperstructure).where(
                SpecialEquipmentSuperstructure.id.in_(superstructure_ids)
            )
        )

    # Modifications
    mod_ids = {m.id for m in plan.delete.get("modifications", [])}
    if mod_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.modification_id.in_(mod_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentModificationCategory).where(
                SpecialEquipmentModificationCategory.modification_id.in_(mod_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentModification).where(
                SpecialEquipmentModification.id.in_(mod_ids)
            )
        )

    # Models
    model_ids = {m.id for m in plan.delete.get("models", [])}
    if model_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModel).where(
                SpecialEquipmentModel.id.in_(model_ids)
            )
        )

    # Marks
    mark_ids = {m.id for m in plan.delete.get("marks", [])}
    if mark_ids:
        await session.execute(
            sa.delete(SpecialEquipmentMark).where(SpecialEquipmentMark.id.in_(mark_ids))
        )

    # Categories
    category_ids = {c.id for c in plan.delete.get("categories", [])}
    if category_ids:
        cat_img_keys = (
            await session.execute(
                sa.select(SpecialEquipmentCategory.image_key).where(
                    SpecialEquipmentCategory.id.in_(category_ids),
                    SpecialEquipmentCategory.image_key.is_not(None),
                )
            )
        ).scalars().all()
        media_storage_keys.update(k for k in cat_img_keys if k)

        await session.execute(
            sa.delete(SpecialEquipmentModificationCategory).where(
                SpecialEquipmentModificationCategory.category_id.in_(category_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentProductCategory).where(
                SpecialEquipmentProductCategory.category_id.in_(category_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCategoryAttribute).where(
                SpecialEquipmentCategoryAttribute.category_id.in_(category_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCategoryRelation).where(
                sa.or_(
                    SpecialEquipmentCategoryRelation.parent_id.in_(category_ids),
                    SpecialEquipmentCategoryRelation.child_id.in_(category_ids),
                )
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCategory).where(
                SpecialEquipmentCategory.id.in_(category_ids)
            )
        )
        await _prune_surviving_modification_attributes(session)


async def _purge_attributes_and_dictionaries(
    session: AsyncSession, plan: CascadePlan
) -> None:
    option_ids = {o.id for o in plan.delete.get("options", [])}
    if option_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.option_id.in_(option_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttributeValue).where(
                SpecialEquipmentTrimAttributeValue.option_id.in_(option_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentAttributeOption).where(
                SpecialEquipmentAttributeOption.id.in_(option_ids)
            )
        )

    attribute_ids = {a.id for a in plan.delete.get("attributes", [])}
    if attribute_ids:
        await session.execute(
            sa.delete(SpecialEquipmentModificationAttributeValue).where(
                SpecialEquipmentModificationAttributeValue.attribute_id.in_(
                    attribute_ids
                )
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttributeValue).where(
                SpecialEquipmentTrimAttributeValue.attribute_id.in_(attribute_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentTrimAttribute).where(
                SpecialEquipmentTrimAttribute.attribute_id.in_(attribute_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCategoryAttribute).where(
                SpecialEquipmentCategoryAttribute.attribute_id.in_(attribute_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentAttributeOption).where(
                SpecialEquipmentAttributeOption.attribute_id.in_(attribute_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentAttribute).where(
                SpecialEquipmentAttribute.id.in_(attribute_ids)
            )
        )

    group_ids = {g.id for g in plan.delete.get("attribute_groups", [])}
    if group_ids:
        await session.execute(
            sa.delete(SpecialEquipmentAttributeGroup).where(
                SpecialEquipmentAttributeGroup.id.in_(group_ids)
            )
        )

    color_ids = {c.id for c in plan.delete.get("colors", [])}
    if color_ids:
        await session.execute(
            sa.delete(SpecialEquipmentColor).where(
                SpecialEquipmentColor.id.in_(color_ids)
            )
        )


async def apply_cascade_plan(
    session: AsyncSession,
    plan: CascadePlan,
    user_id: uuid.UUID | None,
    catalog_revision: int,
) -> dict[str, int]:
    """Execute cascade deletion plan in strict topological order."""
    _ = catalog_revision
    media_storage_keys_to_enqueue: set[str] = set()

    # 1. Field clears
    await _clear_fields(session, plan)

    # 2. Products and commerce dependencies
    product_ids = {p.id for p in plan.delete.get("products", [])}
    await _purge_products(session, product_ids, media_storage_keys_to_enqueue)

    # 3. Hierarchy: trims, modifications, models, marks, categories
    await _purge_hierarchy(session, plan, media_storage_keys_to_enqueue)

    # 4. Attributes, groups, colors
    await _purge_attributes_and_dictionaries(session, plan)

    # 5. External refs and mutation receipts
    all_deleted_ids: set[uuid.UUID] = {
        item.id
        for group in plan.delete.values()
        for item in group
    }
    if all_deleted_ids:
        await session.execute(
            sa.delete(SpecialEquipmentExternalRef).where(
                SpecialEquipmentExternalRef.entity_id.in_(all_deleted_ids)
            )
        )
        await session.execute(
            sa.delete(SpecialEquipmentCatalogMutationReceipt).where(
                SpecialEquipmentCatalogMutationReceipt.resource_id.in_(
                    all_deleted_ids
                )
            )
        )

    # 6. Enqueue collected media keys
    for sk in media_storage_keys_to_enqueue:
        await enqueue_media_cleanup(session, sk)

    # 7. Revision increment
    new_revision = await increment_catalog_revision(session)

    # 8. Write to deletion log
    log_items: list[dict[str, Any]] = [
        {
            "type": it.type,
            "id": str(it.id),
            "code": it.code,
            "name": it.name,
            "action": "delete",
        }
        for items in plan.delete.values()
        for it in items
    ]
    log_items.extend(
        {
            "type": u.type,
            "count": u.count,
            "description": u.description,
            "action": "unlink",
        }
        for u in plan.unlink
    )
    log_items.extend(
        {
            "type": c.type,
            "field": c.field,
            "count": c.count,
            "description": c.description,
            "action": "clear",
        }
        for c in plan.clear
    )
    if plan.attribute_values_to_delete_count > 0:
        log_items.append(
            {
                "type": "attribute_value",
                "count": plan.attribute_values_to_delete_count,
                "action": "delete",
            }
        )

    deletion_log = SpecialEquipmentCatalogDeletionLog(
        user_id=user_id,
        root_type=plan.root.type,
        root_id=plan.root.id,
        root_code=plan.root.code,
        root_name=plan.root.name,
        catalog_revision=new_revision,
        counts=plan.counts,
        items=log_items,
    )
    session.add(deletion_log)
    await session.flush()

    return plan.counts
