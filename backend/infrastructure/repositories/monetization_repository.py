"""Dictionary persistence API for the isolated internal monetization module.

The presentation layer owns commits. Source and program locks last until its
transaction finishes; every financial mutation takes the same deal row lock.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.monetization.errors import MonetizationConflict, MonetizationValidation
from domain.monetization.identifiers import entity_id as _uuid
from infrastructure.models import monetization as m
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import (
    Company,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportProgram,
    SupportProgramDistributor,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import exchange_access_repository, support_repository

Record = dict[str, Any]
_SESSION_ROLES = {"carcraft_employee", "dealer", "distributor", "leasing_company"}


def _json(value: Any) -> Any:
    if isinstance(value, (UUID, Decimal, datetime, date)):
        return str(value)
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _values(table: sa.Table, data: Record) -> Record:
    result: Record = {}
    for column in table.c:
        if column.name not in data:
            continue
        value = data[column.name]
        if value is not None and isinstance(column.type, sa.UUID):
            value = _uuid(value)
        elif isinstance(column.type, sa.JSON):
            value = _json(value)
        elif (
            value is not None
            and isinstance(column.type, sa.DateTime)
            and isinstance(value, str)
        ):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        elif (
            value is not None
            and isinstance(column.type, sa.Date)
            and isinstance(value, str)
        ):
            value = date.fromisoformat(value)
        result[column.name] = value
    return result


async def _one(session: AsyncSession, statement: Any) -> Record | None:
    row = (await session.execute(statement)).mappings().first()
    return dict(row) if row else None


async def _all(session: AsyncSession, statement: Any) -> list[Record]:
    return [
        dict(row) for row in (await session.execute(statement)).mappings().all()
    ]


async def _insert(session: AsyncSession, table: sa.Table, payload: Record) -> Record:
    row = await _one(
        session, table.insert().values(**_values(table, payload)).returning(table)
    )
    assert row is not None
    return row


async def resolve_actor(
    session: AsyncSession, user_id: Any, role: str, company_id: Any = None
) -> Record | None:
    if (
        role not in _SESSION_ROLES
        or await exchange_access_repository.get_actor_role(session, _uuid(user_id))
        != role
    ):
        return None
    actor: Record = {
        "user_id": _uuid(user_id),
        "user_name": await session.scalar(sa.select(User.name).where(User.id == _uuid(user_id))),
        "role": role,
        "company_id": _uuid(company_id) if company_id else None,
        "company_ids": [],
        "leasing_company_ids": [],
        "dealer_group_ids": [],
        "dealer_company_ids": [],
        "can_write": False,
    }
    if role == "carcraft_employee":
        # Global administrators have no company scope. Explicit company employee
        # permissions still apply when one is selected.
        permissions = None
        if company_id is None:
            # Older administrator sessions may predate company assignment.
            company_id = await session.scalar(
                sa.select(User.company_id).where(User.id == _uuid(user_id))
            )
            actor["company_id"] = company_id
        if company_id is not None:
            permissions = (await session.execute(sa.select(
                UserCompany.can_view_applications, UserCompany.can_create_applications,
            ).where(UserCompany.user_id == _uuid(user_id),
                    UserCompany.company_id == _uuid(company_id)))).one_or_none()
        if permissions is not None and not permissions.can_view_applications:
            return None
        actor["can_write"] = permissions is None or permissions.can_create_applications
        return actor
    memberships = await exchange_access_repository.get_actor_companies(
        session, _uuid(user_id), role
    )
    membership = next(
        (
            item
            for item in memberships
            if item["id"] == actor["company_id"] and item["can_view_applications"]
        ),
        None,
    )
    if not membership:
        return None
    actor["company_ids"] = [actor["company_id"]]
    actor["can_write"] = bool(membership["can_create_applications"])
    if role == "leasing_company":
        ids = (
            await session.scalars(
                sa.select(LeasingCompany.id).where(
                    LeasingCompany.company_id == _uuid(company_id),
                    LeasingCompany.is_active.is_(True),
                )
            )
        ).all()
        actor["leasing_company_ids"] = list(ids)
        return actor if ids else None
    group_stmt = sa.select(DealerGroup.id).where(DealerGroup.is_active.is_(True))
    if role == "distributor":
        group_stmt = group_stmt.where(
            DealerGroup.distributor_company_id == _uuid(company_id)
        )
    else:
        group_stmt = group_stmt.join(
            DealerGroupMember, DealerGroupMember.dealer_group_id == DealerGroup.id
        ).where(DealerGroupMember.dealer_company_id == _uuid(company_id))
    group_ids = list((await session.scalars(group_stmt)).all())
    actor["dealer_group_ids"] = group_ids
    if group_ids:
        dealer_ids = (
            await session.scalars(
                sa.select(DealerGroupMember.dealer_company_id).where(
                    DealerGroupMember.dealer_group_id.in_(group_ids)
                )
            )
        ).all()
        actor["dealer_company_ids"] = list(dealer_ids)
    if role == "distributor":
        linked_dealers = (await session.scalars(
            sa.select(DistributorDealerLink.dealer_company_id).where(
                DistributorDealerLink.distributor_company_id == _uuid(company_id)
            )
        )).all()
        actor["dealer_company_ids"] = list(dict.fromkeys([
            *actor["dealer_company_ids"], *linked_dealers,
        ]))
    return actor


def _scope(table: sa.Table, actor: Record | None, *, program: bool = False) -> Any:
    if actor is None or actor["role"] == "carcraft_employee":
        return sa.true()
    role, company = actor["role"], actor.get("company_id")
    if role == "leasing_company":
        return table.c.leasing_company_id.in_(
            [_uuid(item) for item in actor.get("leasing_company_ids", [])]
        )
    if role == "dealer":
        own = table.c.dealer_company_id == _uuid(company)
        return sa.or_(table.c.dealer_company_id.is_(None), own) if program else own
    if role == "distributor":
        own = table.c.distributor_company_id == _uuid(company)
        if program:
            dealers = [_uuid(item) for item in actor.get("dealer_company_ids", [])]
            return sa.and_(
                sa.or_(table.c.distributor_company_id.is_(None), own),
                sa.or_(
                    table.c.dealer_company_id.is_(None),
                    table.c.dealer_company_id.in_(dealers),
                ),
            )
        # Use current direct links and active group membership, never stale
        # snapshot fields: removing both relationships revokes dealer visibility.
        return table.c.dealer_company_id.in_(
            [_uuid(item) for item in actor.get("dealer_company_ids", [])]
        )
    return sa.false()


async def create_program(
    session: AsyncSession, payload: Record, actor_id: Any
) -> Record:
    # One stable row serializes even a first insertion with no monetization rows.
    leasing_id = _uuid(payload["leasing_company_id"])
    await session.execute(
        sa.select(LeasingCompany.id)
        .where(LeasingCompany.id == leasing_id)
        .with_for_update()
    )
    values = _values(m.programs, payload)
    await _validate_program_references(session, payload)
    if payload.get("status", "active") == "active":
        await _check_program_overlap(session, values, source_types={s["source_type"] for s in payload["sources"]})
    program = await _insert(session, m.programs, dict(values, created_by=actor_id))
    for position, source in enumerate(payload["sources"]):
        saved = await _insert(
            session,
            m.sources,
            dict(source, program_id=program["id"], position=position),
        )
        for side, key in (("expense", "expenses"), ("income", "incomes")):
            for index, item in enumerate(source.get(key, [])):
                await _insert(
                    session,
                    m.participants,
                    dict(
                        item,
                        local_id=item.get("local_id") or str(uuid4()),
                        program_source_id=saved["id"],
                        side=side,
                        position=index,
                    ),
                )
    result = await get_program(session, program["id"])
    assert result is not None
    return result


async def get_program(
    session: AsyncSession, program_id: Any, actor: Record | None = None
) -> Record | None:
    program = await _one(
        session,
        sa.select(m.programs).where(
            m.programs.c.id == _uuid(program_id),
            _scope(m.programs, actor, program=True),
        ),
    )
    if program is None:
        return None
    program["sources"] = await _all(
        session,
        sa.select(m.sources)
        .where(m.sources.c.program_id == _uuid(program_id))
        .order_by(m.sources.c.position),
    )
    for source in program["sources"]:
        rows = await _all(
            session,
            sa.select(m.participants)
            .where(m.participants.c.program_source_id == _uuid(source["id"]))
            .order_by(m.participants.c.position),
        )
        source["expenses"] = [item for item in rows if item["side"] == "expense"]
        source["incomes"] = [item for item in rows if item["side"] == "income"]
    program["contracts"] = await _all(
        session,
        sa.select(m.contracts)
        .where(m.contracts.c.program_id == _uuid(program_id))
        .order_by(m.contracts.c.created_at, m.contracts.c.id),
    )
    await _enrich_program(session, program, actor)
    return program


async def list_programs(
    session: AsyncSession,
    actor: Record | None = None,
    filters: Record | None = None,
    offset: int = 0,
    limit: int = 50,
) -> Record:
    conditions = [_scope(m.programs, actor, program=True)]
    for key, value in (filters or {}).items():
        if value is None:
            continue
        if key == "source_type":
            conditions.append(
                sa.exists(
                    sa.select(m.sources.c.id).where(
                        m.sources.c.program_id == m.programs.c.id,
                        m.sources.c.source_type == value,
                    )
                )
            )
        elif key in ("leasing_company_id", "brand", "status"):
            conditions.append(
                m.programs.c[key] == (_uuid(value) if key.endswith("_id") else value)
            )
        elif key in ("search", "q"):
            conditions.append(m.programs.c.name.ilike(f"%{value}%"))
    total = await session.scalar(
        sa.select(sa.func.count()).select_from(m.programs).where(*conditions)
    )
    ids = (
        await session.scalars(
            sa.select(m.programs.c.id)
            .where(*conditions)
            .order_by(m.programs.c.created_at.desc(), m.programs.c.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    items = [await get_program(session, item, actor) for item in ids]
    return {"items": items, "total": int(total or 0)}


async def set_program_status(
    session: AsyncSession, program_id: Any, status: str
) -> Record | None:
    leasing_id = await session.scalar(
        sa.select(m.programs.c.leasing_company_id).where(
            m.programs.c.id == _uuid(program_id)
        )
    )
    if leasing_id is not None:
        await session.execute(
            sa.select(LeasingCompany.id)
            .where(LeasingCompany.id == leasing_id)
            .with_for_update()
        )
    program = await get_program(session, program_id)
    if program is None:
        return None
    if status == "active":
        await _validate_support_reference(session, program)
        await _check_program_overlap(
            session, _values(m.programs, program),
            source_types={s["source_type"] for s in program["sources"]}, exclude_id=program_id
        )
    await session.execute(
        m.programs.update()
        .where(m.programs.c.id == _uuid(program_id))
        .values(status=status)
    )
    return await get_program(session, program_id)


async def get_deal(
    session: AsyncSession, deal_id: Any, actor: Record | None = None
) -> Record | None:
    deal = await _one(
        session,
        sa.select(m.deals).where(
            m.deals.c.id == _uuid(deal_id), _scope(m.deals, actor)
        ),
    )
    if deal is None:
        return None
    deal["amounts"] = await _all(
        session,
        sa.select(
            m.amounts,
            m.participants.c.calc_type.label("original_calc_type"),
            m.participants.c.base_type.label("condition_base_type"),
            m.participants.c.value.label("condition_value"),
            m.participants.c.min.label("condition_min"),
            m.participants.c.max.label("condition_max"),
        )
        .outerjoin(m.participants, m.participants.c.id == m.amounts.c.source_participant_id)
        .where(m.amounts.c.deal_id == _uuid(deal_id))
        .order_by(m.amounts.c.position),
    )
    deal["documents"] = await _all(
        session,
        sa.select(m.documents)
        .where(m.documents.c.deal_id == _uuid(deal_id))
        .order_by(m.documents.c.created_at, m.documents.c.id),
    )
    for document in deal["documents"]:
        document["stale"] = document["revision"] != deal["revision"]
    deal["adjustments"] = await _all(
        session,
        sa.select(m.adjustments)
        .where(m.adjustments.c.deal_id == _uuid(deal_id))
        .order_by(m.adjustments.c.revision, m.adjustments.c.created_at, m.adjustments.c.id),
    )
    _enrich_deal(deal)
    return deal


async def list_deals(
    session: AsyncSession,
    actor: Record | None = None,
    filters: Record | None = None,
    offset: int = 0,
    limit: int = 50,
) -> Record:
    conditions = [_scope(m.deals, actor)]
    for key, value in (filters or {}).items():
        if value is not None and key in (
            "leasing_company_id",
            "dealer_company_id",
            "client_company_id",
            "status",
            "source_type",
        ):
            conditions.append(
                m.deals.c[key] == (_uuid(value) if key.endswith("_id") else value)
            )
        elif value is not None and key == "brand":
            conditions.append(m.deals.c.vehicles.contains([{"brand": value}]))
        elif value is not None and key in ("search", "q"):
            conditions.append(m.deals.c.application_number.ilike(f"%{value}%"))
    total = await session.scalar(
        sa.select(sa.func.count()).select_from(m.deals).where(*conditions)
    )
    ids = (
        await session.scalars(
            sa.select(m.deals.c.id)
            .where(*conditions)
            .order_by(m.deals.c.created_at.desc(), m.deals.c.id)
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "items": [await get_deal(session, item, actor) for item in ids],
        "total": int(total or 0),
    }


async def _advisory_lock(session: AsyncSession, key: str) -> None:
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key}
    )


def _origin_field(context: Record) -> str:
    """The one column that identifies the source of a captured deal.

    Capture is idempotent per origin UUID. A fast deal is keyed by its own id, never
    by its split ``group_id``, so every part of a split deal is a separate source.
    """
    if context.get("exchange_request_id"):
        return "exchange_request_id"
    if context.get("fast_deal_id"):
        return "fast_deal_id"
    return "leasing_company_application_id"


async def insert_deal(
    session: AsyncSession, context: Record, program: Record, amounts: list[Record]
) -> Record:
    origin_field = _origin_field(context)
    origin = context[origin_field]
    await _advisory_lock(session, f"monetization:{origin_field}:{origin}")
    existing = await session.scalar(
        sa.select(m.deals.c.id).where(m.deals.c[origin_field] == _uuid(origin))
    )
    if existing:
        result = await get_deal(session, existing)
        assert result is not None
        return result
    vin = program.get("vin")
    if vin:
        vin = vin.strip().upper()
        await _advisory_lock(session, f"monetization:vin:{vin}")
        if await session.scalar(
            sa.select(m.deals.c.id).where(m.deals.c.consumed_vin == vin)
        ):
            raise MonetizationConflict(
                "Условия монетизации для этого VIN уже использованы"
            )
    snapshot = dict(
        context,
        source_snapshot=context,
        program_id=program["id"],
        consumed_vin=vin,
        participant_snapshot=await _participant_snapshot(session, context),
    )
    snapshot["participant_snapshot"]["program_name"] = program["name"]
    deal = await _insert(session, m.deals, snapshot)
    # Amount IDs are allocated before insertion so references remain in one block.
    rows = [
        dict(
            item, id=item.get("id") or uuid4(), deal_id=deal["id"], position=index
        )
        for index, item in enumerate(amounts)
    ]
    for row in rows:
        participant = row["participant_type"]
        company_key = {
            "leasing": "leasing_company_id",
            "dealer": "dealer_company_id",
            "distributor": "distributor_company_id",
        }.get(participant)
        if company_key and not row.get("participant_company_id"):
            row["participant_company_id"] = context.get(company_key)
    for row in sorted(rows, key=lambda item: item["side"] != "expense"):
        await _insert(session, m.amounts, row)
    result = await get_deal(session, deal["id"])
    assert result is not None
    return result


async def lock_deal(
    session: AsyncSession, deal_id: Any, actor: Record | None = None
) -> Record | None:
    locked = await session.scalar(
        sa.select(m.deals.c.id)
        .where(m.deals.c.id == _uuid(deal_id), _scope(m.deals, actor))
        .with_for_update()
    )
    return await get_deal(session, locked, actor) if locked else None


async def update_deal(session: AsyncSession, deal_id: Any, changes: Record) -> Record:
    deal = await lock_deal(session, deal_id)
    if deal is None:
        raise MonetizationConflict("Сделка монетизации не найдена")
    if deal["status"] == "paid":
        raise MonetizationConflict("Подтверждённую сделку монетизации нельзя изменять")
    allowed = {
        key: value
        for key, value in changes.items()
        if key in ("status", "revision", "confirmations")
    }
    await session.execute(
        m.deals.update()
        .where(m.deals.c.id == _uuid(deal_id))
        .values(**_values(m.deals, allowed))
    )
    result = await get_deal(session, deal_id)
    assert result is not None
    return result


async def replace_amounts(
    session: AsyncSession,
    deal_id: Any,
    amounts: list[Record],
    actor_id: Any,
    revision: int,
) -> None:
    deal = await lock_deal(session, deal_id)
    if deal is None or deal["status"] == "paid":
        raise MonetizationConflict("Эту сделку монетизации нельзя корректировать")
    old = {row["id"]: row for row in deal["amounts"]}
    for row in amounts:
        if _uuid(row["id"]) not in old:
            raise MonetizationConflict("Финансовая строка не относится к этой сделке")
        previous = old[_uuid(row["id"])]
        before = previous["amount"]
        after = Decimal(str(row["amount"]))
        fields = ("amount", "percent", "input_mode")
        if any(row.get(field) != previous.get(field) for field in fields):
            await _insert(
                session,
                m.adjustments,
                {
                    "deal_id": deal_id,
                    "amount_id": row["id"],
                    "old_value": before,
                    "new_value": after,
                    "old_percent": previous.get("percent"),
                    "new_percent": row.get("percent"),
                    "old_input_mode": previous.get("input_mode"),
                    "new_input_mode": row.get("input_mode"),
                    "revision": revision,
                    "created_by": actor_id,
                },
            )
            await session.execute(
                m.amounts.update()
                .where(
                    m.amounts.c.id == _uuid(row["id"]),
                    m.amounts.c.deal_id == _uuid(deal_id),
                )
                .values(
                    amount=after, percent=row.get("percent"),
                    input_mode=row.get("input_mode"),
                )
            )


async def add_document(
    session: AsyncSession, deal_id: Any, payload: Record, actor_id: Any
) -> Record:
    return await _insert(
        session, m.documents, dict(payload, deal_id=deal_id, created_by=actor_id)
    )


async def get_document(
    session: AsyncSession, document_id: Any, actor: Record
) -> Record | None:
    return await _one(
        session,
        sa.select(m.documents)
        .join(m.deals, m.deals.c.id == m.documents.c.deal_id)
        .where(m.documents.c.id == _uuid(document_id), _scope(m.deals, actor)),
    )


async def add_contract(
    session: AsyncSession, program_id: Any, payload: Record, actor_id: Any
) -> Record:
    return await _insert(
        session, m.contracts, dict(payload, program_id=program_id, created_by=actor_id)
    )


async def get_contract(
    session: AsyncSession, contract_id: Any, actor: Record
) -> Record | None:
    return await _one(
        session,
        sa.select(m.contracts)
        .join(m.programs, m.programs.c.id == m.contracts.c.program_id)
        .where(
            m.contracts.c.id == _uuid(contract_id),
            _scope(m.programs, actor, program=True),
        ),
    )


async def lock_application(
    session: AsyncSession, application_id: Any, actor: Record, *, lock: bool = True
) -> Record | None:
    conditions = [LeasingApplication.id == _uuid(application_id)]
    if actor["role"] == "dealer":
        conditions.append(
            LeasingApplication.dealer_company_id == _uuid(actor["company_id"])
        )
    elif actor["role"] != "carcraft_employee":
        return None
    application = await _one(
        session,
        (sa.select(LeasingApplication.__table__).where(*conditions).with_for_update()
         if lock else sa.select(LeasingApplication.__table__).where(*conditions)),
    )
    if application:
        application["has_lca"] = bool(
            await session.scalar(
                sa.select(
                    sa.exists().where(
                        LeasingCompanyApplication.application_id
                        == _uuid(application_id)
                    )
                )
            )
        )
    return application


def _request_scope(actor: Record | None) -> Any:
    if actor is None or actor["role"] == "carcraft_employee":
        return sa.true()
    if actor["role"] == "dealer":
        return m.condition_requests.c.dealer_company_id == _uuid(actor["company_id"])
    if actor["role"] == "leasing_company":
        return m.condition_requests.c.leasing_company_id.in_(
            [_uuid(item) for item in actor.get("leasing_company_ids", [])]
        )
    return sa.false()


async def get_condition_request(
    session: AsyncSession,
    request_id: Any,
    actor: Record | None = None,
    lock: bool = False,
) -> Record | None:
    statement = sa.select(m.condition_requests).where(
        m.condition_requests.c.id == _uuid(request_id), _request_scope(actor)
    )
    row = await _one(session, statement.with_for_update() if lock else statement)
    return await _enrich_condition_request(session, row) if row is not None else None


async def list_condition_requests(
    session: AsyncSession, application_id: Any, actor: Record
) -> list[Record]:
    items = await _all(
        session,
        sa.select(m.condition_requests)
        .where(
            m.condition_requests.c.application_id == _uuid(application_id),
            _request_scope(actor),
        )
        .order_by(m.condition_requests.c.created_at, m.condition_requests.c.id),
    )
    return [await _enrich_condition_request(session, item) for item in items]


async def list_condition_request_inbox(
    session: AsyncSession, actor: Record, *, offset: int, limit: int,
) -> Record:
    scope = _request_scope(actor)
    total = await session.scalar(sa.select(sa.func.count()).select_from(
        m.condition_requests).where(scope))
    items = await _all(session, sa.select(m.condition_requests).where(scope)
        .order_by(m.condition_requests.c.created_at.desc(), m.condition_requests.c.id)
        .offset(offset).limit(limit))
    return {"items": [await _enrich_condition_request(session, row) for row in items],
            "total": total or 0}

async def create_condition_request(
    session: AsyncSession, payload: Record, actor_id: Any
) -> Record:
    application_id = _uuid(payload["application_id"])
    application = await _one(
        session,
        sa.select(LeasingApplication.id, LeasingApplication.dealer_company_id)
        .where(LeasingApplication.id == application_id)
        .with_for_update(),
    )
    if not application or application["dealer_company_id"] != _uuid(
        payload["dealer_company_id"]
    ):
        raise MonetizationConflict("Заявка не относится к компании дилера")
    if await session.scalar(
        sa.select(
            sa.exists().where(
                LeasingCompanyApplication.application_id == application_id
            )
        )
    ):
        raise MonetizationConflict(
            "Комиссию можно запросить только до первой заявки в ЛК"
        )
    await _validate_program_references(
        session, {"leasing_company_id": payload["leasing_company_id"]}
    )
    row = await _insert(
        session, m.condition_requests, dict(payload, created_by=actor_id)
    )
    return await _enrich_condition_request(session, row)


async def update_condition_request(
    session: AsyncSession, request_id: Any, changes: Record
) -> Record:
    values = _values(m.condition_requests, changes)
    values["updated_at"] = sa.func.now()
    await session.execute(
        m.condition_requests.update()
        .where(m.condition_requests.c.id == _uuid(request_id))
        .values(**values)
    )
    row = await get_condition_request(session, request_id)
    assert row is not None
    return row


def _dealer_distributor_link(
    distributor_id: UUID | sa.SQLColumnExpression[UUID],
    dealer_id: UUID | sa.SQLColumnExpression[UUID],
) -> sa.ColumnElement[bool]:
    return sa.or_(
        sa.exists(
            sa.select(DistributorDealerLink.dealer_company_id).where(
                DistributorDealerLink.distributor_company_id == distributor_id,
                DistributorDealerLink.dealer_company_id == dealer_id,
            )
        ),
        sa.exists(
            sa.select(DealerGroupMember.dealer_company_id)
            .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
            .where(
                DealerGroup.distributor_company_id == distributor_id,
                DealerGroupMember.dealer_company_id == dealer_id,
                DealerGroup.is_active.is_(True),
            )
        ),
    )


async def lookup_companies(
    session: AsyncSession, actor: Record, kind: str, query: str = "",
    distributor_company_id: UUID | None = None,
    dealer_company_id: UUID | None = None,
) -> list[Record]:
    conditions: list[Any] = [Company.is_active.is_(True)]
    statement: Any
    if query:
        conditions.append(
            sa.or_(Company.name.ilike(f"%{query}%"), Company.inn.ilike(f"%{query}%"))
        )
    if kind in ("leasing", "leasing_company"):
        statement = (
            sa.select(
                LeasingCompany.id,
                Company.id.label("company_id"),
                Company.name,
                Company.inn,
            )
            .join(Company, Company.id == LeasingCompany.company_id)
            .where(LeasingCompany.is_active.is_(True), *conditions)
        )
        if actor["role"] == "leasing_company":
            statement = statement.where(
                LeasingCompany.id.in_(
                    [_uuid(item) for item in actor["leasing_company_ids"]]
                )
            )
    else:
        statement = sa.select(Company.id, Company.name, Company.inn).where(*conditions)
        if kind in ("dealer", "distributor"):
            statement = statement.where(Company.company_type == kind)
        elif kind == "client":
            permitted = sa.select(m.deals.c.client_company_id).where(
                _scope(m.deals, actor)
            )
            statement = statement.where(Company.id.in_(permitted))
        else:
            return []
        if kind == "dealer" and actor["role"] == "dealer":
            statement = statement.where(Company.id == _uuid(actor["company_id"]))
        if kind == "dealer" and actor["role"] == "distributor":
            statement = statement.where(
                Company.id.in_([_uuid(item) for item in actor["dealer_company_ids"]])
            )
        if kind == "distributor" and actor["role"] == "distributor":
            statement = statement.where(Company.id == _uuid(actor["company_id"]))
        if kind == "dealer" and distributor_company_id is not None:
            statement = statement.where(
                _dealer_distributor_link(distributor_company_id, Company.id)
            )
        if kind == "distributor" and dealer_company_id is not None:
            statement = statement.where(
                _dealer_distributor_link(Company.id, dealer_company_id)
            )
    return await _all(session, statement.order_by(Company.name).limit(100))


def _support_arguments(actor: Record) -> Record:
    role = actor["role"]
    if role == "distributor":
        return {
            "visible_distributor_id": _uuid(actor["company_id"]),
            "restrict_to_distributor": True,
        }
    if role == "dealer":
        return {"visible_dealer_company_id": _uuid(actor["company_id"])}
    if role == "leasing_company":
        return {"visible_leasing_company_id": _uuid(actor["leasing_company_ids"][0])}
    return {}


async def lookup_supports(
    session: AsyncSession, actor: Record, query: str = "",
    distributor_company_id: UUID | None = None,
) -> list[Record]:
    items, _ = await support_repository.list_programs(
        session, search=query or None, limit=100, distributor_id=distributor_company_id,
        **_support_arguments(actor)
    )
    return items


async def get_support(
    session: AsyncSession, support_id: Any, actor: Record
) -> Record | None:
    if actor["role"] in ("carcraft_employee", "distributor"):
        arguments = _support_arguments(actor)
        item = await support_repository.get_program_by_id(
            session, _uuid(support_id), **arguments
        )
        return (
            await _support_view_data(session, item, actor) if item is not None else None
        )
    item = await support_repository.get_program_by_id(session, _uuid(support_id))
    if item is None:
        return None
    page = 1
    while True:
        visible, total = await support_repository.list_programs(
            session,
            search=item["name"],
            page=page,
            limit=100,
            **_support_arguments(actor),
        )
        if _uuid(support_id) in {row["id"] for row in visible}:
            # Existing organization queries hide support files and compatibility.
            return {
                "id": _uuid(support_id),
                "name": item["name"],
                "documents": [],
                "compatible_programs": [],
            }
        if page * 100 >= total:
            return None
        page += 1


async def _company_option(
    session: AsyncSession, company_id: Any, *, leasing: bool = False
) -> Record | None:
    if not company_id:
        return None
    if leasing:
        statement = (
            sa.select(LeasingCompany.id, Company.name, Company.inn)
            .join(Company, Company.id == LeasingCompany.company_id)
            .where(LeasingCompany.id == _uuid(company_id))
        )
    else:
        statement = sa.select(Company.id, Company.name, Company.inn).where(
            Company.id == _uuid(company_id)
        )
    return await _one(session, statement)


async def _enrich_program(
    session: AsyncSession, program: Record, actor: Record | None
) -> None:
    program["leasing_company"] = await _company_option(
        session, program["leasing_company_id"], leasing=True
    )
    program["dealer"] = await _company_option(session, program.get("dealer_company_id"))
    program["distributor"] = await _company_option(
        session, program.get("distributor_company_id")
    )
    if program.get("support_program_id"):
        from infrastructure.models.support import SupportProgram

        program["support_program_name"] = await session.scalar(
            sa.select(SupportProgram.name).where(
                SupportProgram.id == _uuid(program["support_program_id"])
            )
        )
        program["support_program"] = await get_support(
            session,
            program["support_program_id"],
            actor or {"role": "carcraft_employee"},
        )


async def _participant_snapshot(session: AsyncSession, context: Record) -> Record:
    result = dict(context.get("participant_snapshot") or {})
    for key, field in (
        ("leasing_company", "leasing_company_id"),
        ("dealer_company", "dealer_company_id"),
        ("client_company", "client_company_id"),
        ("distributor_company", "distributor_company_id"),
    ):
        if key not in result:
            result[key] = await _company_option(
                session, context.get(field), leasing=key == "leasing_company"
            )
    return result


_SOURCE_UUID_FIELDS = frozenset({
    "application_id", "leasing_company_application_id", "exchange_request_id",
    "fast_deal_id", "leasing_company_id", "dealer_company_id", "distributor_company_id",
    "client_company_id", "dealer_group_id", "final_proposal_id", "accepted_bid_id",
    "actor_user_id",
})
_VEHICLE_UUID_FIELDS = frozenset({
    "vehicle_id", "application_vehicle_id", "allocation_id", "dealer_company_id",
    "stock_dealer_company_id", "fast_deal_vehicle_id",
})
_SUPPORT_UUID_FIELDS = frozenset({
    "id", "application_id", "exchange_request_id", "support_program_id",
    "dealer_company_id", "distributor_company_id", "created_by", "vehicle_id",
    "fast_deal_id", "fast_deal_vehicle_id", "product_id",
})


def _restore_uuid_fields(record: Record, fields: frozenset[str]) -> Record:
    return {key: _uuid(value) if key in fields and value is not None else value
            for key, value in record.items()}


def _restore_source_snapshot(snapshot: Record) -> Record:
    result = _restore_uuid_fields(snapshot, _SOURCE_UUID_FIELDS)
    if "vehicles" in result:
        result["vehicles"] = [
            _restore_uuid_fields(row, _VEHICLE_UUID_FIELDS) for row in result["vehicles"]
        ]
    if "supports" in result:
        result["supports"] = [
            _restore_uuid_fields(row, _SUPPORT_UUID_FIELDS) for row in result["supports"]
        ]
    return result


def _enrich_deal(deal: Record) -> None:
    # JSON is a storage boundary; hydrate its UUID fields before domain use.
    deal["source_snapshot"] = _restore_source_snapshot(deal.get("source_snapshot") or {})
    deal["vehicles"] = [_restore_uuid_fields(row, _VEHICLE_UUID_FIELDS)
                        for row in deal.get("vehicles") or []]
    deal["confirmations"] = {
        party: _restore_uuid_fields(confirmation, frozenset({"user_id"}))
        for party, confirmation in (deal.get("confirmations") or {}).items()
    }
    snapshot = dict(deal.get("participant_snapshot") or {})
    for key in (
        "leasing_company",
        "dealer_company",
        "client_company",
        "distributor_company",
    ):
        company = snapshot.get(key)
        snapshot[key] = _restore_uuid_fields(company, frozenset({"id"})) if company else None
        deal[key] = snapshot[key]
    deal["participant_snapshot"] = snapshot
    deal["program_name"] = snapshot.get("program_name")
    vehicles = deal.get("vehicles") or []
    deal["brand"] = vehicles[0].get("brand") if vehicles else None


async def list_candidate_programs(
    session: AsyncSession, context: Record
) -> list[Record]:
    leasing_id = _uuid(context["leasing_company_id"])
    # Selection, creation and activation use the same serialization boundary.
    await session.execute(
        sa.select(LeasingCompany.id)
        .where(LeasingCompany.id == leasing_id)
        .with_for_update()
    )
    ids = (
        await session.scalars(
            sa.select(m.programs.c.id).where(
                m.programs.c.leasing_company_id == leasing_id,
                m.programs.c.status == "active",
            )
        )
    ).all()
    result = []
    for program_id in ids:
        program = await get_program(session, program_id)
        if program is not None:
            result.append(program)
    return result


async def _enrich_condition_request(session: AsyncSession, request: Record) -> Record:
    request["application_number"] = await session.scalar(
        sa.select(LeasingApplication.display_number).where(
            LeasingApplication.id == _uuid(request["application_id"])))
    request["leasing_company"] = await _company_option(
        session, request["leasing_company_id"], leasing=True
    )
    request["dealer_company"] = await _company_option(
        session, request["dealer_company_id"]
    )
    return request


async def get_support_document(
    session: AsyncSession, document_id: Any, actor: Record
) -> Record | None:
    from infrastructure.models.support import SupportBillOfLading

    if actor["role"] not in ("carcraft_employee", "distributor"):
        return None
    item = await _one(
        session,
        sa.select(SupportBillOfLading.__table__).where(
            SupportBillOfLading.id == _uuid(document_id)
        ),
    )
    if (
        item is None
        or await get_support(session, item["support_program_id"], actor) is None
    ):
        return None
    return dict(
        item,
        filename=item.get("file_name"),
        size_bytes=item.get("file_size"),
        object_key=item.get("file_path"),
    )


async def _check_program_overlap(
    session: AsyncSession, values: Record, *, source_types: set[str], exclude_id: Any = None
) -> None:
    conditions = [
        m.programs.c.leasing_company_id == values["leasing_company_id"],
        m.programs.c.status == "active",
        sa.exists(sa.select(m.sources.c.id).where(
            m.sources.c.program_id == m.programs.c.id,
            m.sources.c.source_type.in_(source_types),
        )),
    ]
    conditions.extend(
        m.programs.c[field].is_not_distinct_from(values.get(field))
        for field in (
            "dealer_company_id",
            "distributor_company_id",
            "support_program_id",
            "brand",
            "model",
            "modification",
            "trim",
            "vin",
        )
    )
    if values.get("trim") is not None:
        conditions.append(
            m.programs.c.vehicle_filter_version
            == values.get("vehicle_filter_version", 2)
        )
    conditions.append(
        sa.or_(
            m.programs.c.period_end.is_(None),
            m.programs.c.period_end >= values["period_start"],
        )
    )
    if values.get("period_end") is not None:
        conditions.append(m.programs.c.period_start <= values["period_end"])
    if exclude_id is not None:
        conditions.append(m.programs.c.id != _uuid(exclude_id))
    if await session.scalar(sa.select(m.programs.c.id).where(*conditions).limit(1)):
        raise MonetizationConflict(
            "Периоды одинаковых активных условий монетизации пересекаются"
        )


async def _validate_program_references(session: AsyncSession, payload: Record) -> None:
    leasing = await session.scalar(
        sa.select(LeasingCompany.id)
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(
            LeasingCompany.id == _uuid(payload["leasing_company_id"]),
            LeasingCompany.is_active.is_(True),
            Company.is_active.is_(True),
            Company.company_type == "leasing_company",
        )
    )
    if not leasing:
        raise MonetizationValidation(
            "Выберите действующую зарегистрированную лизинговую компанию"
        )
    for field, kind in (
        ("dealer_company_id", "dealer"),
        ("distributor_company_id", "distributor"),
    ):
        if payload.get(field):
            valid = await session.scalar(
                sa.select(Company.id).where(
                    Company.id == _uuid(payload[field]),
                    Company.company_type == kind,
                    Company.is_active.is_(True),
                )
            )
            if not valid:
                raise MonetizationValidation(
                    "Выберите зарегистрированную компанию: "
                    + {"dealer": "дилер", "distributor": "дистрибьютор"}[kind]
                )
    distributor_id = payload.get("distributor_company_id")
    dealer_id = payload.get("dealer_company_id")
    if distributor_id is not None and dealer_id is not None:
        linked = await session.scalar(sa.select(
            _dealer_distributor_link(_uuid(distributor_id), _uuid(dealer_id))
        ))
        if not linked:
            raise MonetizationValidation(
                "Выбранный дилер не связан с выбранным дистрибьютором"
            )
    await _validate_support_reference(session, payload)


async def _validate_support_reference(session: AsyncSession, payload: Record) -> None:
    if not payload.get("support_program_id"):
        return
    statement = sa.select(SupportProgram.id).where(
        SupportProgram.id == _uuid(payload["support_program_id"])
    )
    distributor_id = payload.get("distributor_company_id")
    if distributor_id is not None:
        linked_distributor = _uuid(distributor_id)
        statement = statement.where(
            sa.or_(
                SupportProgram.distributor_id == linked_distributor,
                sa.exists(sa.select(SupportProgramDistributor.support_program_id).where(
                    SupportProgramDistributor.support_program_id == SupportProgram.id,
                    SupportProgramDistributor.distributor_id == linked_distributor,
                )),
            )
        )
    if not await session.scalar(statement):
        raise MonetizationValidation(
            "Программа стимулирования не связана с выбранным дистрибьютором"
            if distributor_id is not None else "Программа стимулирования не найдена"
        )


async def find_source_deal(session: AsyncSession, context: Record) -> Record | None:
    origin_field = _origin_field(context)
    origin = context[origin_field]
    await _advisory_lock(session, f"monetization:{origin_field}:{origin}")
    deal_id = await session.scalar(
        sa.select(m.deals.c.id).where(m.deals.c[origin_field] == _uuid(origin))
    )
    return await get_deal(session, deal_id) if deal_id else None


async def _support_view_data(
    session: AsyncSession, item: Record, actor: Record
) -> Record:
    result = dict(item)
    result["documents"] = [
        dict(
            document,
            filename=document.get("file_name"),
            object_key=document.get("file_path"),
            size_bytes=document.get("file_size"),
        )
        for document in (result.get("bill_of_lading") or {}).get("files", [])
    ]
    result["compatible_programs"] = []
    for program_id in item.get("compatible_support_ids", []):
        compatible = await support_repository.get_program_by_id(
            session, _uuid(program_id), **_support_arguments(actor)
        )
        if compatible is not None:
            result["compatible_programs"].append(
                {"id": compatible["id"], "name": compatible["name"]}
            )
    return result
