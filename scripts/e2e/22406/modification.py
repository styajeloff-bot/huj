"""Live API checks for separate modification and trim conditions in task 22406."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, "/e2e")
from runtime import API, ROOT, guard, private_json, progress, require

MANIFEST = ROOT / "modification.manifest.json"
PROGRAMS = "/api/v1/admin/monetization/programs"
CATALOG = "/api/v1/monetization/lookups/catalog"


def actors():
    guard()
    return json.loads((ROOT / "state.secret.json").read_text())


async def seed():
    """Only fixture setup uses ORM; every behavior assertion uses the live API."""
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.exchange import ExchangeBid, ExchangeRequest
    from infrastructure.models.special_equipment import (
        SpecialEquipmentMark, SpecialEquipmentModel,
        SpecialEquipmentModification, SpecialEquipmentProduct, SpecialEquipmentTrim,
    )

    state = actors()
    if MANIFEST.exists() and json.loads(MANIFEST.read_text()).get("fixture_version") == 2:
        manifest = json.loads(MANIFEST.read_text())
        await seed_applications(state, manifest)
        progress("modification_fixture_ready", reused=True)
        return
    suffix = uuid4().hex[:8]
    manifest = {
        "marker": "monetization-22406-modification", "fixture_version": 2,
        "cases": {}, "programs": {}, "trims": {},
        "brand": "22406 Марка " + suffix, "model": "22406 Модель " + suffix,
        "base_url": "http://localhost:18268",
    }
    companies, users = state["companies"], state["users"]
    async with AsyncSessionLocal() as session:
        mark = SpecialEquipmentMark(id=uuid4(), code="22406-mark-" + suffix,
            slug="22406-mark-" + suffix, name=manifest["brand"])
        session.add(mark)
        await session.flush()
        model = SpecialEquipmentModel(id=uuid4(), code="22406-model-" + suffix,
            slug="22406-model-" + suffix, name=manifest["model"], mark_id=mark.id)
        session.add(model)
        await session.flush()
        manifest.update(mark_id=str(mark.id), model_id=str(model.id))
        for index, kind in enumerate(("specific_a", "specific_b", "generic", "legacy_trim"), 1):
            name = "22406 Модификация " + kind + " " + suffix
            code = "22406-" + kind + "-" + suffix
            modification = SpecialEquipmentModification(id=uuid4(), code=code,
                slug=code, name=name, model_id=model.id)
            session.add(modification)
            await session.flush()
            product = SpecialEquipmentProduct(id=uuid4(), code=code, slug=code,
                modification_id=modification.id,
                seller_company_id=UUID(companies["dealer"]["company_id"]),
                vin="22406" + suffix.upper() + str(index).zfill(4),
                price=Decimal("1000000"), condition="new")
            session.add(product)
            await session.flush()
            request = ExchangeRequest(id=uuid4(), lc_user_id=UUID(users["leasing"]["id"]),
                lc_company_id=UUID(companies["leasing_company"]["company_id"]),
                product_id=product.id, quantity=1, status="open",
                batch_number=2240600 + index, batch_index=1,
                expiration_at=datetime.now(UTC) + timedelta(days=1))
            session.add(request)
            await session.flush()
            bid = ExchangeBid(id=uuid4(), request_id=request.id,
                dealer_id=UUID(users["dealer"]["id"]),
                dealer_company_id=UUID(companies["dealer"]["company_id"]),
                price=Decimal("1000000"), quantity=1, kp_status="accepted", is_accepted=False)
            session.add(bid)
            manifest["cases"][kind] = {
                "modification_id": str(modification.id), "modification": name,
                "product_id": str(product.id), "bid_id": str(bid.id),
                "request_id": str(request.id), "application_number": f"{2240600 + index}-1",
            }
        for index, kind in enumerate(("trim_a", "trim_b", "trim_other"), 10):
            modification_kind = "specific_b" if kind == "trim_other" else "specific_a"
            parent = manifest["cases"][modification_kind]
            name = "22406 Комплектация " + kind + " " + suffix
            code = "22406-" + kind + "-" + suffix
            trim = SpecialEquipmentTrim(id=uuid4(), code=code, slug=code, name=name,
                modification_id=UUID(parent["modification_id"]))
            session.add(trim)
            await session.flush()
            manifest["trims"][kind] = {
                "id": str(trim.id), "name": name, "modification_id": parent["modification_id"],
            }
            if kind == "trim_other":
                continue
            product = SpecialEquipmentProduct(id=uuid4(), code=code, slug=code,
                modification_id=UUID(parent["modification_id"]), trim_id=trim.id,
                seller_company_id=UUID(companies["dealer"]["company_id"]),
                vin="22406" + suffix.upper() + str(index).zfill(4),
                price=Decimal("1000000"), condition="new")
            session.add(product)
            await session.flush()
            request = ExchangeRequest(id=uuid4(), lc_user_id=UUID(users["leasing"]["id"]),
                lc_company_id=UUID(companies["leasing_company"]["company_id"]),
                product_id=product.id, quantity=1, status="open",
                batch_number=2240600 + index, batch_index=1,
                expiration_at=datetime.now(UTC) + timedelta(days=1))
            session.add(request)
            await session.flush()
            bid = ExchangeBid(id=uuid4(), request_id=request.id,
                dealer_id=UUID(users["dealer"]["id"]),
                dealer_company_id=UUID(companies["dealer"]["company_id"]),
                price=Decimal("1000000"), quantity=1, kp_status="accepted", is_accepted=False)
            session.add(bid)
            manifest["cases"][kind] = {
                "modification_id": parent["modification_id"], "modification": parent["modification"],
                "trim_id": str(trim.id), "trim": name,
                "product_id": str(product.id), "bid_id": str(bid.id),
                "request_id": str(request.id), "application_number": f"{2240600 + index}-1",
            }
        manifest["cases"]["legacy_trim"]["program_kind"] = "generic"
        await session.commit()
    private_json(MANIFEST, manifest)
    await seed_applications(state, manifest)
    progress("modification_fixture_ready", cases=len(manifest["cases"]))


async def seed_applications(state, manifest):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import (
        ApplicationVehicle, ApplicationVehicleAllocation, LeasingApplication,
        LeasingCompanyApplication, LeasingProposal,
    )
    from infrastructure.models.documents import Document
    from infrastructure.models.special_equipment import SpecialEquipmentProduct

    if manifest.get("applications"):
        return
    companies, users = state["companies"], state["users"]
    manifest["applications"] = {}
    async with AsyncSessionLocal() as session:
        for kind, program_kind in (("stock", "specific_a"), ("model_order", "specific_b"),
                ("stock_trim", "trim_a"), ("product_trim", "trim_b")):
            case = manifest["cases"][program_kind]
            application = LeasingApplication(id=uuid4(),
                company_id=UUID(companies["client"]["company_id"]),
                dealer_company_id=UUID(companies["dealer"]["company_id"]),
                created_by=UUID(users["dealer"]["id"]), source_type="platform", status="active",
                display_number="22406-" + kind, name="22406 " + kind,
                total_amount=Decimal("1000000"))
            session.add(application)
            await session.flush()
            product = None
            if kind != "model_order":
                suffix = uuid4().hex[:8]
                product = SpecialEquipmentProduct(id=uuid4(), code="22406-stock-" + suffix,
                    slug="22406-stock-" + suffix, modification_id=UUID(case["modification_id"]),
                    trim_id=UUID(case["trim_id"]) if case.get("trim_id") else None,
                    seller_company_id=UUID(companies["dealer"]["company_id"]),
                    vin="22406STCK" + suffix.upper(), price=Decimal("1000000"), condition="new")
                session.add(product)
                await session.flush()
            line = ApplicationVehicle(id=uuid4(), application_id=application.id,
                product_id=product.id if product else None,
                modification_id=case["modification_id"],
                dealer_company_id=UUID(companies["dealer"]["company_id"]),
                quantity=1, requested_quantity=1, confirmed_quantity=1,
                unit_price=Decimal("1000000"), total_price=Decimal("1000000"),
                car_status="confirmed", is_model_order=product is None)
            session.add(line)
            await session.flush()
            if product and kind != "product_trim":
                session.add(ApplicationVehicleAllocation(id=uuid4(),
                    application_vehicle_id=line.id, product_id=product.id, vin=product.vin,
                    unit_price=Decimal("1000000"), reserved_until=datetime.now(UTC)+timedelta(days=1),
                    created_by=UUID(users["dealer"]["id"])))
            link = LeasingCompanyApplication(id=uuid4(), application_id=application.id,
                leasing_company_id=UUID(companies["leasing_company"]["id"]), status="selected_lc")
            session.add(link)
            await session.flush()
            session.add(LeasingProposal(id=uuid4(), leasing_company_application_id=link.id,
                kind="final", total_amount=Decimal("1000000"), client_decision_action="accepted"))
            documents = []
            for document_type in ("signed_lease_agreement", "acceptance_transfer_act"):
                document = Document(id=uuid4(),
                    company_id=UUID(companies["client"]["company_id"]),
                    document_type=document_type, file_name=f"22406-{kind}-{document_type}.pdf",
                    status="uploaded", uploaded_at=datetime.now(UTC))
                session.add(document)
                documents.append({"file_id": str(document.id), "document_type": document_type})
            manifest["applications"][kind] = {
                "application_id": str(application.id), "lca_id": str(link.id),
                "program_kind": program_kind, "modification": case["modification"], "trim": case.get("trim"),
                "confirmation": {
                    "deal_date": "2026-10-05",
                    "vehicles": [{"vehicle_id": str(line.id),
                        "vin": product.vin if product else "22406MODL" + uuid4().hex[:8].upper()}],
                    "documents": documents,
                },
            }
        await session.commit()
    private_json(MANIFEST, manifest)
    progress("modification_applications_seeded", count=len(manifest["applications"]))


def payload(state, manifest, kind):
    conditions = {
        "name": "22406 " + kind + " " + manifest["model"],
        "leasing_company_id": state["companies"]["leasing_company"]["id"],
        "dealer_company_id": state["companies"]["dealer"]["company_id"],
        "brand": manifest["brand"], "model": manifest["model"],
        "period_start": "2026-01-01", "period_end": "2030-12-31", "status": "active",
        "sources": [{"source_type": "exchange", "expenses": [
            {"local_id": "expense", "participant_type": "leasing",
             "base_type": "property_value", "calc_type": "percent", "value": "5"}],
            "incomes": [{"local_id": "income", "participant_type": "dealer",
             "base_type": "expense_amount", "calc_type": "percent", "value": "100",
             "expense_ref": "expense"}]}],
    }
    platform = deepcopy(conditions["sources"][0])
    platform["source_type"] = "platform"
    platform["expenses"][0]["value"] = "7"
    conditions["sources"].append(platform)
    if kind in {"specific_a", "specific_b", "trim_a", "trim_b"}:
        conditions["modification"] = manifest["cases"][kind]["modification"]
    if kind in {"trim_a", "trim_b"}:
        conditions["trim"] = manifest["cases"][kind]["trim"]
    return conditions


async def verify():
    import httpx
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    state = actors()
    manifest = json.loads(MANIFEST.read_text())
    require(manifest["marker"] == "monetization-22406-modification", "Unexpected fixture")
    api = API(state)
    query = {"mark_id": manifest["mark_id"], "model_id": manifest["model_id"]}
    found = await api.request("admin", "GET", CATALOG, params={**query, "fields": "modifications"})
    expected = {case["modification_id"]: case["modification"] for case in manifest["cases"].values()}
    require({row["id"]: row["name"] for row in found["modifications"]} == expected,
        "Modification selector must return registered names of the selected model")
    empty = await api.request("admin", "GET", CATALOG, params={**query, "fields": "trims"})
    require(empty == {"trims": []}, "No modification must yield no trims")
    for parent in ("specific_a", "specific_b", "generic"):
        modification_id = manifest["cases"][parent]["modification_id"]
        trims = await api.request("admin", "GET", CATALOG,
            params={**query, "fields": "trims", "modification_id": modification_id})
        expected_trims = {row["id"]: row["name"] for row in manifest["trims"].values()
            if row["modification_id"] == modification_id}
        require({row["id"]: row["trim_name"] for row in trims["trims"]} == expected_trims,
            parent + ": trims must come only from the selected modification")
        require(all(row["name"] == row["trim_name"] for row in trims["trims"]),
            "Trim label must be the registered trim name")
    for changes in ({"model_id": str(uuid4())}, {"mark_id": str(uuid4())},
            {"model_id": "invalid"}):
        wrong = await api.request("admin", "GET", CATALOG,
            params={**query, "fields": "trims", "modification_id": manifest["cases"]["specific_a"]["modification_id"], **changes})
        require(wrong == {"trims": []}, "Wrong trim parent must yield no options")
    await api.request("admin", "GET", CATALOG, expected=422,
        params={**query, "fields": "trims", "modification_id": "invalid"})
    invalid = await api.request("admin", "GET", CATALOG,
        params={"fields": "modifications", "mark_id": manifest["mark_id"], "model_id": "invalid"})
    require(invalid == {"modifications": []}, "Invalid model should have no catalog options")
    async with httpx.AsyncClient(base_url="http://backend:3002", trust_env=False) as client:
        response = await client.get(CATALOG, params={**query, "fields": "modifications"})
        require(response.status_code == 401, "Anonymous catalog lookup must be denied")
    await api.request("dealer", "POST", PROGRAMS, expected=403,
        json=payload(state, manifest, "specific_a"))
    api.passed("separate modification and trim lookups, hierarchy constraints, UUID validation and access restrictions")
    for kind in ("generic", "specific_a", "specific_b", "trim_a", "trim_b"):
        body = payload(state, manifest, kind)
        if kind not in manifest["programs"]:
            created = await api.request("admin", "POST", PROGRAMS, expected=201, json=body)
            manifest["programs"][kind] = created["id"]
            private_json(MANIFEST, manifest)
        program = await api.request("admin", "GET", PROGRAMS + "/" + manifest["programs"][kind])
        require(program.get("modification") == body.get("modification"), "Modification not preserved")
        require(program.get("trim") == body.get("trim"), "Trim not preserved")
    await api.request("admin", "POST", PROGRAMS, expected=409,
        json=payload(state, manifest, "specific_a"))
    boundary = payload(state, manifest, "trim_b")
    boundary.update(name="22406 trim length " + manifest["model"], status="inactive",
        trim="Комплектация " + "Д" * (255 - len("Комплектация ")))
    require(len(boundary["trim"]) == 255, "Trim boundary fixture must have 255 characters")
    if not manifest.get("trim_boundary_program"):
        created = await api.request("admin", "POST", PROGRAMS, expected=201, json=boundary)
        manifest["trim_boundary_program"] = created["id"]
        private_json(MANIFEST, manifest)
    persisted = await api.request("admin", "GET", PROGRAMS + "/" + manifest["trim_boundary_program"])
    require(persisted["trim"] == boundary["trim"], "Full catalog trim length must round-trip")
    await api.request("admin", "POST", PROGRAMS, expected=422,
        json={**boundary, "trim": boundary["trim"] + "Д"})
    api.passed("different modifications coexist, exact duplicate still conflicts, values round-trip")
    for kind, case in manifest["cases"].items():
        program_kind = case.get("program_kind", kind)
        if not case.get("deal_id"):
            await api.request("leasing", "PUT", "/api/v1/exchange/bids/" + case["bid_id"] + "/approve")
        async with AsyncSessionLocal() as session:
            captured = (await session.execute(select(
                models.deals.c.id, models.deals.c.program_id, models.deals.c.vehicles,
            ).where(models.deals.c.exchange_request_id == UUID(case["request_id"])))).mappings().all()
        require(len(captured) == 1, kind + ": source approval must capture one deal")
        row = captured[0]
        require(str(row["program_id"]) == manifest["programs"][program_kind], kind + ": incorrect selected conditions")
        require(row["vehicles"][0]["modification"] == case["modification"], "Missing modification in source snapshot")
        require(row["vehicles"][0]["trim"] == case.get("trim"), "Snapshot must contain actual trim name or null")
        case["deal_id"] = str(row["id"])
        private_json(MANIFEST, manifest)
        deal = await api.request("admin", "GET", "/api/v1/monetization/deals/" + case["deal_id"])
        require(deal["program_name"] == payload(state, manifest, program_kind)["name"], "Wrong program in API deal")
        require(Decimal(deal["expenses"][0]["amount"]) == Decimal("50000"), "Wrong calculated expense")
    api.passed("real exchange approval selects matching modification, exact trims and wildcard for unknown trim")
    for kind, case in manifest["applications"].items():
        path = "/api/v1/leasing/applications/" + case["application_id"] + "/confirm-deal"
        if not case.get("deal_id"):
            await api.request("dealer", "POST", path, expected=403, json=case["confirmation"])
            await api.request("leasing", "POST", path, json=case["confirmation"])
        async with AsyncSessionLocal() as session:
            captured = (await session.execute(select(
                models.deals.c.id, models.deals.c.program_id, models.deals.c.vehicles,
            ).where(models.deals.c.leasing_company_application_id == UUID(case["lca_id"])))).mappings().all()
        require(len(captured) == 1, kind + ": confirm-deal must capture one deal")
        row = captured[0]
        require(str(row["program_id"]) == manifest["programs"][case["program_kind"]],
            kind + ": modification was not matched on ordinary application")
        require(row["vehicles"][0]["modification"] == case["modification"],
            kind + ": modification missing from ordinary snapshot")
        require(row["vehicles"][0]["trim"] == case.get("trim"),
            kind + ": actual trim missing from ordinary snapshot")
        case["deal_id"] = str(row["id"])
        private_json(MANIFEST, manifest)
        deal = await api.request("admin", "GET", "/api/v1/monetization/deals/" + case["deal_id"])
        require(deal["source_type"] == "platform" and len(deal["expenses"]) == 1,
            kind + ": another source block leaked into calculation")
        require(Decimal(deal["expenses"][0]["amount"]) == Decimal("70000"),
            kind + ": platform must use its own 7% rate, exchange uses 5%")
    api.passed("ordinary stock allocation and model order match modification and calculate only their source block")
    private_json(ROOT / "modification.results.json", {"checks": api.checks})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify"])
    asyncio.run(seed() if parser.parse_args().action == "seed" else verify())
