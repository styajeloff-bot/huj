from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands import employees
from application.commands.employees import (
    InviteEmployeeCommand,
    RemoveCompanyMemberCommand,
    UpdateEmployeePermissionsCommand,
    UpdateEmployeeSubRoleCommand,
    handle_invite_employee,
    handle_remove_company_member,
    handle_update_employee_permissions,
    handle_update_employee_sub_role,
)
from application.errors import ServiceError
from infrastructure.models.companies import Company
from infrastructure.models.users import User, UserCompany
from presentation.schemas.users import InviteEmployeeRequest

pytestmark = pytest.mark.asyncio


async def test_invite_employee_request_accepts_formatted_phone() -> None:
    request = InviteEmployeeRequest(phone="8 (666) 000-80-16")

    assert request.phone == "8 (666) 000-80-16"


async def _company(db_session: AsyncSession) -> Company:
    company = Company(name="Sub Role Co", inn="7711334455", company_type="other")
    db_session.add(company)
    await db_session.flush()
    return company


async def _distributor_company(db_session: AsyncSession, name: str) -> Company:
    company = Company(name=name, inn=None, company_type="distributor")
    db_session.add(company)
    await db_session.flush()
    return company


async def _user(
    db_session: AsyncSession,
    *,
    phone: str,
    role: str = "client",
    company_id: UUID | None = None,
) -> User:
    user = User(
        phone=phone,
        email=f"{phone[-4:]}@test.local",
        name=f"User {phone[-4:]}",
        role=role,
        company_id=company_id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _link(
    db_session: AsyncSession,
    user: User,
    company: Company,
    *,
    sub_role: str,
    can_view: bool,
    can_create: bool,
) -> UserCompany:
    link = UserCompany(
        user_id=user.id,
        company_id=company.id,
        sub_role=sub_role,
        can_view_applications=can_view,
        can_create_applications=can_create,
    )
    db_session.add(link)
    await db_session.flush()
    return link


async def test_invite_new_user_normalizes_phone_and_links_blocked_employee(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(employees, "_fire_invite_sms", lambda phone, token: None)
    company = await _company(db_session)
    admin = await _user(db_session, phone="+76660008001", company_id=company.id)
    await _link(
        db_session,
        admin,
        company,
        sub_role="administrator",
        can_view=True,
        can_create=True,
    )

    await handle_invite_employee(
        InviteEmployeeCommand(
            actor_user_id=admin.id,
            company_id=company.id,
            phone="8 (666) 000-80-02",
        ),
        db_session,
    )

    invited = (
        await db_session.execute(select(User).where(User.phone == "+76660008002"))
    ).scalars().one()
    link = await db_session.get(UserCompany, (invited.id, company.id))
    assert link is not None
    assert link.sub_role == "employee"
    assert link.can_view_applications is False
    assert link.can_create_applications is False


async def test_invite_employee_rejects_invalid_normalized_phone(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(employees, "_fire_invite_sms", lambda phone, token: None)
    company = await _company(db_session)
    admin = await _user(db_session, phone="+76660008012", company_id=company.id)
    await _link(
        db_session,
        admin,
        company,
        sub_role="administrator",
        can_view=True,
        can_create=True,
    )

    with pytest.raises(ServiceError):
        await handle_invite_employee(
            InviteEmployeeCommand(
                actor_user_id=admin.id,
                company_id=company.id,
                phone="12345",
            ),
            db_session,
        )


async def test_invite_existing_unlinked_user_sets_employee_defaults(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(employees, "_fire_invite_sms", lambda phone, token: None)
    company = await _company(db_session)
    manager = await _user(db_session, phone="+76660008003", company_id=company.id)
    target = await _user(db_session, phone="+76660008004")
    await _link(
        db_session,
        manager,
        company,
        sub_role="manager",
        can_view=True,
        can_create=True,
    )

    await handle_invite_employee(
        InviteEmployeeCommand(
            actor_user_id=manager.id,
            company_id=company.id,
            phone=target.phone,
        ),
        db_session,
    )

    link = await db_session.get(UserCompany, (target.id, company.id))
    assert link is not None
    assert link.sub_role == "employee"
    assert link.can_view_applications is False
    assert link.can_create_applications is False


async def test_employee_cannot_manage_members(db_session: AsyncSession) -> None:
    company = await _company(db_session)
    employee = await _user(db_session, phone="+76660008005", company_id=company.id)
    target = await _user(db_session, phone="+76660008006", company_id=company.id)
    await _link(
        db_session,
        employee,
        company,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )
    await _link(
        db_session,
        target,
        company,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )

    with pytest.raises(ServiceError):
        await handle_update_employee_permissions(
            UpdateEmployeePermissionsCommand(
                actor_user_id=employee.id,
                company_id=company.id,
                target_user_id=target.id,
                can_view_applications=True,
            ),
            db_session,
        )
    with pytest.raises(ServiceError) as exc_info:
        await handle_remove_company_member(
            RemoveCompanyMemberCommand(
                actor_user_id=employee.id,
                company_id=company.id,
                target_user_id=target.id,
            ),
            db_session,
        )
    assert exc_info.value.status_code == 403
    assert str(exc_info.value) == "Доступ запрещён. Требуется роль администратора."



async def test_carcraft_employee_can_manage_any_company_members(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(employees, "_fire_invite_sms", lambda phone, token: None)
    company = await _company(db_session)
    staff = await _user(
        db_session,
        phone="+76660008016",
        role="carcraft_employee",
    )
    target = await _user(db_session, phone="+76660008017", company_id=company.id)
    await _link(
        db_session,
        target,
        company,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )

    members = await employees.handle_list_company_members(
        employees.ListCompanyMembersQuery(
            actor_user_id=staff.id,
            company_id=company.id,
            actor_role="carcraft_employee",
        ),
        db_session,
    )
    assert {member["phone"] for member in members} == {"+76660008017"}

    await handle_update_employee_permissions(
        UpdateEmployeePermissionsCommand(
            actor_user_id=staff.id,
            company_id=company.id,
            target_user_id=target.id,
            can_view_applications=True,
            can_create_applications=True,
            actor_role="carcraft_employee",
        ),
        db_session,
    )
    link = await db_session.get(UserCompany, (target.id, company.id))
    assert link is not None
    assert link.can_view_applications is True
    assert link.can_create_applications is True

    await handle_update_employee_sub_role(
        UpdateEmployeeSubRoleCommand(
            actor_user_id=staff.id,
            company_id=company.id,
            target_user_id=target.id,
            sub_role="manager",
            actor_role="carcraft_employee",
        ),
        db_session,
    )
    await db_session.refresh(link)
    assert link.sub_role == "manager"

    await handle_invite_employee(
        InviteEmployeeCommand(
            actor_user_id=staff.id,
            company_id=company.id,
            phone="+76660008018",
            actor_role="carcraft_employee",
        ),
        db_session,
    )
    invited = (
        await db_session.execute(select(User).where(User.phone == "+76660008018"))
    ).scalars().one()
    assert await db_session.get(UserCompany, (invited.id, company.id)) is not None


async def test_carcraft_employee_can_remove_company_member_link(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    staff = await _user(
        db_session,
        phone="+76660008019",
        role="carcraft_employee",
    )
    target = await _user(db_session, phone="+76660008020", company_id=company.id)
    await _link(
        db_session,
        target,
        company,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )

    await handle_remove_company_member(
        RemoveCompanyMemberCommand(
            actor_user_id=staff.id,
            company_id=company.id,
            target_user_id=target.id,
            actor_role="carcraft_employee",
        ),
        db_session,
    )

    assert await db_session.get(UserCompany, (target.id, company.id)) is None
    await db_session.refresh(target)
    assert target.company_id is None


async def test_manager_updates_permissions_but_only_admin_updates_sub_role(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    manager = await _user(db_session, phone="+76660008007", company_id=company.id)
    admin = await _user(db_session, phone="+76660008008", company_id=company.id)
    target = await _user(db_session, phone="+76660008009", company_id=company.id)
    await _link(db_session, manager, company, sub_role="manager", can_view=True, can_create=True)
    await _link(db_session, admin, company, sub_role="administrator", can_view=True, can_create=True)
    await _link(db_session, target, company, sub_role="employee", can_view=False, can_create=False)

    await handle_update_employee_permissions(
        UpdateEmployeePermissionsCommand(
            actor_user_id=manager.id,
            company_id=company.id,
            target_user_id=target.id,
            can_view_applications=True,
            can_create_applications=True,
        ),
        db_session,
    )
    link = await db_session.get(UserCompany, (target.id, company.id))
    assert link is not None
    assert link.can_view_applications is True
    assert link.can_create_applications is True

    with pytest.raises(ServiceError) as remove_exc:
        await handle_remove_company_member(
            RemoveCompanyMemberCommand(
                actor_user_id=manager.id,
                company_id=company.id,
                target_user_id=target.id,
            ),
            db_session,
        )
    assert remove_exc.value.status_code == 403
    assert str(remove_exc.value) == "Доступ запрещён. Требуется роль администратора."

    with pytest.raises(ServiceError):
        await handle_update_employee_sub_role(
            UpdateEmployeeSubRoleCommand(
                actor_user_id=manager.id,
                company_id=company.id,
                target_user_id=target.id,
                sub_role="manager",
            ),
            db_session,
        )

    await handle_update_employee_sub_role(
        UpdateEmployeeSubRoleCommand(
            actor_user_id=admin.id,
            company_id=company.id,
            target_user_id=target.id,
            sub_role="manager",
        ),
        db_session,
    )
    await db_session.refresh(link)
    assert link.sub_role == "manager"


async def test_admin_cannot_update_sub_role_for_unlinked_user(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    admin = await _user(db_session, phone="+76660008010", company_id=company.id)
    target = await _user(db_session, phone="+76660008011")
    await _link(db_session, admin, company, sub_role="administrator", can_view=True, can_create=True)

    with pytest.raises(ServiceError):
        await handle_update_employee_sub_role(
            UpdateEmployeeSubRoleCommand(
                actor_user_id=admin.id,
                company_id=company.id,
                target_user_id=target.id,
                sub_role="manager",
            ),
            db_session,
        )


async def test_list_company_members_scopes_to_selected_distributor_company(
    db_session: AsyncSession,
) -> None:
    distributor = await _distributor_company(db_session, "Distributor Team")
    other = await _distributor_company(db_session, "Other Distributor Team")
    admin = await _user(
        db_session,
        phone="+76660008013",
        role="distributor",
        company_id=distributor.id,
    )
    member = await _user(db_session, phone="+76660008014", role="distributor")
    outsider = await _user(db_session, phone="+76660008015", role="distributor")
    await _link(
        db_session,
        admin,
        distributor,
        sub_role="administrator",
        can_view=True,
        can_create=True,
    )
    await _link(
        db_session,
        member,
        distributor,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )
    await _link(
        db_session,
        outsider,
        other,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )

    members = await employees.handle_list_company_members(
        employees.ListCompanyMembersQuery(
            actor_user_id=admin.id,
            company_id=distributor.id,
        ),
        db_session,
    )

    phones = {member["phone"] for member in members}
    assert phones == {"+76660008013", "+76660008014"}


async def test_list_company_members_includes_primary_company_member_with_admin_defaults(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    staff = await _user(
        db_session,
        phone="+76660008021",
        role="carcraft_employee",
    )
    primary_member = await _user(
        db_session,
        phone="+76660008022",
        company_id=company.id,
    )

    members = await employees.handle_list_company_members(
        employees.ListCompanyMembersQuery(
            actor_user_id=staff.id,
            company_id=company.id,
            actor_role="carcraft_employee",
        ),
        db_session,
    )

    assert members == [
        {
            "user_id": str(primary_member.id),
            "name": primary_member.name,
            "phone": primary_member.phone,
            "sub_role": "administrator",
            "can_view_applications": True,
            "can_create_applications": True,
        }
    ]


async def test_list_company_members_prefers_user_company_link_over_primary_company_defaults(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)
    staff = await _user(
        db_session,
        phone="+76660008023",
        role="carcraft_employee",
    )
    member = await _user(
        db_session,
        phone="+76660008024",
        company_id=company.id,
    )
    await _link(
        db_session,
        member,
        company,
        sub_role="employee",
        can_view=False,
        can_create=False,
    )

    members = await employees.handle_list_company_members(
        employees.ListCompanyMembersQuery(
            actor_user_id=staff.id,
            company_id=company.id,
            actor_role="carcraft_employee",
        ),
        db_session,
    )

    assert members == [
        {
            "user_id": str(member.id),
            "name": member.name,
            "phone": member.phone,
            "sub_role": "employee",
            "can_view_applications": False,
            "can_create_applications": False,
        }
    ]
