#!/usr/bin/env python3
"""Opt-in follow-up fixtures and real requested-document transport acceptance.

Only synthetic rows in the separately owned local Compose are mutated. Business
actions use HTTP; Kafka consumers, the scheduler and SMTP remain real processes.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from runtime import Smoke, guard_runtime, load_state, progress, require, write_json


async def prepare(args: argparse.Namespace) -> None:
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    require("followup" not in state, "Follow-up fixture already exists; never overwrite its progress")
    from application.notifications.leasing_events import record_company_assignments
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import (
        ApplicationVehicle,
        LeasingApplication,
        LeasingCompanyApplication,
    )
    from infrastructure.models.companies import Company, LeasingCompany

    followup = {}
    async with AsyncSessionLocal() as session:
        other_company = Company(name="ТЗ35 follow-up другая ЛК", company_type="leasing_company", is_active=True)
        session.add(other_company)
        await session.flush()
        other_lc = LeasingCompany(company_id=other_company.id, is_active=True)
        session.add(other_lc)
        await session.flush()
        for kind in ("take", "take_final", "navigation", "grouping"):
            application_id = uuid4()
            number = f"TZ35-{kind}-{application_id.hex[:8]}"
            app = LeasingApplication(
                id=application_id, company_id=UUID(state["companies"]["buyer"]),
                dealer_company_id=UUID(state["companies"]["dealer"]),
                created_by=UUID(state["users"]["client"]["id"]), status="active",
                display_number=number, name="ТЗ35 follow-up acceptance",
                total_amount=Decimal("1000000"), down_payment=Decimal("200000"),
                down_payment_percent=Decimal("20"), lease_term_months=36,
                monthly_payment=Decimal("30000"),
                selected_leasing_companies=[UUID(state["leasing_company_id"])],
                storefront_id=UUID("00000000-0000-0000-0000-000000000001"),
            )
            session.add(app)
            await session.flush()
            session.add_all([
                ApplicationVehicle(application_id=app.id, vehicle_id=UUID(state["vehicle_id"]),
                    dealer_company_id=app.dealer_company_id, quantity=1,
                    unit_price=Decimal("1000000"), total_price=Decimal("1000000")),
                LeasingCompanyApplication(application_id=app.id,
                    leasing_company_id=UUID(state["leasing_company_id"]),
                    status="submitted" if kind.startswith("take") else "under_review"),
            ])
            if kind == "navigation":
                other_lca = LeasingCompanyApplication(application_id=app.id, leasing_company_id=other_lc.id,
                    status="approved_final")
                session.add(other_lca)
                await session.flush()
                followup["other_lca_id"] = str(other_lca.id)
            await session.flush()
            await record_company_assignments(session,
                application={"id": app.id, "display_number": number},
                leasing_company_ids=[UUID(state["leasing_company_id"])], actor_user_id=None)
            followup[f"{kind}_application_id"] = str(app.id)
            followup[f"{kind}_application_number"] = number
        await session.commit()
    state["followup"] = followup
    write_json(directory / "fixtures.secret.json", state)
    case = Smoke(args, directory, state)
    for kind in ("take", "take_final", "navigation", "grouping"):
        event = await case.event_after(0, "leasing.company_assigned", followup[f"{kind}_application_id"])
        await case.observe(event, {"leasing_company": "sent"})
        followup[f"{kind}_event_id"] = str(event["event_id"])
        write_json(directory / "fixtures.secret.json", state)
    progress("followup_prepared", applications=4)
    await navigation_notice(args)


async def navigation_notice(args: argparse.Namespace) -> None:
    """Emit the initial synthetic second-LC offer through the real outbox/Kafka.

    The first LC's later decisions remain real HTTP actions in the browser suite.
    This only supplies two distinct inbox identities for the same target step.
    """
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    case = Smoke(args, directory, state)
    app_id = state["followup"]["navigation_application_id"]
    lca_id = state["followup"]["other_lca_id"]
    from application.notifications.leasing_events import record_leasing_event
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication, LeasingCompanyApplication

    async with AsyncSessionLocal() as session:
        app = await session.get(LeasingApplication, UUID(app_id))
        lca = await session.get(LeasingCompanyApplication, UUID(lca_id))
        require(app is not None and app.name == "ТЗ35 follow-up acceptance"
            and str(app.company_id) == state["companies"]["buyer"], "Unexpected synthetic application")
        require(lca is not None and str(lca.application_id) == app_id and lca.status == "approved_final",
            "Only the initial synthetic second-LC offer can be announced")
        assert app is not None and lca is not None
        event_id = await record_leasing_event(session,
            application={"id": app.id, "display_number": app.display_number},
            event_type="leasing.company_decision_received", new_values={"lca_status": "approved_final"},
            payload={"leasing_company_id": lca.leasing_company_id, "leasing_company_application_id": lca.id, "proposal_kind": "final"},
            occurrence_key=f"tz35-navigation-fixture-final:{lca.id}")
        await session.commit()
    events = await case.query("SELECT event_id, sequence, payload FROM notification_event_outbox WHERE event_id=CAST(:id AS uuid)", id=str(event_id))
    require(len(events) == 1, "Missing synthetic offer outbox fact")
    await case.observe(events[0], dict.fromkeys(("client", "dealer", "distributor", "carcraft_employee"), "sent"))
    state["followup"]["other_final_event_id"] = str(event_id)
    write_json(directory / "fixtures.secret.json", state)
    progress("navigation_second_final_notice_ready")


async def context_prepare(args: argparse.Namespace) -> None:
    """Own new secondary-client/storefront rows; never switch the primary company."""
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    require("context_acceptance" not in state, "Context fixture already exists; never overwrite it")
    from application.notifications.leasing_events import record_leasing_event
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationVehicle, LeasingApplication, LeasingCompanyApplication
    from infrastructure.models.companies import Company
    from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
    from infrastructure.models.users import User, UserCompany

    fixture = {"marker": "tz35-context-acceptance", "applications": {}, "events": {}}
    async with AsyncSessionLocal() as session:
        user = await session.get(User, UUID(state["users"]["client"]["id"]))
        require(user is not None and user.email == "client@notifications35.test"
            and str(user.company_id) == state["companies"]["buyer"], "Unexpected primary client")
        company = Company(name="ТЗ35 context secondary client", company_type="other", is_active=True)
        storefront = Storefront(slug=f"tz35-context-{uuid4().hex[:12]}", is_default=False, is_active=True, version=1)
        session.add_all([company, storefront])
        await session.flush()
        session.add(UserCompany(user_id=user.id, company_id=company.id, sub_role="employee",
            can_view_applications=True, can_create_applications=True))
        session.add(StorefrontWarehouse(storefront_id=storefront.id, warehouse_id=UUID(state["warehouse_id"])))
        fixture.update(company_id=str(company.id), storefront_id=str(storefront.id), storefront_slug=storefront.slug)
        other = await session.get(LeasingCompanyApplication, UUID(state["followup"]["other_lca_id"]))
        require(other is not None, "Missing owned secondary LC fixture")
        for kind, status in (("preliminary", "approved_scoring"), ("documents", "under_review"), ("final", "approved_final")):
            app_id = uuid4()
            app = LeasingApplication(id=app_id, company_id=company.id,
                dealer_company_id=UUID(state["companies"]["dealer"]), created_by=user.id,
                status="active", display_number=f"TZ35-context-{kind}-{app_id.hex[:8]}",
                name="ТЗ35 context acceptance", storefront_id=storefront.id,
                total_amount=Decimal("1000000"), down_payment=Decimal("200000"),
                down_payment_percent=Decimal("20"), lease_term_months=36, monthly_payment=Decimal("30000"),
                selected_leasing_companies=[UUID(state["leasing_company_id"])])
            session.add(app)
            await session.flush()
            session.add(ApplicationVehicle(application_id=app.id, vehicle_id=UUID(state["vehicle_id"]),
                dealer_company_id=app.dealer_company_id, quantity=1, unit_price=Decimal("1000000"), total_price=Decimal("1000000")))
            lca = LeasingCompanyApplication(application_id=app.id, leasing_company_id=UUID(state["leasing_company_id"]), status=status)
            session.add(lca)
            await session.flush()
            fixture["applications"][kind] = str(app.id)
            if kind != "documents":
                for index, company_id in enumerate([lca.leasing_company_id] + ([other.leasing_company_id] if kind == "final" else [])):
                    branch = lca
                    if index:
                        branch = LeasingCompanyApplication(application_id=app.id, leasing_company_id=company_id, status=status)
                        session.add(branch)
                        await session.flush()
                    event_id = await record_leasing_event(session,
                        application={"id": app.id, "display_number": app.display_number},
                        event_type="leasing.company_decision_received", new_values={"lca_status": status},
                        payload={"leasing_company_id": company_id, "leasing_company_application_id": branch.id, "proposal_kind": kind},
                        occurrence_key=f"tz35-context-initial:{branch.id}")
                    fixture["events"][kind if not index else "final_other"] = str(event_id)
        await session.commit()
    state["context_acceptance"] = fixture
    write_json(directory / "fixtures.secret.json", state)
    case = Smoke(args, directory, state)
    documents_id = fixture["applications"]["documents"]
    await case.api("leasing_company", "PUT", f"/api/v1/leasing/applications/{documents_id}/request-documents",
        body={"requestedDocuments": [{"source": "custom", "display_name": "ТЗ35 context запрошенный документ"}]})
    event = await case.event_after(0, "leasing.documents_requested", documents_id)
    fixture["events"]["documents"] = str(event["event_id"])
    write_json(directory / "fixtures.secret.json", state)
    await context_observe(args)


async def context_observe(args: argparse.Namespace) -> None:
    # Observe the recipient's actual HTTP inbox; no materialized inbox rows are seeded.
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    fixture = state["context_acceptance"]
    require(fixture["marker"] == "tz35-context-acceptance", "Unexpected context marker")
    case = Smoke(args, directory, state)
    deadline = asyncio.get_running_loop().time() + case.args.timeout
    while asyncio.get_running_loop().time() < deadline:
        response = await case.api("client", "GET", "/api/v1/notifications?limit=100")
        received = {(item.get("data") or {}).get("event_id") for item in response["notifications"]}
        if set(fixture["events"].values()) <= received:
            progress("context_acceptance_ready", applications=3, events=4, primary_unchanged=True)
            return
        await asyncio.sleep(1)
    raise RuntimeError("Context fixture events did not reach the real client inbox")


async def context_permissions(args: argparse.Namespace) -> None:
    """Revoke/restore only the membership created by context_prepare."""
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    fixture = state["context_acceptance"]
    require(fixture["marker"] == "tz35-context-acceptance", "Unexpected context marker")
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from infrastructure.models.users import User, UserCompany
    async with AsyncSessionLocal() as session:
        user = await session.get(User, UUID(state["users"]["client"]["id"]))
        company = await session.get(Company, UUID(fixture["company_id"]))
        require(user is not None and user.email == "client@notifications35.test"
            and str(user.company_id) == state["companies"]["buyer"], "Primary client changed")
        require(company is not None and company.name == "ТЗ35 context secondary client"
            and company.id != user.company_id, "Not an owned secondary company")
        membership = await session.get(UserCompany, (user.id, company.id))
        require(membership is not None and membership.sub_role == "employee", "Not an owned fixture membership")
        membership.can_view_applications = args.mode == "context-restore"
        await session.commit()
    progress(args.mode, primary_unchanged=True)


async def upload(case: Smoke, app_id: str, request_id: str, index: int) -> None:
    import httpx
    async with httpx.AsyncClient(base_url=case.args.api_url, trust_env=False, timeout=30,
        cookies={"accessToken": case.state["users"]["client"]["access_token"]}) as client:
        response = await client.post("/api/v1/documents/", data={
            "application_id": app_id, "document_request_id": request_id,
        }, files={"files": (f"tz35-{index}.pdf", b"%PDF-1.4\n% synthetic TZ35 document\n%%EOF", "application/pdf")})
    require(response.status_code == 201, f"Fixture upload failed: {response.status_code}; {response.text[:500]}")


async def await_members(case: Smoke, app_id: str, count: int) -> list[dict]:
    deadline = asyncio.get_running_loop().time() + case.args.timeout
    while asyncio.get_running_loop().time() < deadline:
        groups = await case.query("SELECT g.id, g.first_upload_at, g.closes_at, g.closed_at, count(m.event_id) AS members "
            "FROM notification_document_upload_groups g JOIN notification_document_upload_members m ON m.group_id=g.id "
            "WHERE g.application_id=CAST(:id AS uuid) GROUP BY g.id ORDER BY g.first_upload_at", id=app_id)
        if sum(row["members"] for row in groups) == count:
            return groups
        await asyncio.sleep(1)
    raise RuntimeError("Timed out waiting for real consumer group membership")


async def age_group(case: Smoke, app_id: str, group_id: str) -> None:
    """Advance only fixture timestamps coherently; never modify production clocks."""
    from infrastructure.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as session:
        row = (await session.execute(text(
            "SELECT g.first_upload_at, g.closes_at, g.closed_at, a.name, a.company_id "
            "FROM notification_document_upload_groups g JOIN leasing_applications a ON a.id=g.application_id "
            "WHERE g.id=CAST(:group AS uuid) AND a.id=CAST(:app AS uuid) FOR UPDATE OF g"
        ), {"group": group_id, "app": app_id})).mappings().one()
        require(row["name"] == "ТЗ35 follow-up acceptance" and str(row["company_id"]) == case.state["companies"]["buyer"],
            "Cannot alter another application's timing")
        require(row["closed_at"] is None and row["closes_at"] - row["first_upload_at"] == timedelta(minutes=10),
            "Expected open fixed ten-minute group")
        shift = row["closes_at"] - datetime.now(UTC) + timedelta(seconds=2)
        await session.execute(text("UPDATE notification_document_upload_groups "
            "SET first_upload_at=first_upload_at-CAST(:shift AS interval), closes_at=closes_at-CAST(:shift AS interval) WHERE id=CAST(:id AS uuid)"),
            {"shift": shift, "id": group_id})
        await session.execute(text("UPDATE notification_document_upload_members SET occurred_at=occurred_at-CAST(:shift AS interval) "
            "WHERE group_id=CAST(:id AS uuid)"), {"shift": shift, "id": group_id})
        await session.commit()


async def await_summary(case: Smoke, group_id: str, count: int) -> dict:
    deadline = asyncio.get_running_loop().time() + case.args.timeout
    while asyncio.get_running_loop().time() < deadline:
        events = await case.query("SELECT event_id, sequence, payload FROM notification_event_outbox "
            "WHERE event_id=CAST(:id AS uuid) AND event_type='leasing.documents_uploads_summary'", id=group_id)
        if events:
            event = events[0]
            require(event["payload"]["payload"]["document_count"] == count, "Wrong distinct document count")
            await case.observe(event, {"leasing_company": "sent"})
            return event
        await asyncio.sleep(1)
    raise RuntimeError("Real scheduled finalizer did not publish the due group")


async def grouping(args: argparse.Namespace) -> None:
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    started = state["followup"].get("grouping_started")
    require(not state["followup"].get("grouping_completed"), "Grouping acceptance already completed")
    require(not started or args.resume, "Interrupted HTTP uploads require explicit --resume")
    state["followup"]["grouping_started"] = True
    write_json(directory / "fixtures.secret.json", state)
    case = Smoke(args, directory, state)
    app_id = state["followup"]["grouping_application_id"]
    if not started:
        requested = await case.api("leasing_company", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
            body={"requestedDocuments": [{"source": "custom", "display_name": f"ТЗ35 документ {i}"} for i in range(10)]})
        for index, item in enumerate(requested["items"]):
            await upload(case, app_id, item["id"], index)
    else:
        batches = await case.query("SELECT count(DISTINCT request_batch_id) AS count FROM application_document_requests "
            "WHERE application_id=CAST(:id AS uuid)", id=app_id)
        require(batches[0]["count"] == 1, "Resume only supports observation after the first ten uploads, before another request")
    groups = await await_members(case, app_id, 10)
    require(len(groups) == 1 and (args.resume or groups[0]["closed_at"] is None), "Ten uploads did not form one open group")
    require(groups[0]["closes_at"] - groups[0]["first_upload_at"] == timedelta(minutes=10), "Window changed or slid")
    individual = await case.query("SELECT n.id FROM notifications n JOIN notification_event_outbox e ON e.event_id=n.event_id "
        "WHERE e.aggregate_id=CAST(:app AS uuid) AND e.event_type='leasing.documents_uploaded'", app=app_id)
    require(not individual, "Individual upload notifications leaked before summary")
    files = await case.api("leasing_company", "GET", f"/api/v1/leasing/applications/{app_id}/documents")
    require(files["total"] == 10, "Requested files are not immediately visible to their LC")
    raw_events = await case.query("SELECT event_id, sequence, payload FROM notification_event_outbox "
        "WHERE aggregate_id=CAST(:app AS uuid) AND event_type='leasing.documents_uploaded' ORDER BY sequence", app=app_id)
    require(len(raw_events) == 10, "Raw upload audit facts were lost")
    await case.replay(raw_events[0])
    first_id = str(groups[0]["id"])
    if groups[0]["closed_at"] is None:
        await age_group(case, app_id, first_id)
    summary = await await_summary(case, first_id, 10)
    await case.replay(summary)
    # Preserve the real state machine: another document request is legal after
    # the LC publishes its preliminary decision, not directly after upload.
    await case.api("leasing_company", "PUT", f"/api/v1/leasing/applications/{app_id}/proposals/preliminary",
        body={"total_amount": "1000000", "down_payment": "200000", "down_payment_percent": "20",
            "lease_term_months": 36, "monthly_payment": "30000", "buyout_amount": "0"})
    await case.api("leasing_company", "PUT", f"/api/v1/leasing/applications/{app_id}/decision",
        body={"action": "approve", "kind": "preliminary"})
    next_request = await case.api("leasing_company", "PUT", f"/api/v1/leasing/applications/{app_id}/request-documents",
        body={"requestedDocuments": [{"source": "custom", "display_name": "ТЗ35 следующий документ"}]})
    await upload(case, app_id, next_request["items"][0]["id"], 10)
    groups = await await_members(case, app_id, 11)
    require(len(groups) == 2, "Upload in a new request batch must create an independent group")
    next_group = next(row for row in groups if row["closed_at"] is None)
    await age_group(case, app_id, str(next_group["id"]))
    await await_summary(case, str(next_group["id"]), 1)
    state["followup"]["grouping_completed"] = True
    write_json(directory / "fixtures.secret.json", state)
    write_json(directory / "followup-grouping-report.json", {
        "result": "PASS", "checks": case.report["checks"], "window_seconds": 600,
        "ten_uploads_one_summary": True, "new_request_batch_independent_summary": True,
        "files_available_before_notification": True,
        "clock_control": "Only exact synthetic group/member timestamps shifted; real scheduler/consumer/SMTP",
    })
    progress("followup_grouping_pass", window_seconds=600, uploads=11, summaries=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "grouping", "navigation-notice", "context-prepare", "context-observe", "context-revoke", "context-restore"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Resume observation of exactly ten existing fixture uploads; never repeat them")
    parser.set_defaults(state_dir="/runtime", backend_path="/app", api_url="http://nginx",
        smtp_api_url="http://smtp:8025", metrics_url="http://event-worker:8000/metrics", timeout=180)
    args = parser.parse_args()
    asyncio.run({"prepare": prepare, "grouping": grouping, "navigation-notice": navigation_notice,
        "context-prepare": context_prepare, "context-observe": context_observe,
        "context-revoke": context_permissions, "context-restore": context_permissions}[args.mode](args))


if __name__ == "__main__":
    main()
