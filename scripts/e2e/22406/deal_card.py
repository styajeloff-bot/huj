"""Guarded fixtures and real HTTP checks for task 22406 deal cards."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

sys.path.insert(0, "/e2e")
from runtime import API, ROOT, guard, identifier, private_json, program_payload, progress, require


def state():
    guard()
    return json.loads((ROOT / "state.secret.json").read_text())


async def seed():
    from domain.monetization.programs import calculate_program
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication, LeasingCompanyApplication
    from infrastructure.repositories import monetization_repository as repo

    api = API(state())
    run = uuid4().hex[:10]
    draft = program_payload("22406 dealer recipients " + run, active=True)
    draft["brand"] = "22406-RECIPIENTS-" + run
    source = draft["sources"][0]
    source["expenses"][0]["participant_type"] = "dealer"
    source["incomes"][0].update(participant_type="leasing")
    source["expenses"].append({"local_id": "expense-other", "participant_type": "leasing",
        "base_type": "property_value", "calc_type": "percent", "value": "1"})
    source["incomes"].append({"local_id": "income-other", "participant_type": "platform",
        "base_type": "expense_amount", "expense_ref": "expense-other", "calc_type": "percent", "value": "100"})
    created = await api.request("admin", "POST", "/api/v1/admin/monetization/programs", 201, json=draft)
    async with AsyncSessionLocal() as session:
        program = await repo.get_program(session, UUID(created["id"]))
        require(program, "Program missing")
        context = {
            "source_type": "platform", "application_id": uuid4(),
            "leasing_company_application_id": uuid4(), "application_number": "22406-" + run,
            "leasing_company_id": identifier("leasing-company"),
            "dealer_company_id": identifier("company/dealer"),
            "distributor_company_id": identifier("company/distributor"),
            "client_company_id": identifier("company/client"),
            "base_amount": Decimal("1000000"), "occurred_at": datetime.now(UTC),
            "vehicles": [{"vehicle_id": identifier("vehicle/ui"), "brand": draft["brand"], "quantity": 1}],
            "actor_user_id": identifier("user/admin"),
        }
        session.add(LeasingApplication(id=context["application_id"], company_id=identifier("company/client"),
            dealer_company_id=identifier("company/dealer"), created_by=identifier("user/admin"),
            source_type="platform", display_number=context["application_number"], total_amount=context["base_amount"]))
        await session.flush()
        session.add(LeasingCompanyApplication(id=context["leasing_company_application_id"],
            application_id=context["application_id"], leasing_company_id=identifier("leasing-company")))
        await session.flush()
        captured = await repo.insert_deal(session, context, program, calculate_program(program, context))
        await session.commit()
    main = json.loads((ROOT / "manifest.json").read_text())
    manifest = {
        "marker": "monetization-22406-deal-card", "base_url": main["base_url"],
        "storage_states": main["storage_states"], "deal_id": str(captured["id"]),
        "application_id": str(context["application_id"]), "application_number": context["application_number"],
        "leasing_company_id": str(identifier("leasing-company")), "companies": main["companies"],
        "exchange_deal_id": main["deal_id"], "exchange_request_id": str(identifier("request/ui")),
    }
    private_json(ROOT / "deal-card.manifest.json", manifest)
    await prepare_navigation()
    progress("deal_card_seeded", deal_id=manifest["deal_id"])


async def prepare_navigation():
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
    from infrastructure.models.exchange import ExchangeRequest, ExchangeRequestWarehouse
    from infrastructure.models.vehicles import Warehouse
    from infrastructure.models.companies import DistributorBrand
    from infrastructure.models.special_equipment import SpecialEquipmentProduct
    from infrastructure.models.support import DealerGroup, DealerGroupMember

    state()
    manifest = json.loads((ROOT / "deal-card.manifest.json").read_text())
    async with AsyncSessionLocal() as session:
        application_id = UUID(manifest["application_id"])
        application = await session.get(LeasingApplication, application_id)
        require(application and application.display_number.startswith("22406-"), "Unknown application fixture")
        vehicle = (await session.scalars(select(ApplicationVehicle).where(
            ApplicationVehicle.application_id == application_id))).first()
        if vehicle is None:
            session.add(ApplicationVehicle(application_id=application_id, product_id=identifier("vehicle/ui"),
                dealer_company_id=identifier("company/dealer"), quantity=1, unit_price=Decimal("1000000"),
                total_price=Decimal("1000000"), car_status="confirmed"))
        request = await session.get(ExchangeRequest, identifier("request/ui"))
        require(request and request.lc_user_id == identifier("user/leasing"), "Unknown exchange fixture")
        warehouse_id = identifier("22406/deal-card-warehouse")
        if await session.get(Warehouse, warehouse_id) is None:
            session.add(Warehouse(id=warehouse_id, name="22406 Test warehouse",
                address="22406 Synthetic warehouse", owner_company_id=identifier("company/dealer"),
                owner_company_type="dealer", is_active=True))
            await session.flush()
        product = await session.get(SpecialEquipmentProduct, identifier("vehicle/ui"))
        require(product and product.code == "22406-ui", "Unknown product fixture")
        product.warehouse_id = warehouse_id
        group_id = identifier("22406/deal-card-dealer-group")
        if await session.get(DealerGroup, group_id) is None:
            session.add(DealerGroup(id=group_id, name="22406 Navigation dealer group",
                distributor_company_id=identifier("company/distributor"), is_active=True,
                created_by=identifier("user/admin")))
            await session.flush()
            session.add(DealerGroupMember(dealer_group_id=group_id, dealer_company_id=identifier("company/dealer"),
                created_by=identifier("user/admin")))
        brand = (await session.scalars(select(DistributorBrand).where(
            DistributorBrand.distributor_company_id == identifier("company/distributor"),
            DistributorBrand.brand_id == identifier("catalog/mark"),
            DistributorBrand.is_active.is_(True)))).first()
        if brand is None:
            session.add(DistributorBrand(distributor_company_id=identifier("company/distributor"),
                brand_id=identifier("catalog/mark"), is_active=True))
        assignment = (await session.scalars(select(ExchangeRequestWarehouse).where(
            ExchangeRequestWarehouse.request_id == request.id,
            ExchangeRequestWarehouse.warehouse_id == warehouse_id))).first()
        if assignment is None:
            session.add(ExchangeRequestWarehouse(request_id=request.id, warehouse_id=warehouse_id,
                dealer_id=identifier("company/dealer")))
        await session.commit()
    progress("deal_card_navigation_seeded")


async def verify():
    from sqlalchemy import delete, select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.user_company_access import UserCompanySectionAccess
    from infrastructure.models.users import UserCompany

    api = API(state())
    manifest = json.loads((ROOT / "deal-card.manifest.json").read_text())
    path = "/api/v1/monetization/deals/" + manifest["deal_id"]
    admin = await api.request("admin", "GET", path)
    dealer = await api.request("dealer", "GET", path)
    require(len(dealer["expenses"]) == 1, "Dealer lost own expense")
    expense = dealer["expenses"][0]["id"]
    recipients = [row for row in admin["incomes"] if row["expense_ref_amount_id"] == expense]
    require(len(recipients) == 3, "Fixture must contain three recipients")
    require({row["id"] for row in dealer["incomes"]} == {row["id"] for row in recipients},
            "Dealer cannot see exactly the recipients funded by own expense")
    require(not dealer["can_adjust"], "Recipient visibility must not grant editing")
    page, summary = 1, None
    while summary is None:
        listing = await api.request("dealer", "GET", "/api/v1/monetization/deals",
            params={"page": page, "page_size": 100})
        summary = next((row for row in listing["items"] if row["id"] == manifest["deal_id"]), None)
        if page >= listing["pagination"]["total_pages"]:
            break
        page += 1
    require(summary is not None, "Dealer deal missing from paginated list")
    require(summary["income_participants"] == [], "Recipient income must not become dealer income in list")
    await api.request("outsider", "GET", path, 404)
    await api.request("dealer", "POST", "/api/v1/admin/monetization/deals/" + manifest["deal_id"] + "/adjust-conditions", 403, json={
        "revision": dealer["revision"], "items": [{"deal_participant_amount_id": recipients[0]["id"],
        "input_mode": "amount", "new_value": "1"}]})
    for role in ("leasing", "distributor"):
        visible = await api.request(role, "GET", path)
        participant = "leasing" if role == "leasing" else "distributor"
        require(all(row["participant_type"] == participant for row in visible["expenses"] + visible["incomes"]),
                "Other roles' projection must remain scoped")
    async with AsyncSessionLocal() as session:
        membership = (await session.scalars(select(UserCompany).where(
            UserCompany.user_id == identifier("user/dealer"),
            UserCompany.company_id == identifier("company/dealer")))).one()
        membership_id = membership.id
        existing = (await session.scalars(select(UserCompanySectionAccess).where(
            UserCompanySectionAccess.user_company_id == membership_id,
            UserCompanySectionAccess.section_code.in_(["monetization_income", "monetization_expense"])))).all()
        require(not existing, "Refusing to overwrite existing section access fixture")
    try:
        for hidden, expected_count in (("monetization_income", 3), ("monetization_expense", 0)):
            async with AsyncSessionLocal() as session:
                session.add(UserCompanySectionAccess(user_company_id=membership_id, section_code=hidden, can_view=False))
                await session.commit()
            visible = await api.request("dealer", "GET", path)
            require(len(visible["incomes"]) == expected_count, hidden + " must honor expense recipient scope")
            async with AsyncSessionLocal() as session:
                await session.execute(delete(UserCompanySectionAccess).where(
                    UserCompanySectionAccess.user_company_id == membership_id,
                    UserCompanySectionAccess.section_code == hidden))
                await session.commit()
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(UserCompanySectionAccess).where(
                UserCompanySectionAccess.user_company_id == membership_id,
                UserCompanySectionAccess.section_code.in_(["monetization_income", "monetization_expense"])))
            await session.commit()
    await api.request("distributor", "GET", "/api/v1/applications/" + manifest["application_id"])
    await api.request("distributor", "GET", "/api/v1/applications")
    await api.request("outsider", "GET", "/api/v1/applications/" + manifest["application_id"], 404)
    outsider_list = await api.request("outsider", "GET", "/api/v1/applications")
    require(not any(row["id"] == manifest["application_id"] for row in outsider_list["applications"]),
            "Unrelated distributor must not see the application")
    import httpx
    async with httpx.AsyncClient(base_url="http://backend:3002", trust_env=False) as anonymous:
        for endpoint in ("/api/v1/applications", "/api/v1/applications/" + manifest["application_id"]):
            response = await anonymous.get(endpoint)
            require(response.status_code == 401, "Unauthenticated application read must be denied")
    progress("deal_card_http_passed", checks="linked recipients, no unrelated rows, summaries, outsider, writes, role and section access, distributor application detail and list")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify", "navigation"])
    action = parser.parse_args().action
    asyncio.run({"seed": seed, "verify": verify, "navigation": prepare_navigation}[action]())
