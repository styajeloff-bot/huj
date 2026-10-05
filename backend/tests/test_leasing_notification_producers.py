"""Business commands publish immutable notification facts in their transaction."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_applications.assign_leasing_companies import (
    AssignLeasingCompaniesToApplicationCommand,
    handle_assign_leasing_companies_to_application,
)
from application.commands.application_vehicles.dealer_action import (
    DealerVehicleActionCommand,
    handle_dealer_vehicle_action,
)
from application.commands.applications import change_status
from application.commands.documents.upload_document import UploadedDocumentFile
from application.commands.documents.upload_for_application import (
    UploadDocumentForApplicationCommand,
    handle_upload_document_for_application,
)
from application.commands.leasing.issue_application import (
    IssueApplicationCommand,
    handle_issue_application,
)
from application.commands.leasing.request_documents import (
    RequestDocumentsCommand,
    RequestedDocument,
    handle_request_documents,
)
from application.commands.leasing.take_in_work import (
    TakeInWorkCommand,
    handle_take_in_work,
)
from application.commands.leasing_applications_lc.change_status import (
    ChangeLeasingAppStatusCommand,
    handle_change_leasing_app_status,
)
from application.commands.leasing_response import (
    SubmitDecisionCommand,
    handle_submit_decision,
)
from application.commands.leasing_response_client_decision import (
    ClientProposalDecisionCommand,
    handle_client_proposal_decision,
)
from application.commands.select_leasing_company import (
    SelectLeasingCompanyCommand,
    handle_select_leasing_company,
)
from application.notifications.leasing_deadlines import (
    scan_leasing_reservation_deadlines,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import DocumentType
from infrastructure.models.notification_delivery import NotificationEventOutbox
from infrastructure.models.users import User
from tests.fakes.object_storage import FakeObjectStorage


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_role,old_status,new_status,kind", [
    ("client", "active", "rejected", "application_cancelled"),
    ("carcraft_employee", "active", "issued", "application_finalized"),
    ("carcraft_employee", "issued", "rejected", "application_finalized"),
    ("carcraft_employee", "rejected", "active", "application_status_changed"),
])
async def test_root_status_transition_records_one_semantic_event(
    db_session: AsyncSession, actor_role: str, old_status: str, new_status: str, kind: str,
) -> None:
    company = Company(name="Notification producer client", company_type="other")
    db_session.add(company)
    await db_session.flush()
    user = User(
        phone=f"+7{uuid4().int % 10**16:016d}", role=actor_role,
        company_id=company.id, is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    application = LeasingApplication(
        company_id=company.id, created_by=user.id, status=old_status,
        display_number=f"N-{uuid4().hex[:10]}",
    )
    db_session.add(application)
    await db_session.flush()
    result = await change_status.handle_change_status(
        change_status.ChangeStatusCommand(
            application_id=application.id, actor_id=user.id,
            actor_role=actor_role, actor_company_id=company.id,
            new_status=new_status,
        ), db_session,
    )

    assert result["application"]["status"] == new_status
    events = await _events(db_session, application.id)
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == f"leasing.{kind}"
    assert event["previous_values"] == {"status": old_status}
    assert event["new_values"] == {"status": new_status}
    assert event["application_id"] == str(application.id)
    assert event["request_number"] == application.display_number


async def _events(session: AsyncSession, application_id: UUID) -> list[dict]:
    rows = await session.scalars(
        sa.select(NotificationEventOutbox)
        .where(NotificationEventOutbox.aggregate_id == application_id)
        .order_by(NotificationEventOutbox.sequence)
    )
    return [row.payload for row in rows]


async def _leasing_graph(session: AsyncSession) -> tuple[
    LeasingApplication, User, LeasingCompany, User, LeasingCompanyApplication,
]:
    buyer = Company(name="Buyer", company_type="other")
    lender = Company(name="Lender", company_type="leasing_company")
    session.add_all([buyer, lender])
    await session.flush()
    client = User(phone=f"+7{uuid4().int % 10**16:016d}", role="client", company_id=buyer.id)
    lender_user = User(phone=f"+7{uuid4().int % 10**16:016d}", role="leasing_company", company_id=lender.id)
    lc = LeasingCompany(company_id=lender.id, is_active=True)
    session.add_all([client, lender_user, lc])
    await session.flush()
    application = LeasingApplication(
        company_id=buyer.id, created_by=client.id, status="active",
        display_number=f"N-{uuid4().hex[:10]}", selected_leasing_companies=[lc.id],
    )
    session.add(application)
    await session.flush()
    link = LeasingCompanyApplication(
        application_id=application.id, leasing_company_id=lc.id, status="under_review",
    )
    session.add(link)
    await session.flush()
    return application, client, lc, lender_user, link


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,expected_status", [
    ("preliminary", "approved_scoring"), ("final", "approved_final"),
])
async def test_submitted_decision_and_acceptance_keep_the_proposal_author(
    db_session: AsyncSession, kind: str, expected_status: str,
) -> None:
    app, client, lc, lc_user, link = await _leasing_graph(db_session)
    previous_status = "under_review" if kind == "preliminary" else "approved_scoring"
    link.status = previous_status
    proposal = LeasingProposal(
        leasing_company_application_id=link.id, kind=kind,
        total_amount=Decimal("1000000"), down_payment=Decimal("100000"),
        down_payment_percent=Decimal("10"), lease_term_months=36,
        monthly_payment=Decimal("30000"),
    )
    db_session.add(proposal)
    await db_session.flush()
    await handle_submit_decision(
        SubmitDecisionCommand(
            application_id=app.id, actor_user_id=lc_user.id,
            actor_leasing_company_id=lc.id, action="approve",
            decision_comment="Confidential comment not for outbox", kind=kind,
        ), db_session,
    )
    await handle_client_proposal_decision(
        ClientProposalDecisionCommand(
            application_id=app.id, proposal_id=proposal.id, actor_id=client.id,
            actor_role="client", actor_company_id=client.company_id, action="accepted",
        ), db_session,
    )
    events = await _events(db_session, app.id)
    assert [event["event_type"] for event in events] == [
        "leasing.company_decision_received", f"leasing.{kind}_offer_accepted",
    ]
    assert events[0]["previous_values"] == {"lca_status": previous_status}
    assert events[0]["new_values"] == {"lca_status": expected_status}
    assert events[1]["payload"]["proposal_id"] == str(proposal.id)
    assert events[1]["payload"]["leasing_company_id"] == str(lc.id)
    assert "Confidential" not in str(events)


@pytest.mark.asyncio
async def test_company_selection_records_distinct_selected_and_not_selected_facts(
    db_session: AsyncSession,
) -> None:
    app, client, lc, _, link = await _leasing_graph(db_session)
    link.status = "approved_final"
    await db_session.flush()
    await handle_select_leasing_company(
        SelectLeasingCompanyCommand(
            application_id=app.id, lca_id=link.id, actor_id=client.id,
            actor_role="client", actor_company_id=client.company_id,
        ), db_session,
    )
    events = await _events(db_session, app.id)
    assert [event["event_type"] for event in events] == [
        "leasing.company_selected", "leasing.company_not_selected",
    ]
    assert all(event["payload"]["selected_leasing_company_id"] == str(lc.id) for event in events)


@pytest.mark.asyncio
async def test_rejected_legacy_reserve_does_not_publish_false_reservation(
    db_session: AsyncSession,
) -> None:
    app, _, _, _, _ = await _leasing_graph(db_session)
    dealer_company = Company(name="Reservation seller", company_type="dealer", is_active=True)
    db_session.add(dealer_company)
    await db_session.flush()
    dealer = User(phone=f"+7{uuid4().int % 10**16:016d}", role="dealer", company_id=dealer_company.id, is_active=True)
    db_session.add(dealer)
    vehicle = ApplicationVehicle(application_id=app.id, dealer_company_id=dealer_company.id, quantity=1, unit_price=100, total_price=100)
    db_session.add(vehicle)
    await db_session.flush()
    expiry = (datetime.now(UTC) + timedelta(days=1)).date()
    command = DealerVehicleActionCommand(
        application_vehicle_id=vehicle.id, actor_id=dealer.id,
        actor_role="dealer", actor_company_id=dealer_company.id,
        action="reserve", reserve_expires_at=expiry,
    )
    from domain.errors import ApplicationVehicleFulfillmentRequiredError
    with pytest.raises(ApplicationVehicleFulfillmentRequiredError, match="Подберите автомобили"):
        await handle_dealer_vehicle_action(command, db_session)
    assert await _events(db_session, app.id) == []
    command.action = "reject"
    await handle_dealer_vehicle_action(command, db_session)
    events = await _events(db_session, app.id)
    assert [event["event_type"] for event in events] == [
        "leasing.vehicle_cancelled",
    ]
    assert events[0]["previous_values"]["car_status"] == "active"
    assert events[0]["new_values"]["car_status"] == "not_confirmed"
    assert events[0]["payload"]["application_vehicle_id"] == str(vehicle.id)
    assert events[0]["entity_id"] == str(app.id)


@pytest.mark.asyncio
async def test_expiry_and_outbox_rollback_together_then_sweep_is_idempotent(
    db_session: AsyncSession,
) -> None:
    app, _, _, _, _ = await _leasing_graph(db_session)
    now = datetime.now(UTC)
    vehicle = ApplicationVehicle(
        application_id=app.id, quantity=1, unit_price=100, total_price=100,
        car_status="confirmed", reserve_expires_at=(now - timedelta(days=1)).date(),
    )
    db_session.add(vehicle)
    await db_session.flush()
    savepoint = await db_session.begin_nested()
    assert await scan_leasing_reservation_deadlines(db_session, now) == 1
    assert len(await _events(db_session, app.id)) == 1
    await savepoint.rollback()
    assert await _events(db_session, app.id) == []
    assert await scan_leasing_reservation_deadlines(db_session, now) == 1
    assert await scan_leasing_reservation_deadlines(db_session, now) == 0
    events = await _events(db_session, app.id)
    assert len(events) == 1
    assert events[0]["event_type"] == "leasing.vehicle_reservation_expired"
    assert events[0]["new_values"] == {"car_status": "active", "reserve_expires_at": None}


@pytest.mark.asyncio
async def test_repeated_assignment_has_only_one_event_per_actual_lca_link(
    db_session: AsyncSession,
) -> None:
    app, client, lc, _, _ = await _leasing_graph(db_session)
    new_company = Company(name="New lender", company_type="leasing_company")
    db_session.add(new_company)
    await db_session.flush()
    new_lc = LeasingCompany(company_id=new_company.id, is_active=True)
    db_session.add(new_lc)
    await db_session.flush()
    command = AssignLeasingCompaniesToApplicationCommand(
        application_id=app.id, leasing_company_ids=[lc.id, new_lc.id], actor_id=client.id,
    )
    await handle_assign_leasing_companies_to_application(command, db_session)
    await handle_assign_leasing_companies_to_application(command, db_session)
    events = await _events(db_session, app.id)
    assert len(events) == 1
    assert events[0]["event_type"] == "leasing.company_assigned"
    assert events[0]["payload"]["leasing_company_id"] == str(new_lc.id)


@pytest.mark.asyncio
async def test_requested_upload_targets_only_requesting_leasing_company(
    db_session: AsyncSession,
) -> None:
    app, client, lc, lc_user, _ = await _leasing_graph(db_session)
    db_session.add(
        DocumentType(
            name="Расшифровка",
            type_code="balance_detail",
            display_name="Расшифровка",
        )
    )
    await db_session.flush()
    request = await handle_request_documents(
        RequestDocumentsCommand(
            application_id=app.id, actor_user_id=lc_user.id,
            actor_role="leasing_company", actor_leasing_company_id=lc.id,
            requested_documents=[RequestedDocument(source="catalog", display_name="Расшифровка", document_type="balance_detail")],
        ), db_session,
    )
    request_id = request["items"][0]["id"]
    await handle_upload_document_for_application(
        UploadDocumentForApplicationCommand(
            actor_user_id=client.id, actor_company_id=client.company_id,
            actor_role="client", application_id=app.id, document_type="balance_detail",
            document_request_id=request_id,
            idempotency_key="ee459049-55bb-427d-9e67-d732b0a2c6d0",
            file=UploadedDocumentFile(filename="balance.pdf", content_type="application/pdf", data=b"%PDF-test"),
        ), db_session, FakeObjectStorage(),
    )
    events = await _events(db_session, app.id)
    assert [event["event_type"] for event in events] == [
        "leasing.documents_requested", "leasing.documents_uploaded",
    ]
    assert events[0]["payload"]["request_batch_id"] == str(request["request_batch_id"])
    assert events[1]["payload"]["document_request_id"] == str(request_id)
    assert events[1]["payload"]["request_batch_id"] == str(request["request_batch_id"])
    assert events[1]["payload"]["leasing_company_id"] == str(lc.id)
    assert events[1]["previous_values"] == {"document_status": "requested"}
    assert events[1]["new_values"] == {"document_status": "provided"}


@pytest.mark.asyncio
async def test_issue_replay_does_not_emit_duplicate_finalization(
    db_session: AsyncSession,
) -> None:
    app, _, lc, lc_user, link = await _leasing_graph(db_session)
    link.status = "approved_final"
    db_session.add(LeasingProposal(
        leasing_company_application_id=link.id, kind="final",
        total_amount=Decimal("1000000"), down_payment=Decimal("100000"),
        down_payment_percent=Decimal("10"), lease_term_months=36,
        monthly_payment=Decimal("30000"), client_decision_action="accepted",
    ))
    await db_session.flush()
    command = IssueApplicationCommand(
        application_id=app.id, actor_user_id=lc_user.id,
        actor_leasing_company_id=lc.id,
    )
    first = await handle_issue_application(command, db_session)
    replay = await handle_issue_application(command, db_session)
    assert not first["replayed"] and replay["replayed"]
    events = await _events(db_session, app.id)
    assert len(events) == 1
    assert events[0]["event_type"] == "leasing.application_finalized"
    assert events[0]["previous_values"] == {"status": "active"}
    assert events[0]["new_values"] == {"status": "issued"}


@pytest.mark.asyncio
async def test_take_in_work_replay_and_admin_decision_have_distinct_facts(
    db_session: AsyncSession,
) -> None:
    app, _, lc, lc_user, link = await _leasing_graph(db_session)
    link.status = "submitted"
    await db_session.flush()
    command = TakeInWorkCommand(
        application_id=app.id, actor_user_id=lc_user.id, actor_leasing_company_id=lc.id,
    )
    await handle_take_in_work(command, db_session)
    await handle_take_in_work(command, db_session)
    await handle_change_leasing_app_status(
        ChangeLeasingAppStatusCommand(
            link_id=link.id, actor_user_id=lc_user.id, actor_role="carcraft_employee",
            new_status="approved_scoring",
        ), db_session,
    )
    events = await _events(db_session, app.id)
    assert [event["event_type"] for event in events] == [
        "leasing.application_status_changed", "leasing.company_decision_received",
    ]
    assert events[0]["previous_values"] == {"lca_status": "submitted"}
    assert events[0]["new_values"] == {"lca_status": "under_review"}
    assert events[1]["previous_values"] == {"lca_status": "under_review"}
    assert events[1]["new_values"] == {"lca_status": "approved_scoring"}
