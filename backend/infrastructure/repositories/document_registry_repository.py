"""Registry persistence, locking, scoped predicates and batch projections."""
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.document_registry import ROLES, TYPES, normalize_number, status
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.document_registry import (
    document_group_participants as participants,
)
from infrastructure.models.document_registry import (
    document_groups as groups,
)
from infrastructure.models.document_registry import (
    reference_document_files as files,
)
from infrastructure.models.document_registry import (
    reference_document_monetization_programs as links,
)
from infrastructure.models.document_registry import (
    reference_document_related_companies as related,
)
from infrastructure.models.document_registry import (
    reference_document_version_related_companies as version_related,
)
from infrastructure.models.document_registry import (
    reference_document_versions as versions,
)
from infrastructure.models.document_registry import (
    reference_documents as documents,
)
from infrastructure.models.monetization import programs
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
)
from infrastructure.models.users import User
from infrastructure.repositories import exchange_access_repository


async def resolve_actor(session: AsyncSession, user_id: UUID, role: str, company_id: UUID | None) -> dict[str, Any] | None:
    current_role = await exchange_access_repository.get_actor_role(session, user_id)
    if current_role != role or role not in (*ROLES, "carcraft_employee"):
        return None
    actor = {"user_id": user_id, "role": role, "company_id": company_id, "company_ids": [], "can_write": role == "carcraft_employee"}
    if role == "carcraft_employee":
        return actor
    memberships = await exchange_access_repository.get_actor_companies(session, user_id, role)
    if company_id not in [item["id"] for item in memberships]:
        return None
    actor["company_ids"] = [company_id]
    return actor


def access(actor: dict[str, Any]) -> Any:
    if actor["role"] == "carcraft_employee":
        return sa.true()
    company_ids = actor.get("company_ids", [])
    return sa.or_(
        sa.exists(sa.select(1).where(participants.c.group_id == documents.c.group_id,
            participants.c.role == actor["role"], participants.c.company_id.in_(company_ids))),
        sa.exists(sa.select(1).where(related.c.document_id == documents.c.id,
            related.c.role == actor["role"], related.c.company_id.in_(company_ids))))


def _live(actor: dict[str, Any]) -> Any:
    return sa.and_(documents.c.deleted_at.is_(None), access(actor))


async def lookup_companies(session: AsyncSession, role: str, search: str) -> list[dict[str, Any]]:
    stmt = sa.select(Company.id.label("company_id"), Company.name, Company.inn)
    if role == "leasing_company":
        stmt = stmt.add_columns(LeasingCompany.id.label("leasing_company_id")).join(LeasingCompany, LeasingCompany.company_id == Company.id).where(LeasingCompany.is_active.is_(True))
    else:
        stmt = stmt.add_columns(sa.literal(None).label("leasing_company_id"))
    stmt = stmt.where(Company.company_type == role, Company.is_active.is_(True))
    if search.strip():
        text = f"%{search.strip()}%"
        stmt = stmt.where(sa.or_(Company.name.ilike(text), Company.inn.ilike(text)))
    return [dict(row, role=role) for row in (await session.execute(stmt.order_by(Company.name, Company.id).limit(100))).mappings()]


async def lookup_catalog(session: AsyncSession, fields: str, mark_id: UUID | None) -> list[dict[str, Any]]:
    stmt: Any
    if fields == "marks":
        stmt = sa.select(SpecialEquipmentMark.id, SpecialEquipmentMark.name).where(SpecialEquipmentMark.is_active.is_(True)).order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
    else:
        stmt = sa.select(SpecialEquipmentModel.id, SpecialEquipmentModel.name, SpecialEquipmentModel.mark_id).where(SpecialEquipmentModel.is_active.is_(True), SpecialEquipmentModel.mark_id == mark_id).order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
    return [dict(row) for row in (await session.execute(stmt)).mappings()]


async def resolve_companies(session: AsyncSession, payload: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for role in ROLES:
        key = "leasing_company_ids" if role == "leasing_company" else f"{role}_company_ids"
        identifiers = set(payload.get(key) or [])
        if not identifiers:
            continue
        if role == "leasing_company":
            stmt = sa.select(Company.id).join(LeasingCompany, LeasingCompany.company_id == Company.id).where(LeasingCompany.id.in_(identifiers), LeasingCompany.is_active.is_(True), Company.is_active.is_(True), Company.company_type == role)
            valid = set((await session.scalars(sa.select(LeasingCompany.id).join(Company, Company.id == LeasingCompany.company_id).where(LeasingCompany.id.in_(identifiers), LeasingCompany.is_active.is_(True), Company.is_active.is_(True), Company.company_type == role))).all())
        else:
            stmt = sa.select(Company.id).where(Company.id.in_(identifiers), Company.company_type == role, Company.is_active.is_(True))
            valid = set((await session.scalars(stmt)).all())
        if valid != identifiers:
            raise ValueError("Компания не зарегистрирована, неактивна или имеет другую роль; ЛК должна быть связана с юрлицом")
        company_ids = set((await session.scalars(stmt)).all())
        result.extend({"role": role, "company_id": company_id} for company_id in sorted(company_ids))
    return result


async def resolve_version_companies(session: AsyncSession, payload: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    """Preserve existing historical assignments; validate only newly added ones."""
    additions = {}
    for role in ROLES:
        key = "leasing_company_ids" if role == "leasing_company" else f"{role}_company_ids"
        additions[key] = list(set(payload[key]) - set(current[key]))
    rows = await resolve_companies(session, additions)
    for company in current["companies"]:
        role = company["role"]
        key = "leasing_company_ids" if role == "leasing_company" else f"{role}_company_ids"
        identifier = company["leasing_company_id"] if role == "leasing_company" else company["company_id"]
        if identifier in payload[key]:
            rows.append({"role": role, "company_id": company["company_id"]})
    return [{"role": role, "company_id": company_id} for role, company_id in sorted({(row["role"], row["company_id"]) for row in rows})]


async def validate_catalog(session: AsyncSession, mark_id: UUID | None, model_id: UUID | None) -> None:
    if model_id and not mark_id:
        raise ValueError("Для модели требуется марка")
    if mark_id and not await session.scalar(sa.select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.id == mark_id, SpecialEquipmentMark.is_active.is_(True))):
        raise ValueError("Марка не найдена или неактивна")
    if model_id and not await session.scalar(sa.select(SpecialEquipmentModel.id).where(SpecialEquipmentModel.id == model_id, SpecialEquipmentModel.mark_id == mark_id, SpecialEquipmentModel.is_active.is_(True))):
        raise ValueError("Модель не принадлежит выбранной марке или неактивна")


async def number_available(session: AsyncSession, number: str) -> bool:
    return not bool(await session.scalar(sa.select(documents.c.id).where(documents.c.contract_number_normalized == normalize_number(number), documents.c.deleted_at.is_(None)).limit(1)))


async def _company_projection(session: AsyncSession, table: sa.Table, owner_column: str, ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    result: dict[UUID, dict[str, Any]] = {identifier: {"leasing_company_ids": [], "dealer_company_ids": [], "distributor_company_ids": [], "companies": []} for identifier in ids}
    stmt = sa.select(table.c[owner_column].label("owner_id"), table.c.role, Company.id.label("company_id"), Company.name, Company.inn, LeasingCompany.id.label("leasing_company_id")).join(Company, Company.id == table.c.company_id).outerjoin(LeasingCompany, sa.and_(LeasingCompany.company_id == Company.id, table.c.role == "leasing_company")).where(table.c[owner_column].in_(ids)).order_by(table.c.role, Company.name, Company.id, LeasingCompany.id)
    for row in (await session.execute(stmt)).mappings():
        item = dict(row)
        target = result[item.pop("owner_id")]
        role = item["role"]
        if role == "leasing_company":
            if item["leasing_company_id"]:
                target["leasing_company_ids"].append(item["leasing_company_id"])
        else:
            target[f"{role}_company_ids"].append(item["company_id"])
        target["companies"].append(item)
    return result


async def group_projection(session: AsyncSession, group_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    company_map = await _company_projection(session, participants, "group_id", group_ids)
    stmt = sa.select(groups, SpecialEquipmentMark.name.label("mark_name"), SpecialEquipmentModel.name.label("model_name")).outerjoin(SpecialEquipmentMark, SpecialEquipmentMark.id == groups.c.mark_id).outerjoin(SpecialEquipmentModel, SpecialEquipmentModel.id == groups.c.model_id).where(groups.c.id.in_(group_ids))
    result = {}
    for row in (await session.execute(stmt)).mappings():
        result[row["id"]] = {**company_map[row["id"]], "platform_ml": row["platform_ml_participates"], "mark_id": row["mark_id"], "model_id": row["model_id"], "mark_name": row["mark_name"], "model_name": row["model_name"]}
    return result


async def version_projection(session: AsyncSession, document_ids: list[UUID]) -> dict[UUID, list[dict[str, Any]]]:
    rows = (await session.execute(sa.select(versions, User.name.label("author_name")).join(User, User.id == versions.c.uploaded_by).where(versions.c.document_id.in_(document_ids)).order_by(versions.c.version_number.desc()))).mappings().all()
    company_map = await _company_projection(session, version_related, "version_id", [row["id"] for row in rows])
    file_map: dict[UUID, list[dict[str, Any]]] = {}
    file_rows = (await session.execute(sa.select(files).where(files.c.version_id.in_([row["id"] for row in rows])).order_by(files.c.position))).mappings()
    for row in file_rows:
        file_map.setdefault(row["version_id"], []).append({"id": row["id"], "name": row["file_name"], "type": row["content_type"], "size": row["file_size"], "download_url": f"/api/v1/document-registry/files/{row['id']}/download"})
    result: dict[UUID, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row["document_id"], []).append({"id": row["id"], "version_number": row["version_number"], "name": row["name"], "related_companies": {**company_map[row["id"]], "platform_ml": row["platform_ml_related"]}, "metadata_backfilled": row["metadata_backfilled"], "valid_from": row["valid_from"], "valid_to": row["valid_to"], "uploaded_by": {"id": row["uploaded_by"], "display_name": row["author_name"] or "Пользователь"}, "uploaded_at": row["created_at"], "files": file_map.get(row["id"], []), "is_current": row["is_current"]})
    return result


async def project_documents(session: AsyncSession, rows: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    ids = [row["id"] for row in rows]
    company_map = await _company_projection(session, related, "document_id", ids)
    history = await version_projection(session, ids)
    result = []
    for row in rows:
        current = next((version for version in history.get(row["id"], []) if version["is_current"]), None)
        if current is None:
            continue
        result.append({"id": row["id"], "group_id": row["group_id"], "is_main": row["is_main"], "document_type": row["document_type"], "contract_number": row["contract_number"], "name": row["name"], "related_companies": {**company_map[row["id"]], "platform_ml": row["platform_ml_related"]}, "active": row["deactivated_at"] is None, "status": status(current["valid_from"], current["valid_to"], row["deactivated_at"] is not None, today), "current_version": current, "version_count": len(history[row["id"]])})
    return result


async def get_document(session: AsyncSession, document_id: UUID, actor: dict[str, Any], *, today: date | None = None) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(documents).where(documents.c.id == document_id, _live(actor)))).mappings().first()
    if row is None:
        return None
    if today is None:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
    return (await project_documents(session, [dict(row)], today))[0]


async def get_group_documents(session: AsyncSession, group_id: UUID, actor: dict[str, Any], today: date) -> list[dict[str, Any]]:
    rows = (await session.execute(sa.select(documents).where(documents.c.group_id == group_id, _live(actor)).order_by(documents.c.is_main.desc(), documents.c.created_at, documents.c.id))).mappings().all()
    return await project_documents(session, [dict(row) for row in rows], today)


def _status_expression(today: date) -> Any:
    from datetime import timedelta
    return sa.case((documents.c.deactivated_at.is_not(None), "deactivated"), (versions.c.valid_from > today, "pending"), (versions.c.valid_to < today, "expired"), (versions.c.valid_to <= today + timedelta(days=30), "expiring"), else_="active")


def _group_query(actor: dict[str, Any], filters: dict[str, Any], today: date) -> Any:
    base = sa.select(1).select_from(documents.join(versions, sa.and_(versions.c.document_id == documents.c.id, versions.c.is_current.is_(True)))).where(documents.c.group_id == groups.c.id, _live(actor)).correlate(groups)
    stmt = sa.select(groups).where(sa.exists(base))
    for field in ("mark_id", "model_id"):
        if filters.get(field):
            stmt = stmt.where(groups.c[field] == filters[field])
    if filters.get("document_type"):
        stmt = stmt.where(sa.exists(base.where(documents.c.document_type == filters["document_type"])))
    if filters.get("status"):
        stmt = stmt.where(sa.exists(base.where(_status_expression(today) == filters["status"])))
    period = []
    if filters.get("valid_from"):
        period.append(versions.c.valid_from >= filters["valid_from"])
    if filters.get("valid_to"):
        period.append(versions.c.valid_to <= filters["valid_to"])
    if period:
        stmt = stmt.where(sa.exists(base.where(*period)))
    search = (filters.get("search") or "").strip()
    if search:
        stmt = stmt.where(sa.exists(base.where(sa.or_(documents.c.name.icontains(search, autoescape=True), documents.c.contract_number_normalized.contains(normalize_number(search), autoescape=True)))))
    return _company_filters(stmt, base, filters)


def _company_filters(stmt: Any, base: Any, filters: dict[str, Any]) -> Any:
    for role in ROLES:
        field = "leasing_company_id" if role == "leasing_company" else f"{role}_company_id"
        if not filters.get(field):
            continue
        company_id = filters[field]
        if role == "leasing_company":
            company_id = sa.select(LeasingCompany.company_id).where(LeasingCompany.id == company_id).scalar_subquery()
        if filters.get("participant_scope") == "related":
            predicate = sa.exists(sa.select(1).where(related.c.document_id == documents.c.id, related.c.role == role, related.c.company_id == company_id))
            stmt = stmt.where(sa.exists(base.where(predicate)))
        else:
            stmt = stmt.where(sa.exists(sa.select(1).where(participants.c.group_id == groups.c.id, participants.c.role == role, participants.c.company_id == company_id)))
    return stmt


async def list_groups(session: AsyncSession, actor: dict[str, Any], filters: dict[str, Any], today: date, *, offset: int = 0, limit: int | None = 20, cursor: tuple[datetime, UUID] | None = None) -> tuple[list[dict[str, Any]], int]:
    stmt = _group_query(actor, filters, today)
    total = int(await session.scalar(sa.select(sa.func.count()).select_from(stmt.subquery())) or 0)
    if cursor:
        stmt = stmt.where(sa.tuple_(groups.c.created_at, groups.c.id) < cursor)
    stmt = stmt.order_by(groups.c.created_at.desc(), groups.c.id.desc()).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    raw_groups = (await session.execute(stmt)).mappings().all()
    ids = [row["id"] for row in raw_groups]
    group_map = await group_projection(session, ids)
    raw_documents = (await session.execute(sa.select(documents).where(documents.c.group_id.in_(ids), _live(actor)).order_by(documents.c.is_main.desc(), documents.c.created_at, documents.c.id))).mappings().all()
    projected = await project_documents(session, [dict(row) for row in raw_documents], today)
    result = []
    for row in raw_groups:
        accessible = [document for document in projected if document["group_id"] == row["id"]]
        if not accessible:
            continue
        main = next((document for document in accessible if document["is_main"]), None)
        result.append({"group_id": row["id"], "participants": group_map[row["id"]], "main_document": main, "display_document": main or accessible[0], "children_count": sum(not document["is_main"] for document in accessible), "documents_count": len(accessible), "counts_by_type": {code: sum(document["document_type"] == code for document in accessible) for code in TYPES}, "can_manage": actor["role"] == "carcraft_employee", "documents": accessible, "created_at": row["created_at"]})
    return result, total


async def candidate_groups(session: AsyncSession, actor: dict[str, Any], context: dict[str, Any], today: date) -> list[dict[str, Any]]:
    from domain.document_registry import matches_context
    lc_exists = await session.scalar(sa.select(LeasingCompany.id).where(LeasingCompany.id == context["leasing_company_id"], LeasingCompany.company_id.is_not(None), LeasingCompany.is_active.is_(True)))
    if not lc_exists:
        raise ValueError("Лизинговая компания не найдена или не связана с юрлицом")
    await validate_catalog(session, context.get("mark_id"), context.get("model_id"))
    rows, _ = await list_groups(session, actor, {}, today, limit=None)
    return [group for group in rows if matches_context(group["participants"], context)]


async def lock_group(session: AsyncSession, group_id: UUID) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(groups).where(groups.c.id == group_id).with_for_update())).mappings().first()
    return dict(row) if row else None


async def lock_documents(session: AsyncSession, document_ids: list[UUID]) -> list[dict[str, Any]]:
    if not document_ids:
        return []
    group_ids = (await session.scalars(sa.select(documents.c.group_id).where(documents.c.id.in_(document_ids)).distinct().order_by(documents.c.group_id))).all()
    for group_id in group_ids:
        await lock_group(session, group_id)
    rows = (await session.execute(sa.select(documents).where(documents.c.id.in_(document_ids), documents.c.deleted_at.is_(None)).order_by(documents.c.id).with_for_update())).mappings()
    return [dict(row) for row in rows]


async def create_group(session: AsyncSession, payload: dict[str, Any], company_rows: list[dict[str, Any]], actor_id: UUID) -> UUID:
    group_id = uuid4()
    await session.execute(groups.insert().values(id=group_id, platform_ml_participates=payload.get("platform_ml", False), mark_id=payload.get("mark_id"), model_id=payload.get("model_id"), created_by=actor_id))
    if company_rows:
        await session.execute(participants.insert(), [{"id": uuid4(), "group_id": group_id, **row} for row in company_rows])
    return group_id


async def set_related(session: AsyncSession, document_id: UUID, company_rows: list[dict[str, Any]]) -> None:
    await session.execute(related.delete().where(related.c.document_id == document_id))
    if company_rows:
        await session.execute(related.insert(), [{"id": uuid4(), "document_id": document_id, **row} for row in company_rows])


async def insert_document(session: AsyncSession, values: dict[str, Any], company_rows: list[dict[str, Any]]) -> None:
    await session.execute(documents.insert().values(**values))
    await set_related(session, values["id"], company_rows)


async def version_files(session: AsyncSession, version_id: UUID, identifiers: list[UUID]) -> list[dict[str, Any]]:
    rows = (await session.execute(sa.select(files).where(files.c.version_id == version_id, files.c.id.in_(identifiers)))).mappings()
    by_id = {row["id"]: dict(row) for row in rows}
    return [by_id[identifier] for identifier in identifiers if identifier in by_id]


async def set_current_version(session: AsyncSession, document_id: UUID, version_id: UUID) -> bool:
    """Atomically select the snapshot and refresh every current metadata projection.

    The caller holds the group and document write locks through commit.
    """
    snapshot = (await session.execute(sa.select(versions).where(versions.c.id == version_id, versions.c.document_id == document_id))).mappings().first()
    if snapshot is None:
        return False
    rows = (await session.execute(sa.select(version_related.c.role, version_related.c.company_id).where(version_related.c.version_id == version_id))).mappings()
    await session.execute(versions.update().where(versions.c.document_id == document_id, versions.c.is_current.is_(True)).values(is_current=False))
    await session.execute(versions.update().where(versions.c.id == version_id).values(is_current=True))
    await set_related(session, document_id, [dict(row) for row in rows])
    await update_document(session, document_id, {"name": snapshot["name"], "platform_ml_related": snapshot["platform_ml_related"]})
    return True


async def insert_version(session: AsyncSession, document_id: UUID, values: dict[str, Any], file_rows: list[dict[str, Any]], company_rows: list[dict[str, Any]]) -> None:
    number = int(await session.scalar(sa.select(sa.func.max(versions.c.version_number)).where(versions.c.document_id == document_id)) or 0) + 1
    await session.execute(versions.insert().values(**values, document_id=document_id, version_number=number, is_current=False))
    await session.execute(files.insert(), file_rows)
    if company_rows:
        await session.execute(version_related.insert(), [{"id": uuid4(), "version_id": values["id"], **row} for row in company_rows])
    await set_current_version(session, document_id, values["id"])


async def update_document(session: AsyncSession, document_id: UUID, values: dict[str, Any]) -> None:
    await session.execute(documents.update().where(documents.c.id == document_id).values(**values, updated_at=sa.func.now()))


async def get_file(session: AsyncSession, file_id: UUID, actor: dict[str, Any]) -> dict[str, Any] | None:
    row = (await session.execute(sa.select(files).join(versions, versions.c.id == files.c.version_id).join(documents, documents.c.id == versions.c.document_id).where(files.c.id == file_id, _live(actor)))).mappings().first()
    return dict(row) if row else None


async def deletion_usages(session: AsyncSession, document_id: UUID) -> dict[str, Any] | None:
    document = (await session.execute(sa.select(documents).where(documents.c.id == document_id, documents.c.deleted_at.is_(None)))).mappings().first()
    if document is None:
        return None
    condition = documents.c.group_id == document["group_id"] if document["is_main"] else documents.c.id == document_id
    ids = list((await session.scalars(sa.select(documents.c.id).where(condition, documents.c.deleted_at.is_(None)).order_by(documents.c.id))).all())
    link_rows = (await session.execute(sa.select(links.c.document_id, links.c.program_id, programs.c.name).join(programs, programs.c.id == links.c.program_id).where(links.c.document_id.in_(ids)).order_by(links.c.document_id, links.c.program_id))).mappings().all()
    return {"document_ids": ids, "programs": [{"id": key, "name": name} for key, name in sorted({(row["program_id"], row["name"]) for row in link_rows})], "links": [{"document_id": row["document_id"], "program_id": row["program_id"]} for row in link_rows]}


async def delete_documents(session: AsyncSession, document_ids: list[UUID], actor_id: UUID, now: datetime) -> None:
    await session.execute(links.delete().where(links.c.document_id.in_(document_ids)))
    await session.execute(documents.update().where(documents.c.id.in_(document_ids)).values(deleted_at=now, deleted_by=actor_id, updated_at=now))
