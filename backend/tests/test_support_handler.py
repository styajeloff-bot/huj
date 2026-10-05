"""Functional tests for the support-program command/query handlers."""

from __future__ import annotations

import datetime as _dt
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.support import (
    CreateDealerGroupCommand,
    CreateSupportProgramCommand,
    DeleteBillOfLadingCommand,
    DeleteDealerGroupCommand,
    DeleteSupportProgramCommand,
    UpdateSupportProgramCommand,
    UploadBillOfLadingCommand,
    UploadedBillOfLadingFile,
    handle_create_dealer_group,
    handle_create_support_program,
    handle_delete_bill_of_lading,
    handle_delete_dealer_group,
    handle_delete_support_program,
    handle_update_support_program,
    handle_upload_bill_of_lading,
)
from application.queries.support import (
    GetDealerGroupQuery,
    GetSupportProgramQuery,
    ListDealerGroupsQuery,
    ListSupportProgramsQuery,
    handle_get_dealer_group,
    handle_get_support_program,
    handle_list_dealer_groups,
    handle_list_support_programs,
)
from domain.errors import (
    BillOfLadingFileNotFoundError,
    DealerGroupAlreadyExistsError,
    DealerGroupNotFoundError,
    DealerNotFoundError,
    DistributorNotFoundError,
    InvalidDealerGroupError,
    InvalidSupportProgramError,
    InvalidUploadError,
    LeasingCompanyNotFoundError,
    SupportProgramNotFoundError,
)
from infrastructure.models.companies import (
    Company,
    Distributor,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.support import (
    SupportProgram,
    SupportProgramCompatibility,
    SupportProgramDistributor,
)
from infrastructure.models.users import User
from infrastructure.repositories import support_repository
from tests.fakes.object_storage import FakeObjectStorage
from tests.legacy_compat import CarModel, Mark


@pytest_asyncio.fixture
async def mark_bmw(db_session: AsyncSession) -> Mark:
    mark = Mark(id="bmw", name="BMW", cyrillic_name="БМВ")
    db_session.add(mark)
    await db_session.flush()
    return mark


@pytest_asyncio.fixture
async def model_x5(
    db_session: AsyncSession,
    mark_bmw: Mark,
    default_vehicle_category_id: str,
) -> CarModel:
    model = CarModel(
        id="x5",
        name="X5",
        cyrillic_name="Икс 5",
        mark_id=mark_bmw.id,
        category=default_vehicle_category_id,
    )
    db_session.add(model)
    await db_session.flush()
    return model


@pytest_asyncio.fixture
async def leasing_company(db_session: AsyncSession) -> LeasingCompany:
    lc = LeasingCompany()
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def distributor(db_session: AsyncSession) -> Distributor:
    company = Company(
        name="Support Distributor",
        inn="7700000100",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    d = Distributor(company_id=company.id, is_active=True)
    db_session.add(d)
    await db_session.flush()
    return d


def _company_id(distributor: Distributor) -> UUID:
    assert distributor.company_id is not None
    return distributor.company_id


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660001111",
        email="dealer@test.local",
        name="Dealer A",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def dealer_company(
    db_session: AsyncSession,
    distributor: Distributor,
) -> Company:
    company = Company(
        name="Support Dealer Company",
        inn="7700000101",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=_company_id(distributor),
            dealer_company_id=company.id,
        )
    )
    await db_session.flush()
    return company


# ---------------------------------------------------------------------------
# Support program handlers
# ---------------------------------------------------------------------------


async def test_create_support_program_persists_and_links_relations(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    model_x5: CarModel,
    leasing_company: LeasingCompany,
    distributor: Distributor,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="Support A",
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        model_ids=[model_x5.id],
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 50000},
        distributor_id=_company_id(distributor),
        leasing_company_ids=[leasing_company.id],
        production_date_from=_dt.date(2026, 1, 10),
        production_date_to=_dt.date(2026, 2, 20),
        delivery_date_from=_dt.date(2026, 3, 1),
        delivery_date_to=_dt.date(2026, 4, 15),
        is_active=True,
        created_by=employee_user.id,
    )
    program = await handle_create_support_program(cmd, db_session)
    assert program["id"] is not None
    assert program["leasing_company_ids"] == [leasing_company.id]
    assert program["leasing_companies"][0]["id"] == leasing_company.id
    assert str(program["distributor_id"]) == str(_company_id(distributor))
    assert program["distributor_ids"] == [_company_id(distributor)]
    assert program["mark_name"] == "BMW"
    assert program["model_name"] == "X5"
    assert program["support_params"]["value"] == 50000
    assert program["production_date_from"] == _dt.date(2026, 1, 10)
    assert program["production_date_to"] == _dt.date(2026, 2, 20)
    assert program["delivery_date_from"] == _dt.date(2026, 3, 1)
    assert program["delivery_date_to"] == _dt.date(2026, 4, 15)


async def test_create_support_program_rejects_unknown_distributor(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="bad",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        distributor_id=uuid4(),
        created_by=employee_user.id,
    )
    with pytest.raises(DistributorNotFoundError):
        await handle_create_support_program(cmd, db_session)


async def test_create_support_program_requires_distributor(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="missing distributor",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        created_by=employee_user.id,
    )
    with pytest.raises(InvalidSupportProgramError, match="Дистрибьютор"):
        await handle_create_support_program(cmd, db_session)


async def test_create_support_program_rejects_multiple_distributors(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="too many distributors",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        distributor_ids=[uuid4(), uuid4()],
        created_by=employee_user.id,
    )
    with pytest.raises(InvalidSupportProgramError, match="только одного"):
        await handle_create_support_program(cmd, db_session)


async def test_create_support_program_rejects_unknown_leasing_company(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="bad",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        distributor_id=_company_id(distributor),
        leasing_company_ids=[uuid4()],
        created_by=employee_user.id,
    )
    with pytest.raises(LeasingCompanyNotFoundError):
        await handle_create_support_program(cmd, db_session)


async def test_create_support_program_rejects_unknown_dealer_group(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="bad",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        distributor_id=_company_id(distributor),
        dealer_group_ids=[uuid4()],
        created_by=employee_user.id,
    )
    with pytest.raises(DealerGroupNotFoundError):
        await handle_create_support_program(cmd, db_session)


async def test_create_support_program_rejects_invalid_type(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    cmd = CreateSupportProgramCommand(
        name="bad",
        mark_id=mark_bmw.id,
        support_type="bogus",
        support_params={"value_type": "amount", "value": 1000},
        distributor_id=_company_id(distributor),
        created_by=employee_user.id,
    )
    with pytest.raises(InvalidSupportProgramError):
        await handle_create_support_program(cmd, db_session)


async def test_update_support_program_replaces_relations(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    leasing_company: LeasingCompany,
    distributor: Distributor,
) -> None:
    create = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="orig",
            mark_id=mark_bmw.id,
            support_type="leasing_interest_compensation",
            support_params={"value_type": "percent", "value": 1.5},
            distributor_id=_company_id(distributor),
            leasing_company_ids=[leasing_company.id],
            created_by=employee_user.id,
        ),
        db_session,
    )

    updated = await handle_update_support_program(
        UpdateSupportProgramCommand(
            program_id=create["id"],
            name="updated",
            mark_id=mark_bmw.id,
            support_type="leasing_interest_compensation",
            support_params={"value_type": "percent", "value": 2.0},
            distributor_id=_company_id(distributor),
            leasing_company_ids=[],
        ),
        db_session,
    )
    assert updated["name"] == "updated"
    assert updated["leasing_company_ids"] == []
    assert updated["support_params"]["value"] == 2.0


async def test_compatibility_is_symmetric_in_create_get_and_list(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    second = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="second",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            created_by=employee_user.id,
        ),
        db_session,
    )
    first = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="first",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            compatible_support_ids=[second["id"]],
            created_by=employee_user.id,
        ),
        db_session,
    )

    assert first["compatible_support_ids"] == [second["id"]]
    second_read = await handle_get_support_program(
        GetSupportProgramQuery(program_id=second["id"]), db_session
    )
    assert second_read["compatible_support_ids"] == [first["id"]]
    listed = await handle_list_support_programs(
        ListSupportProgramsQuery(page=1, limit=20), db_session
    )
    by_id = {item["id"]: item for item in listed["support_programs"]}
    assert by_id[first["id"]]["compatible_support_ids"] == [second["id"]]
    assert by_id[second["id"]]["compatible_support_ids"] == [first["id"]]


async def test_update_compatibility_enables_selected_disabled_target(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    target = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="disabled target",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    source = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="source",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )

    updated = await handle_update_support_program(
        UpdateSupportProgramCommand(
            program_id=source["id"],
            name="source",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            compatible_support_ids=[target["id"]],
        ),
        db_session,
    )

    assert updated["compatible_support_ids"] == [target["id"]]
    target_read = await support_repository.get_program_by_id(
        db_session, target["id"]
    )
    assert target_read is not None
    assert target_read["is_compatible"] is True
    assert target_read["compatible_support_ids"] == [source["id"]]


async def test_compatibility_adjacency_reads_neighbors_from_both_columns(
    db_session: AsyncSession,
    mark_bmw: Mark,
) -> None:
    first_id = UUID("00000000-0000-0000-0000-000000000101")
    middle_id = UUID("00000000-0000-0000-0000-000000000102")
    last_id = UUID("00000000-0000-0000-0000-000000000103")
    programs = [
        SupportProgram(
            id=program_id,
            name=f"program-{program_id}",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            is_compatible=True,
        )
        for program_id in (first_id, middle_id, last_id)
    ]
    db_session.add_all(programs)
    await db_session.flush()
    db_session.add_all(
        [
            SupportProgramCompatibility(
                support_program_id=first_id,
                compatible_support_program_id=middle_id,
            ),
            SupportProgramCompatibility(
                support_program_id=middle_id,
                compatible_support_program_id=last_id,
            ),
        ]
    )
    await db_session.flush()

    adjacency = await support_repository.get_compatibility_by_program_ids(
        db_session, [first_id, middle_id, last_id]
    )
    assert adjacency == {
        first_id: {middle_id},
        middle_id: {first_id, last_id},
        last_id: {middle_id},
    }


async def test_create_compatibility_enables_selected_disabled_target(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    exclusive = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="exclusive",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    source = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="compatible source",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            compatible_support_ids=[exclusive["id"]],
            created_by=employee_user.id,
        ),
        db_session,
    )
    exclusive_read = await support_repository.get_program_by_id(
        db_session, exclusive["id"]
    )
    assert exclusive_read is not None
    assert exclusive_read["is_compatible"] is True
    assert exclusive_read["compatible_support_ids"] == [source["id"]]


async def test_leasing_company_program_lookup_requires_explicit_relation(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    leasing_company: LeasingCompany,
    distributor: Distributor,
) -> None:
    assigned = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="assigned to leasing company",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            leasing_company_ids=[leasing_company.id],
            created_by=employee_user.id,
        ),
        db_session,
    )
    unrestricted = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="without leasing company relation",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            leasing_company_ids=[],
            created_by=employee_user.id,
        ),
        db_session,
    )

    matched = await support_repository.get_program_ids_for_leasing_company(
        db_session,
        leasing_company.id,
        [assigned["id"], unrestricted["id"]],
    )

    assert matched == {assigned["id"]}


async def test_update_compatibility_rejects_self_link(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    created = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="self link",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            created_by=employee_user.id,
        ),
        db_session,
    )
    with pytest.raises(InvalidSupportProgramError, match="сама с собой"):
        await handle_update_support_program(
            UpdateSupportProgramCommand(
                program_id=created["id"],
                name="self link",
                mark_id=mark_bmw.id,
                support_type="down_payment_compensation",
                support_params={"value_type": "amount", "value": 1},
                distributor_id=_company_id(distributor),
                is_compatible=True,
                compatible_support_ids=[created["id"]],
            ),
            db_session,
        )


async def test_update_disabling_compatibility_clears_both_sides(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    neighbor = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="neighbor",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            created_by=employee_user.id,
        ),
        db_session,
    )
    source = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="source",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=True,
            compatible_support_ids=[neighbor["id"]],
            created_by=employee_user.id,
        ),
        db_session,
    )

    cleared = await handle_update_support_program(
        UpdateSupportProgramCommand(
            program_id=source["id"],
            name="source",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=_company_id(distributor),
            is_compatible=False,
            compatible_support_ids=[],
        ),
        db_session,
    )
    assert cleared["is_compatible"] is False
    assert cleared["compatible_support_ids"] == []
    neighbor_read = await support_repository.get_program_by_id(
        db_session, neighbor["id"]
    )
    assert neighbor_read is not None
    assert neighbor_read["compatible_support_ids"] == []


async def test_hard_delete_program_clears_incident_compatibility_pairs(
    db_session: AsyncSession,
    mark_bmw: Mark,
) -> None:
    first = SupportProgram(
        name="delete-first",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1},
        is_compatible=True,
    )
    second = SupportProgram(
        name="delete-second",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1},
        is_compatible=True,
    )
    db_session.add_all([first, second])
    await db_session.flush()
    left_id, right_id = sorted((first.id, second.id))
    db_session.add(
        SupportProgramCompatibility(
            support_program_id=left_id,
            compatible_support_program_id=right_id,
        )
    )
    await db_session.flush()

    assert await support_repository.delete_program(db_session, first.id)
    assert await support_repository.list_compatible_support_ids(
        db_session, second.id
    ) == []


async def test_get_support_program_raises_for_missing(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(SupportProgramNotFoundError):
        await handle_get_support_program(
            GetSupportProgramQuery(program_id=uuid4()), db_session
        )


async def test_delete_support_program_soft_deactivates(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    created = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="to deactivate",
            mark_id=mark_bmw.id,
            support_type="vehicle_discount_dealer_invoice",
            support_params={"value_type": "amount", "value": 1000},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    await handle_delete_support_program(
        DeleteSupportProgramCommand(program_id=created["id"]), db_session
    )
    after = await handle_get_support_program(
        GetSupportProgramQuery(program_id=created["id"]), db_session
    )
    assert after["is_active"] is False


async def test_list_support_programs_pagination(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    for i in range(3):
        await handle_create_support_program(
            CreateSupportProgramCommand(
                name=f"P{i}",
                mark_id=mark_bmw.id,
                support_type="down_payment_compensation",
                support_params={"value_type": "amount", "value": 1},
                distributor_id=_company_id(distributor),
                created_by=employee_user.id,
            ),
            db_session,
        )
    result = await handle_list_support_programs(
        ListSupportProgramsQuery(page=1, limit=2), db_session
    )
    assert result["pagination"]["total"] >= 3
    assert len(result["support_programs"]) == 2


async def test_distributor_scope_lists_legacy_and_m2m_programs_only(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    """A distributor can only read programs attached to its company."""
    visible_company_id = _company_id(distributor)
    foreign_company = Company(
        name="Foreign support distributor",
        inn="7700000199",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(foreign_company)
    await db_session.flush()

    legacy_program = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="Visible legacy program",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 1},
            distributor_id=visible_company_id,
            created_by=employee_user.id,
        ),
        db_session,
    )
    m2m_program = SupportProgram(
        name="Visible M2M program",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1},
        is_active=True,
    )
    foreign_program = SupportProgram(
        name="Foreign program",
        mark_id=mark_bmw.id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1},
        distributor_id=foreign_company.id,
        is_active=True,
    )
    db_session.add_all([m2m_program, foreign_program])
    await db_session.flush()
    db_session.add(
        SupportProgramDistributor(
            support_program_id=m2m_program.id,
            distributor_id=visible_company_id,
        )
    )
    await db_session.flush()

    result = await handle_list_support_programs(
        ListSupportProgramsQuery(
            actor_id=employee_user.id,
            actor_role="distributor",
            actor_company_id=visible_company_id,
            page=1,
            limit=20,
        ),
        db_session,
    )

    assert result["pagination"]["total"] == 2
    assert {item["id"] for item in result["support_programs"]} == {
        legacy_program["id"],
        m2m_program.id,
    }
    with pytest.raises(SupportProgramNotFoundError):
        await handle_get_support_program(
            GetSupportProgramQuery(
                program_id=foreign_program.id,
                actor_id=employee_user.id,
                actor_role="distributor",
                actor_company_id=visible_company_id,
            ),
            db_session,
        )


# ---------------------------------------------------------------------------
# Bill of lading
# ---------------------------------------------------------------------------


async def test_upload_bill_of_lading_persists_file(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    program = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="x",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 100},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    storage = FakeObjectStorage()
    result = await handle_upload_bill_of_lading(
        UploadBillOfLadingCommand(
            program_id=program["id"],
            file=UploadedBillOfLadingFile(
                filename="bol.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4 test",
            ),
            comment="ok",
        ),
        db_session,
        storage,
    )
    assert result["bill_of_lading"]["file_name"] == "bol.pdf"
    assert any("support-programs/" in key for key in storage.items)


async def test_upload_bill_of_lading_rejects_bad_extension(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    program = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="x",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 100},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    storage = FakeObjectStorage()
    with pytest.raises(InvalidUploadError):
        await handle_upload_bill_of_lading(
            UploadBillOfLadingCommand(
                program_id=program["id"],
                file=UploadedBillOfLadingFile(
                    filename="bad.txt",
                    content_type="text/plain",
                    data=b"hi",
                ),
            ),
            db_session,
            storage,
        )


async def test_delete_bill_of_lading_missing_raises(
    db_session: AsyncSession,
    employee_user: User,
    mark_bmw: Mark,
    distributor: Distributor,
) -> None:
    program = await handle_create_support_program(
        CreateSupportProgramCommand(
            name="x",
            mark_id=mark_bmw.id,
            support_type="down_payment_compensation",
            support_params={"value_type": "amount", "value": 100},
            distributor_id=_company_id(distributor),
            created_by=employee_user.id,
        ),
        db_session,
    )
    with pytest.raises(BillOfLadingFileNotFoundError):
        await handle_delete_bill_of_lading(
            DeleteBillOfLadingCommand(program_id=program["id"], file_id=uuid4()),
            db_session,
        )


# ---------------------------------------------------------------------------
# Dealer group handlers
# ---------------------------------------------------------------------------


async def test_create_dealer_group_persists_and_links_dealers(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    group = await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name="Group A",
            distributor_company_id=_company_id(distributor),
            description="desc",
            dealer_company_ids=[dealer_company.id],
            actor_id=employee_user.id,
        ),
        db_session,
    )
    assert group["id"] is not None
    assert group["dealer_company_ids"] == [dealer_company.id]
    assert group["dealers_count"] == 1


async def test_create_dealer_group_duplicate_name_raises(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name="dup",
            distributor_company_id=_company_id(distributor),
            dealer_company_ids=[dealer_company.id],
            actor_id=employee_user.id,
        ),
        db_session,
    )
    with pytest.raises(DealerGroupAlreadyExistsError):
        await handle_create_dealer_group(
            CreateDealerGroupCommand(
                name="DUP",
                distributor_company_id=_company_id(distributor),
                dealer_company_ids=[dealer_company.id],
                actor_id=employee_user.id,
            ),
            db_session,
        )


async def test_create_dealer_group_duplicate_dealer_raises(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    with pytest.raises(
        InvalidDealerGroupError,
        match="Повторяющиеся дилеры",
    ):
        await handle_create_dealer_group(
            CreateDealerGroupCommand(
                name="duplicate dealer",
                distributor_company_id=_company_id(distributor),
                dealer_company_ids=[dealer_company.id, dealer_company.id],
                actor_id=employee_user.id,
            ),
            db_session,
        )


async def test_create_dealer_group_rejects_dealer_not_linked_to_distributor(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
) -> None:
    company = Company(
        name="Unlinked Dealer Company",
        inn="7700000199",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    with pytest.raises(
        InvalidDealerGroupError, match="Дилер не входит в дилерскую сеть дистрибьютора"
    ):
        await handle_create_dealer_group(
            CreateDealerGroupCommand(
                name="unlinked",
                distributor_company_id=_company_id(distributor),
                dealer_company_ids=[company.id],
                actor_id=employee_user.id,
            ),
            db_session,
        )


async def test_create_dealer_group_rejects_missing_dealer_company(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
) -> None:
    missing_dealer_id = uuid4()

    with pytest.raises(
        DealerNotFoundError, match=f"Дилер {missing_dealer_id} не найден"
    ):
        await handle_create_dealer_group(
            CreateDealerGroupCommand(
                name="missing dealer",
                distributor_company_id=_company_id(distributor),
                dealer_company_ids=[missing_dealer_id],
                actor_id=employee_user.id,
            ),
            db_session,
        )


async def test_delete_dealer_group_soft_deactivates_and_keeps_members(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    group = await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name="soft delete group",
            distributor_company_id=_company_id(distributor),
            dealer_company_ids=[dealer_company.id],
            actor_id=employee_user.id,
        ),
        db_session,
    )

    await handle_delete_dealer_group(
        DeleteDealerGroupCommand(group_id=group["id"], actor_id=employee_user.id),
        db_session,
    )

    after = await handle_get_dealer_group(
        GetDealerGroupQuery(group_id=group["id"]), db_session
    )
    assert after is not None
    assert after["is_active"] is False
    assert after["dealer_company_ids"] == [dealer_company.id]
    assert after["updated_by"] == employee_user.id


async def test_list_dealer_groups_orders_active_before_inactive(
    db_session: AsyncSession,
    employee_user: User,
    distributor: Distributor,
    dealer_company: Company,
) -> None:
    active = await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name="active group",
            distributor_company_id=_company_id(distributor),
            dealer_company_ids=[dealer_company.id],
            actor_id=employee_user.id,
        ),
        db_session,
    )
    inactive = await handle_create_dealer_group(
        CreateDealerGroupCommand(
            name="inactive group",
            distributor_company_id=_company_id(distributor),
            dealer_company_ids=[dealer_company.id],
            actor_id=employee_user.id,
        ),
        db_session,
    )
    await handle_delete_dealer_group(
        DeleteDealerGroupCommand(group_id=inactive["id"], actor_id=employee_user.id),
        db_session,
    )

    result = await handle_list_dealer_groups(
        ListDealerGroupsQuery(page=1, limit=10), db_session
    )

    assert [item["id"] for item in result["dealer_groups"]] == [
        active["id"],
        inactive["id"],
    ]
