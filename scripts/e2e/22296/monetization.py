"""Real HTTP fixtures for task 22296 monetization; isolated Docker database only."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from runtime import API, ROOT, guard, identifier, private_json, progress, require

HOST_ROOT = Path("/tmp/carcraft-22296-monetization")
PROGRAMS = "/api/v1/admin/monetization/programs"
LOOKUP = "/api/v1/monetization/lookups/companies"


def state():
    guard()
    return json.loads((ROOT / "state.secret.json").read_text())


def program_payload(actors, name, *, vin=None, expense=None, income=None):
    companies = actors["companies"]
    return {
        "name": name, "status": "active",
        "leasing_company_id": companies["leasing"]["leasing_company_id"],
        "dealer_company_id": companies["dealer"]["company_id"],
        "distributor_company_id": companies["distributor"]["company_id"],
        "vin": vin, "period_start": "2026-01-01", "period_end": "2030-12-31",
        "sources": [{
            "source_type": "exchange",
            "expenses": [{"local_id": "expense", "participant_type": "leasing",
                "base_type": "property_value", "calc_type": "percent",
                "value": "5", **(expense or {})}],
            "incomes": [{"local_id": "dealer-income", "participant_type": "dealer",
                "base_type": "expense_amount", "calc_type": "percent",
                "value": "30", "expense_ref": "expense", **(income or {})}],
        }],
    }


async def source_bid(actors, vin, name, batch, base="2403000"):
    """Only source setup uses ORM; program creation/capture/readback use real HTTP."""
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.exchange import ExchangeBid, ExchangeRequest
    from infrastructure.models.special_equipment import SpecialEquipmentModification, SpecialEquipmentProduct

    companies, users = actors["companies"], actors["users"]
    async with AsyncSessionLocal() as session:
        modification = SpecialEquipmentModification(id=uuid4(), code=name, slug=name,
            name=name, model_id=UUID(actors["catalog"]["model_id"]))
        session.add(modification)
        await session.flush()
        product = SpecialEquipmentProduct(id=uuid4(), code=name, slug=name,
            modification_id=modification.id,
            seller_company_id=UUID(companies["dealer"]["company_id"]),
            vin=vin, price=Decimal(base), condition="new")
        session.add(product)
        await session.flush()
        request = ExchangeRequest(id=uuid4(), lc_user_id=UUID(users["leasing"]["id"]),
            lc_company_id=UUID(companies["leasing"]["company_id"]), product_id=product.id,
            quantity=1, status="open", batch_number=batch, batch_index=1,
            expiration_at=datetime.now(UTC) + timedelta(days=1))
        session.add(request)
        await session.flush()
        bid = ExchangeBid(id=uuid4(), request_id=request.id,
            dealer_id=UUID(users["dealer"]["id"]),
            dealer_company_id=UUID(companies["dealer"]["company_id"]),
            price=Decimal(base), quantity=1, kp_status="accepted", is_accepted=False)
        session.add(bid)
        await session.commit()
        return {"bid_id": str(bid.id), "request_id": str(request.id),
                "application_number": f"{batch}-1"}


async def seed():
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company, DistributorDealerLink
    from infrastructure.models.support import DealerGroup, DealerGroupMember
    from infrastructure.models.users import UserCompany
    from infrastructure.models import monetization as models

    actors = state()
    companies = actors["companies"]
    extras = {}
    async with AsyncSessionLocal() as session:
        for actor in actors["users"].values():
            if actor["company_id"]:
                membership = await session.get(UserCompany, (UUID(actor["id"]), UUID(actor["company_id"])))
                require(membership is not None, "Missing isolated company membership")
                membership.role = actor["role"]
        for index, (alias, kind) in enumerate([
            ("distributor2", "distributor"), ("group_dealer", "dealer"),
            ("inactive_group_dealer", "dealer"),
        ], 1):
            company_id = identifier("monetization/" + alias)
            company = await session.get(Company, company_id)
            if company is None:
                company = Company(id=company_id, name="22296 " + alias,
                    inn=f"000029296{index}", company_type=kind, is_active=True)
                session.add(company)
            extras[alias] = {"company_id": str(company.id), "name": company.name}
        await session.flush()
        dealer_id = UUID(companies["dealer"]["company_id"])
        distributor_id = UUID(companies["distributor"]["company_id"])
        if not await session.scalar(select(DistributorDealerLink).where(
            DistributorDealerLink.dealer_company_id == dealer_id)):
            session.add(DistributorDealerLink(dealer_company_id=dealer_id,
                distributor_company_id=distributor_id))
        for alias, active, members in [
            ("active-group", True, [dealer_id, UUID(extras["group_dealer"]["company_id"])]),
            ("inactive-group", False, [UUID(extras["inactive_group_dealer"]["company_id"])]),
        ]:
            group_id = identifier("monetization/" + alias)
            if await session.get(DealerGroup, group_id) is None:
                session.add(DealerGroup(id=group_id, name="22296 " + alias,
                    distributor_company_id=distributor_id, is_active=active,
                    created_by=UUID(actors["users"]["admin"]["id"])))
                await session.flush()
                for member in members:
                    session.add(DealerGroupMember(dealer_group_id=group_id,
                        dealer_company_id=member, created_by=UUID(actors["users"]["admin"]["id"])))
        await session.commit()
    companies.update(extras)
    api = API(actors)
    run = uuid4().hex[:8]
    cases = []
    # Expected boundaries are independent constants, including exact equality.
    definitions = [
        ("maximum", {"max": "100000"}, {}, "100000", "max", "100000", "30000", "none", None),
        ("minimum", {"min": "150000"}, {}, "150000", "min", "150000", "45000", "none", None),
        ("unbounded", {}, {}, "120150", "none", None, "36045", "none", None),
        ("equal_maximum", {"max": "120150"}, {}, "120150", "none", None, "36045", "none", None),
        ("equal_minimum", {"min": "120150"}, {}, "120150", "none", None, "36045", "none", None),
        ("income_maximum", {"max": "100000"}, {"max": "25000"}, "100000", "max", "100000", "25000", "max", "25000"),
        ("income_minimum", {"min": "150000"}, {"min": "50000"}, "150000", "min", "150000", "50000", "min", "50000"),
        ("fractional_maximum", {"max": "100000.49"}, {}, "100000.49", "max", "100000.49", "30000.15", "none", None),
    ]
    for index, (kind, expense, income, amount, clip, limit, received, income_clip, income_limit) in enumerate(definitions, 1):
        name = f"22296-monetization-{run}-{kind}"
        vin = "E22296" + run.upper() + str(index) + "00"
        body = program_payload(actors, name, vin=vin, expense=expense, income=income)
        program = await api.request("admin", "POST", PROGRAMS, 201, json=body)
        bid = await source_bid(actors, vin, name, 222960000 + int(run[:4], 16) * 10 + index)
        await api.request("leasing", "PUT", f"/api/v1/exchange/bids/{bid['bid_id']}/approve")
        async with AsyncSessionLocal() as session:
            deal_ids = (await session.scalars(select(models.deals.c.id).where(
                models.deals.c.exchange_request_id == UUID(bid["request_id"])))).all()
        require(len(deal_ids) == 1, kind + ": source action did not capture exactly one deal")
        cases.append({"kind": kind, "deal_id": str(deal_ids[0]), "program_id": program["id"],
            "expense": amount, "expense_clip": clip, "expense_limit": limit,
            "income": received, "income_clip": income_clip, "income_limit": income_limit})
        await api.request("admin", "PATCH", PROGRAMS + "/" + program["id"], json={"status": "inactive"})
    browser_vin = "B22296" + run.upper() + "000"
    browser_bid = await source_bid(actors, browser_vin, f"22296-browser-{run}", 222969999 + int(run[:4], 16))
    manifest = json.loads((ROOT / "manifest.json").read_text())
    manifest.update(marker="monetization-22296", companies=companies, cases=cases,
        browser_vin=browser_vin, browser_bid=browser_bid)
    manifest["storage_states"] = {
        role: str(HOST_ROOT / (role + ".storage.json")) for role in manifest["storage_states"]}
    private_json(ROOT / "monetization.manifest.json", manifest)
    progress("monetization_fixtures_ready", cases=len(cases), path=str(HOST_ROOT / "monetization.manifest.json"))


async def verify():
    actors = state()
    api = API(actors)
    manifest = json.loads((ROOT / "monetization.manifest.json").read_text())
    companies = manifest["companies"]
    checks = 0

    def check(condition, message):
        nonlocal checks
        require(condition, message)
        checks += 1

    distributor = companies["distributor"]["company_id"]
    dealer = companies["dealer"]["company_id"]
    linked = await api.request("admin", "GET", LOOKUP,
        params={"kind": "dealer", "distributor_company_id": distributor})
    ids = [row["id"] for row in linked["items"]]
    check(set(ids) == {dealer, companies["group_dealer"]["company_id"]},
          "Distributor lookup must include direct and active-group relations only")
    check(len(ids) == len(set(ids)), "Overlapping direct and group relations duplicated a dealer")
    for alias in ("dealer", "group_dealer"):
        found = await api.request("admin", "GET", LOOKUP,
            params={"kind": "distributor", "dealer_company_id": companies[alias]["company_id"]})
        check([row["id"] for row in found["items"]] == [distributor], "Reverse lookup " + alias)
    for alias in ("dealer2", "inactive_group_dealer"):
        found = await api.request("admin", "GET", LOOKUP,
            params={"kind": "distributor", "dealer_company_id": companies[alias]["company_id"]})
        check(not found["items"], "Unrelated/inactive-group dealer unexpectedly has a distributor")
    unrestricted = await api.request("admin", "GET", LOOKUP, params={"kind": "dealer", "q": "22296"})
    check(companies["dealer2"]["company_id"] in {row["id"] for row in unrestricted["items"]},
          "No distributor must preserve unrestricted dealer selection")
    await api.request("guest", "GET", LOOKUP, expected=401, params={"kind": "dealer"})
    await api.request("client", "GET", LOOKUP, expected=403, params={"kind": "dealer"})
    await api.request("admin", "GET", LOOKUP, expected=422,
        params={"kind": "dealer", "distributor_company_id": "not-a-uuid"})
    await api.request("dealer", "POST", PROGRAMS, expected=403,
        json=program_payload(actors, "22296 rejected dealer write"))
    mismatch = program_payload(actors, "22296 rejected mismatched pair " + uuid4().hex)
    mismatch["distributor_company_id"] = companies["distributor2"]["company_id"]
    await api.request("admin", "POST", PROGRAMS, expected=400, json=mismatch)
    for omission in ("dealer_company_id", "distributor_company_id"):
        body = program_payload(actors, "22296 optional " + uuid4().hex)
        body[omission] = None
        body["status"] = "inactive"
        await api.request("admin", "POST", PROGRAMS, expected=201, json=body)
    progress("monetization_lookup_http_passed", assertions=checks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify"])
    asyncio.run(globals()[parser.parse_args().action]())
