"""Real HTTP proof that registered trims preserve existing condition semantics."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

sys.path.insert(0, "/e2e")
from runtime import API, ROOT, guard, private_json, progress, require

MANIFEST = ROOT / "trim-legacy.manifest.json"
PROGRAMS = "/api/v1/admin/monetization/programs"


def actors():
    guard()
    return json.loads((ROOT / "state.secret.json").read_text())


def payload(state, case, *, fallback=False, current=False):
    return {
        "name": "22406 trim " + ("fallback " if fallback else "current " if current else "legacy ") + case["model"],
        "leasing_company_id": state["companies"]["leasing_company"]["id"],
        "dealer_company_id": state["companies"]["dealer"]["company_id"],
        "brand": case["brand"], "model": case["model"],
        "modification": None if fallback else case["modification"] if current else case["old_modification"],
        "trim": None if fallback else case["new_filter_trim"] if current else case["old_trim"],
        "period_start": "2026-01-01", "period_end": "2030-12-31", "status": "active",
        "sources": [{"source_type": "platform", "expenses": [{
            "local_id": "expense", "participant_type": "leasing", "base_type": "property_value",
            "calc_type": "percent", "value": "1" if fallback else "3" if current else "2",
        }], "incomes": []}],
    }


async def database_snapshot(ids):
    import sqlalchemy as sa
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    async with AsyncSessionLocal() as session:
        deals = (await session.execute(sa.select(models.deals).where(
            models.deals.c.id.in_([UUID(value) for value in ids])).order_by(models.deals.c.id))).mappings().all()
        amounts = (await session.execute(sa.select(models.amounts).where(
            models.amounts.c.deal_id.in_([UUID(value) for value in ids])).order_by(models.amounts.c.id))).mappings().all()
    return json.dumps({"deals": [dict(row) for row in deals], "amounts": [dict(row) for row in amounts]},
        default=str, sort_keys=True)


async def capture(api, origin, expected_program, expected_amount):
    import sqlalchemy as sa
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    if not origin.get("deal_id"):
        await api.request("leasing", "POST",
            "/api/v1/leasing/applications/" + origin["application_id"] + "/confirm-deal",
            json=origin["confirmation"])
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sa.select(models.deals.c.id).where(
            models.deals.c.leasing_company_application_id == UUID(origin["lca_id"])))).scalars().all()
    require(len(rows) == 1, "Source transition must capture exactly one financial snapshot")
    origin["deal_id"] = str(rows[0])
    deal = await api.request("admin", "GET", "/api/v1/monetization/deals/" + origin["deal_id"])
    require(deal["program_id"] == expected_program, "Wrong condition selected for legacy/actual trim")
    require(Decimal(deal["expenses"][0]["amount"]) == Decimal(expected_amount), "Wrong financial result")
    return deal


async def seed():
    import sqlalchemy as sa
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import ApplicationVehicle, ApplicationVehicleAllocation, LeasingApplication, LeasingCompanyApplication, LeasingProposal
    from infrastructure.models.documents import Document
    from infrastructure.models.special_equipment import SpecialEquipmentMark, SpecialEquipmentModel, SpecialEquipmentModification, SpecialEquipmentProduct, SpecialEquipmentTrim, SpecialEquipmentSuperstructure

    state = actors()
    api = API(state)
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())
        require(manifest.get("pre_migration_snapshot"), "Incomplete legacy fixture; inspect before retry")
        progress("legacy_trim_seed_reused")
        return
    async with AsyncSessionLocal() as session:
        has_version = await session.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='monetization_programs' AND column_name='vehicle_filter_version')"))
        require(not has_version, "Run seed before applying revision 167")
    suffix = uuid4().hex[:8]
    manifest = {"marker": "22406-trim-legacy", "cases": {}}
    companies, users = state["companies"], state["users"]
    async with AsyncSessionLocal() as session:
        mark = SpecialEquipmentMark(id=uuid4(), code="22406-legacy-" + suffix, slug="22406-legacy-" + suffix, name="22406 Legacy " + suffix)
        session.add(mark)
        await session.flush()
        for index, kind in enumerate(("null_modification", "equal_modification", "different_modification", "arbitrary_trim", "superstructure")):
            code = "22406-legacy-" + kind + "-" + suffix
            model = SpecialEquipmentModel(id=uuid4(), code=code, slug=code, name=kind + " " + suffix, mark_id=mark.id)
            session.add(model)
            await session.flush()
            modification = SpecialEquipmentModification(id=uuid4(), code=code, slug=code, name="M " + kind + " " + suffix, model_id=model.id)
            session.add(modification)
            await session.flush()
            trim = SpecialEquipmentTrim(id=uuid4(), code=code, slug=code, name="T " + kind + " " + suffix, modification_id=modification.id)
            session.add(trim)
            superstructure = None
            if kind == "superstructure":
                superstructure = SpecialEquipmentSuperstructure(id=uuid4(), code=code, slug=code, name="S " + suffix)
                session.add(superstructure)
            await session.flush()
            old_trim = modification.name
            if kind == "different_modification":
                old_trim = trim.name
            elif kind == "arbitrary_trim":
                old_trim = "Unknown legacy value " + suffix
            elif superstructure:
                old_trim = superstructure.name
            case = {
                "brand": mark.name, "model": model.name,
                "modification": None if superstructure else modification.name,
                "actual_trim": None if superstructure else trim.name,
                "old_modification": modification.name if kind in {"equal_modification", "different_modification"} else None,
                "old_trim": old_trim,
                "new_filter_trim": superstructure.name if superstructure else trim.name,
                "old_matches": kind not in {"different_modification", "arbitrary_trim"},
                "origins": {},
            }
            manifest["cases"][kind] = case
            for phase in ("before", "legacy_after", "current_after"):
                part = uuid4().hex[:8]
                vin = "22406LEGA" + part.upper()
                product_fields = {"id": uuid4(), "code": code + "-" + phase, "slug": code + "-" + phase,
                    "seller_company_id": UUID(companies["dealer"]["company_id"]), "vin": vin,
                    "price": Decimal("1000000"), "condition": "new"}
                if superstructure:
                    product_fields.update(model_id=model.id, superstructure_id=superstructure.id,
                        superstructure_name=superstructure.name, superstructure_manufacturer="Fixture", chassis_vin=vin)
                else:
                    product_fields.update(modification_id=modification.id, trim_id=trim.id)
                product = SpecialEquipmentProduct(**product_fields)
                session.add(product)
                app = LeasingApplication(id=uuid4(), company_id=UUID(companies["client"]["company_id"]),
                    dealer_company_id=UUID(companies["dealer"]["company_id"]), created_by=UUID(users["dealer"]["id"]),
                    source_type="platform", status="active", display_number="22406-legacy-" + part,
                    name="22406 Legacy " + kind, total_amount=Decimal("1000000"))
                session.add(app)
                await session.flush()
                line = ApplicationVehicle(id=uuid4(), application_id=app.id, product_id=product.id,
                    modification_id=str(modification.id) if not superstructure else None,
                    dealer_company_id=UUID(companies["dealer"]["company_id"]),
                    quantity=1, requested_quantity=1, confirmed_quantity=1, unit_price=Decimal("1000000"),
                    total_price=Decimal("1000000"), car_status="confirmed", is_model_order=False)
                session.add(line)
                await session.flush()
                session.add(ApplicationVehicleAllocation(id=uuid4(), application_vehicle_id=line.id,
                    product_id=product.id, vin=vin, unit_price=Decimal("1000000"),
                    reserved_until=datetime.now(UTC)+timedelta(days=1), created_by=UUID(users["dealer"]["id"])))
                link = LeasingCompanyApplication(id=uuid4(), application_id=app.id,
                    leasing_company_id=UUID(companies["leasing_company"]["id"]), status="selected_lc")
                session.add(link)
                await session.flush()
                session.add(LeasingProposal(id=uuid4(), leasing_company_application_id=link.id,
                    kind="final", total_amount=Decimal("1000000"), client_decision_action="accepted"))
                documents = []
                for document_type in ("signed_lease_agreement", "acceptance_transfer_act"):
                    document = Document(id=uuid4(), company_id=UUID(companies["client"]["company_id"]),
                        document_type=document_type, file_name=part + "-" + document_type + ".pdf",
                        status="uploaded", uploaded_at=datetime.now(UTC))
                    session.add(document)
                    documents.append({"file_id": str(document.id), "document_type": document_type})
                case["origins"][phase] = {"application_id": str(app.id), "lca_id": str(link.id),
                    "confirmation": {"deal_date": "2026-10-05",
                        "vehicles": [{"vehicle_id": str(line.id), "vin": vin}], "documents": documents}}
        await session.commit()
    for case in manifest["cases"].values():
        for key, fallback in (("fallback_program", True), ("legacy_program", False)):
            program = await api.request("admin", "POST", PROGRAMS, 201, json=payload(state, case, fallback=fallback))
            case[key] = program["id"]
        expected = case["legacy_program"] if case["old_matches"] else case["fallback_program"]
        await capture(api, case["origins"]["before"], expected, "20000" if case["old_matches"] else "10000")
    ids = [case["origins"]["before"]["deal_id"] for case in manifest["cases"].values()]
    manifest["pre_migration_snapshot"] = await database_snapshot(ids)
    private_json(MANIFEST, manifest)
    progress("legacy_trim_seeded_before_revision_167", programs=10, historical_deals=5, pending_origins=10)


async def verify():
    import sqlalchemy as sa
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    state, api = actors(), API(actors())
    manifest = json.loads(MANIFEST.read_text())
    require(manifest["marker"] == "22406-trim-legacy", "Unexpected legacy trim fixture")
    ids = [case["origins"]["before"]["deal_id"] for case in manifest["cases"].values()]
    require(await database_snapshot(ids) == manifest["pre_migration_snapshot"], "Migration changed existing financial snapshots")
    for kind, case in manifest["cases"].items():
        async with AsyncSessionLocal() as session:
            programs = (await session.execute(sa.select(models.programs).where(
                models.programs.c.id.in_([UUID(case["legacy_program"]), UUID(case["fallback_program"])])))).mappings().all()
        require(len(programs) == 2 and all(row["vehicle_filter_version"] == 1 for row in programs), "Existing rows must retain v1 filter semantics")
        require(all(row["rules_version"] == 2 for row in programs), "Financial rule versions must remain unchanged")
        old = next(row for row in programs if str(row["id"]) == case["legacy_program"])
        require(old["modification"] == case["old_modification"] and old["trim"] == case["old_trim"], "Migration rewrote existing criteria")
        await api.request("admin", "POST", PROGRAMS, 409, json=payload(state, case, fallback=True))
        expected = case["legacy_program"] if case["old_matches"] else case["fallback_program"]
        await capture(api, case["origins"]["legacy_after"], expected, "20000" if case["old_matches"] else "10000")
        private_json(MANIFEST, manifest)
        if kind in {"null_modification", "equal_modification"}:
            await api.request("admin", "PATCH", PROGRAMS + "/" + case["legacy_program"], json={"status": "inactive"})
        body = payload(state, case, current=True)
        if not case.get("current_program"):
            program = await api.request("admin", "POST", PROGRAMS, 201, json=body)
            case["current_program"] = program["id"]
            private_json(MANIFEST, manifest)
        async with AsyncSessionLocal() as session:
            version = await session.scalar(sa.select(models.programs.c.vehicle_filter_version).where(
                models.programs.c.id == UUID(case["current_program"])))
        require(version == 2, "Application must stamp newly created programs with v2")
        await api.request("admin", "POST", PROGRAMS, 409, json=body)
        expected_current = case["legacy_program"] if kind == "superstructure" else case["current_program"]
        await capture(api, case["origins"]["current_after"], expected_current, "20000" if kind == "superstructure" else "30000")
        private_json(MANIFEST, manifest)
        progress("legacy_trim_http_case_passed", case=kind)
    require(await database_snapshot(ids) == manifest["pre_migration_snapshot"], "New conditions changed historical financial snapshots")
    case = next(iter(manifest["cases"].values()))
    long_name = deepcopy(payload(state, case, current=True))
    long_name.update(name="22406 trim length " + uuid4().hex[:8], status="inactive", trim="T" * 255)
    accepted = await api.request("admin", "POST", PROGRAMS, 201, json=long_name)
    require(accepted["trim"] == long_name["trim"], "Full catalog trim length must round-trip")
    long_name["trim"] = "T" * 256
    await api.request("admin", "POST", PROGRAMS, 422, json=long_name)
    rejected = deepcopy(payload(state, case, current=True))
    rejected["vehicle_filter_version"] = 1
    await api.request("admin", "POST", PROGRAMS, 422, json=rejected)
    progress("legacy_trim_migration_and_http_passed", cases=5, historical_snapshots_unchanged=5, rules_version_unchanged=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seed", "verify", "verify-if-seeded"])
    action = parser.parse_args().action
    if action == "verify-if-seeded" and not MANIFEST.exists():
        guard()
        progress("legacy_trim_migration_skipped", reason="no pre167 baseline")
    else:
        asyncio.run(seed() if action == "seed" else verify())
