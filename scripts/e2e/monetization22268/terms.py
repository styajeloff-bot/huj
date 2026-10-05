"""Real HTTP and Kafka/inbox checks for the saved deal percentages in task 22268."""
from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from runtime import API, HOST_ROOT, MARKER, ROOT, guard, identifier, private_json, program_payload, progress, require

EVENT = "monetization.deal_terms_changed"
ROLES = ("admin", "leasing", "dealer", "distributor", "read_only")


def state():
    guard()
    value = json.loads((ROOT / "state.secret.json").read_text())
    require(value["marker"] == MARKER, "Wrong fixture marker")
    return value


async def seed():
    from sqlalchemy import insert, update
    from infrastructure.models import monetization as m
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import monetization_repository as repo
    from infrastructure.models.applications import LeasingApplication, LeasingCompanyApplication
    from domain.monetization.programs import calculate_program

    actors = state()
    api = API(actors)
    run = uuid4().hex[:10]
    programs = {}
    for kind in ("property", "linked", "fixed", "clip", "zero", "cent_groups", "cent_rounding", "cent_history"):
        draft = program_payload(f"22268 saved-percent {kind} {run}", "platform", active=True)
        draft["brand"] = "TERMS-" + run + "-" + kind
        source = draft["sources"][0]
        source["expenses"][0]["value"] = "3"
        for row, rate in zip(source["incomes"], ("0.8", "0.4", "0.3"), strict=True):
            row["value"] = rate
        if kind == "linked":
            source["expenses"][0].update(base_type="none", calc_type="amount", value="10000")
            for row, rate in zip(source["incomes"], ("10", "20", "30"), strict=True):
                row.update(base_type="expense_amount", value=rate)
        elif kind == "fixed":
            source["expenses"][0].update(base_type="none", calc_type="amount", value="10000")
            for row in source["incomes"]:
                row.update(base_type="none", calc_type="amount", value="500")
        elif kind == "clip":
            source["incomes"][0].update(value="1", max="500")
        elif kind == "zero":
            source["expenses"][0]["value"] = "0.01"
            for row in source["incomes"]:
                row.update(base_type="expense_amount", value="10")
        elif kind == "cent_groups":
            source["expenses"] = [
                {"local_id": key, "participant_type": "leasing", "base_type": "none", "calc_type": "amount", "value": value}
                for key, value in (("expense-1", "100.01"), ("expense-2", "200.02"), ("expense-empty", "50.05"))
            ]
            source["incomes"] = [
                {"local_id": key, "participant_type": party, "base_type": "none", "calc_type": "amount", "value": value, "expense_ref": expense}
                for key, party, value, expense in (
                    ("income-dealer", "dealer", "33.33", "expense-1"),
                    ("income-distributor", "distributor", "20.01", "expense-1"),
                    ("income-platform", "platform", "10.00", "expense-1"),
                    ("income-second-dealer", "dealer", "40.01", "expense-2"),
                    ("income-second-distributor", "distributor", "30.02", "expense-2"),
                )
            ]
        elif kind == "cent_rounding":
            source["expenses"][0].update(base_type="none", calc_type="amount", value="100.05")
            for row, rate in zip(source["incomes"], ("10", "2", "3"), strict=True):
                row["value"] = rate
        elif kind == "cent_history":
            source["expenses"][0]["value"] = "40"
        programs[kind] = await api.request("admin", "POST", "/api/v1/admin/monetization/programs", 201, json=draft)

    deals = {}
    cases = {
        "api_property": "property", "api_linked": "linked",
        "ui_main": "property", "ui_stale": "property",
        "ui_768": "property", "ui_1280": "property", "ui_1920": "property",
        "ui_fixed": "fixed", "ui_clip": "clip", "ui_zero": "zero",
        "api_cent_groups": "cent_groups", "ui_cent_groups": "cent_groups",
        "api_cent_rounding": "cent_rounding", "ui_cent_rounding": "cent_rounding",
        "api_cent_history": "cent_history", "ui_cent_history": "cent_history",
    }
    async with AsyncSessionLocal() as session:
        for alias, kind in cases.items():
            program = await repo.get_program(session, UUID(programs[kind]["id"]))
            require(program is not None, "Program missing")
            context = {
                "source_type": "platform", "application_id": uuid4(),
                "leasing_company_application_id": uuid4(),
                "application_number": f"22268-{run}-{alias}",
                "leasing_company_id": identifier("leasing-company"),
                "dealer_company_id": identifier("company/dealer"),
                "distributor_company_id": identifier("company/distributor"),
                "client_company_id": identifier("company/client"),
                "base_amount": Decimal("1" if kind == "zero" else "100.05" if kind == "cent_rounding" else "123456"),
                "occurred_at": datetime.now(UTC),
                "vehicles": [{"vehicle_id": identifier("vehicle/ui"), "brand": program["brand"], "quantity": 1}],
                "actor_user_id": identifier("user/admin"),
            }
            session.add(LeasingApplication(id=context['application_id'], company_id=identifier('company/client'),
                dealer_company_id=identifier('company/dealer'), created_by=identifier('user/admin'),
                source_type='platform', display_number=context['application_number'], total_amount=context['base_amount']))
            await session.flush()
            session.add(LeasingCompanyApplication(id=context['leasing_company_application_id'],
                application_id=context['application_id'], leasing_company_id=identifier('leasing-company')))
            await session.flush()
            captured = await repo.insert_deal(session, context, program, calculate_program(program, context))
            if kind == "cent_history":
                # Model already-saved pre-cents overrides only in new isolated fixtures.
                historical = {
                    "dealer": ("28873.00", "23.38743238", "percent"),
                    "distributor": ("493.82", "0.40000234", "amount"),
                    "platform": ("1235.00", "1", "percent"),
                }
                for row in captured["amounts"]:
                    if row["side"] != "income":
                        continue
                    value, percent, mode = historical[row["participant_type"]]
                    await session.execute(update(m.amounts).where(
                        m.amounts.c.id == row["id"], m.amounts.c.deal_id == captured["id"],
                    ).values(amount=Decimal(value), percent=Decimal(percent), input_mode=mode))
                    await session.execute(insert(m.adjustments).values(
                        deal_id=captured["id"], amount_id=row["id"], revision=2,
                        old_value=row["amount"], new_value=Decimal(value),
                        old_percent=row.get("percent"), new_percent=Decimal(percent),
                        old_input_mode=row.get("input_mode"), new_input_mode=mode,
                        created_by=identifier("user/admin"),
                    ))
                await session.execute(update(m.deals).where(m.deals.c.id == captured["id"]).values(revision=2))
            deals[alias] = str(captured["id"])
        await session.commit()
    main = json.loads((ROOT / "manifest.json").read_text())
    manifest = {"marker": MARKER, "run": run, "base_url": main["base_url"],
                "storage_states": main["storage_states"], "deals": deals}
    private_json(ROOT / "terms.manifest.json", manifest)
    progress("saved_percent_fixtures_ready", count=len(deals), path=str(HOST_ROOT / "terms.manifest.json"))


async def verify_tiny(api: API | None = None):
    """Use an independent deal: never reset or consume browser fixture IDs."""
    from sqlalchemy import insert, select, update
    from infrastructure.models.notification_delivery import NotificationEventOutbox
    from domain.monetization.programs import calculate_program
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as m
    from infrastructure.models.applications import LeasingApplication, LeasingCompanyApplication
    from infrastructure.repositories import monetization_repository as repo

    api = api or API(state())
    run = uuid4().hex[:10]
    draft = program_payload(f"22268 tiny-percent {run}", "platform", active=True)
    draft["brand"] = "TERMS-TINY-" + run
    program_out = await api.request("admin", "POST", "/api/v1/admin/monetization/programs", 201, json=draft)
    async with AsyncSessionLocal() as session:
        program = await repo.get_program(session, UUID(program_out["id"]))
        require(program is not None, "Tiny-percent condition missing")
        context = {
            "source_type": "platform", "application_id": uuid4(),
            "leasing_company_application_id": uuid4(),
            "application_number": f"22268-{run}-tiny",
            "leasing_company_id": identifier("leasing-company"),
            "dealer_company_id": identifier("company/dealer"),
            "distributor_company_id": identifier("company/distributor"),
            "client_company_id": identifier("company/client"),
            "base_amount": Decimal("10000000000"),
            "occurred_at": datetime.now(UTC),
            "vehicles": [{"vehicle_id": identifier("vehicle/ui"), "brand": program["brand"], "quantity": 1}],
            "actor_user_id": identifier("user/admin"),
        }
        session.add(LeasingApplication(
            id=context["application_id"], company_id=identifier("company/client"),
            dealer_company_id=identifier("company/dealer"), created_by=identifier("user/admin"),
            source_type="platform", display_number=context["application_number"],
            total_amount=context["base_amount"],
        ))
        await session.flush()
        session.add(LeasingCompanyApplication(
            id=context["leasing_company_application_id"],
            application_id=context["application_id"], leasing_company_id=identifier("leasing-company"),
        ))
        await session.flush()
        captured = await repo.insert_deal(session, context, program, calculate_program(program, context))
        deal_id = str(captured["id"])
        await session.commit()

    url = "/api/v1/monetization/deals/" + deal_id
    deal = await api.request("admin", "GET", url)
    income = next(item for item in deal["incomes"] if item["participant_type"] == "dealer")
    await api.request(
        "admin", "POST", "/api/v1/admin/monetization/deals/" + deal_id + "/adjust-conditions", 400,
        json={"revision": deal["revision"], "items": [{
            "deal_participant_amount_id": income["id"], "input_mode": "percent",
            "new_percent": "0.00000001",
        }]},
    )
    unchanged = await api.request("admin", "GET", url)
    for key in ("revision", "expenses", "incomes", "confirmations", "has_new_conditions"):
        require(unchanged[key] == deal[key], "New tiny percentage rejection was not atomic: " + key)
    async with AsyncSessionLocal() as session:
        require(not (await session.scalars(select(m.adjustments.c.id).where(
            m.adjustments.c.deal_id == UUID(deal_id)))).all(), "Rejected tiny percentage wrote audit")
        require(not (await session.scalars(select(NotificationEventOutbox.event_id).where(
            NotificationEventOutbox.entity_id == UUID(deal_id),
            NotificationEventOutbox.event_type == EVENT))).all(), "Rejected tiny percentage wrote event")
        # Simulate a previously saved tiny percentage, without changing any UI fixture.
        await session.execute(update(m.amounts).where(m.amounts.c.id == UUID(income["id"])).values(
            amount=Decimal("1"), percent=Decimal("0.00000001"), input_mode="percent"))
        await session.execute(insert(m.adjustments).values(
            deal_id=UUID(deal_id), amount_id=UUID(income["id"]), revision=2,
            old_value=Decimal(income["amount"]), new_value=Decimal("1"),
            old_percent=None, new_percent=Decimal("0.00000001"),
            old_input_mode=None, new_input_mode="percent", created_by=identifier("user/admin")))
        await session.execute(update(m.deals).where(m.deals.c.id == UUID(deal_id)).values(revision=2))
        await session.commit()
    historical = await api.request("admin", "GET", url)
    expense = historical["expenses"][0]
    adjusted = await api.request(
        "admin", "POST", "/api/v1/admin/monetization/deals/" + deal_id + "/adjust-conditions",
        json={"revision": historical["revision"], "items": [{
            "deal_participant_amount_id": expense["id"], "input_mode": "amount",
            "new_value": str(Decimal(expense["amount"]) + 1),
        }]},
    )
    for role, response in (
        ("save response", adjusted),
        ("admin reload", await api.request("admin", "GET", url)),
        ("dealer reload", await api.request("dealer", "GET", url)),
    ):
        saved = next(item for item in response["incomes"] if item["id"] == income["id"])
        require(saved["percent"] == "0.00000001", role + ": historical tiny percentage must use plain decimal JSON")
        require(Decimal(saved["amount"]) == Decimal("1"), role + ": unrelated edit changed historical money")
        require(saved["input_mode"] == "percent" and response["has_new_conditions"],
                role + ": historical percentage mode or new conditions were lost")
        require(saved["original_percent"] == income["original_percent"], role + ": original condition overwritten")
    async with AsyncSessionLocal() as session:
        audit = (await session.execute(select(m.adjustments).where(
            m.adjustments.c.amount_id == UUID(income["id"]),
        ))).mappings().all()
        require(len(audit) == 1 and audit[0]["new_percent"] == Decimal("0.00000001"),
                "Unrelated edit rewrote historical tiny percentage audit")
    checks = ["new tiny percentage rounds to zero and is rejected atomically",
              "historical tiny percentage survives unrelated edit and serializes as plain decimal"]
    for check in checks:
        api.passed(check)
    private_json(ROOT / "terms.tiny.results.json", {
        "marker": MARKER, "deal_id": deal_id, "checks": checks, "passed": len(checks),
    })
    progress("tiny_percent_api_complete", passed=len(checks))


async def verify():
    from sqlalchemy import func, select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as m
    from infrastructure.models.notification_delivery import NotificationEventOutbox
    from application.notifications.publisher import _publish
    from infrastructure.messaging.broker import stop_broker

    actors = state()
    api = API(actors)
    fixtures = json.loads((ROOT / "terms.manifest.json").read_text())

    async def get(deal_id, role="admin"):
        return await api.request(role, "GET", "/api/v1/monetization/deals/" + deal_id)

    async def adjust(deal, items, expected=200, role="admin"):
        return await api.request(role, "POST", "/api/v1/admin/monetization/deals/" + deal["id"] + "/adjust-conditions",
                                 expected, json={"revision": deal["revision"], "items": items})

    def row(deal, party="dealer", side="incomes"):
        return next(item for item in deal[side] if item["participant_type"] == party)

    def percent_item(item, value):
        return {"deal_participant_amount_id": item["id"], "input_mode": "percent", "new_percent": value}

    def amount_item(item, value):
        return {"deal_participant_amount_id": item["id"], "input_mode": "amount", "new_value": value}

    def agreement(deal):
        return {key: deal.get(key) for key in ('id', 'revision', 'status', 'expenses', 'incomes', 'confirmations', 'documents', 'has_new_conditions')}

    async def counts(deal_id):
        async with AsyncSessionLocal() as session:
            audit = await session.scalar(select(func.count()).select_from(m.adjustments).where(m.adjustments.c.deal_id == UUID(deal_id)))
            events = await session.scalar(select(func.count()).select_from(NotificationEventOutbox).where(
                NotificationEventOutbox.entity_id == UUID(deal_id), NotificationEventOutbox.event_type == EVENT))
        return audit, events

    async def confirm_parties(deal):
        for role in ("leasing", "dealer", "distributor"):
            await api.request(role, "POST", f"/api/v1/monetization/deals/{deal['id']}/confirm",
                              json={"revision": deal["revision"]})

    async def inbox(role, deal_id, revision):
        response = await api.request(role, "GET", "/api/v1/notifications", params={"limit": 100})
        return [item for item in response["notifications"] if
                (item.get("data") or {}).get("event_type") == EVENT and
                str((item.get("data") or {}).get("entity_id")) == deal_id and
                (item.get("data") or {}).get("revision") == revision]

    async def delivered(deal):
        deadline = asyncio.get_running_loop().time() + 35
        while True:
            records = {role: await inbox(role, deal["id"], deal["revision"]) for role in ROLES}
            if all(len(items) == 1 for items in records.values()):
                break
            require(asyncio.get_running_loop().time() < deadline,
                    "Notification delivery incomplete: " + str({role: len(items) for role, items in records.items()}))
            await asyncio.sleep(0.5)
        for role, items in records.items():
            item = items[0]
            require(deal["id"] in item["action_url"], role + ": wrong action URL")
            require("Изменены условия сделки" in item["message"] and "повторное подтверждение" in item["message"],
                    role + ": wrong notification text")
            require(not {"amount", "percent", "expenses", "incomes"} & item["data"].keys(), "Financial data leaked into notification")
        require(not await inbox("outsider", deal["id"], deal["revision"]), "Unrelated company got notification")
        return records

    deal = await get(fixtures["deals"]["api_property"])
    dealer = row(deal)
    require(Decimal(str(dealer["original_percent"])) == Decimal("0.8"), "Original percentage missing")
    await confirm_parties(deal)
    changed = await adjust(deal, [percent_item(dealer, "1")])
    require(changed["revision"] == deal["revision"] + 1, "No new revision")
    require(Decimal(str(row(changed)["percent"])) == 1 and Decimal(str(row(changed)["amount"])) == Decimal("1234.56"),
            "Entered 1% did not produce 1234.56 with cent rounding")
    require(row(changed)["input_mode"] == "percent", "Percentage input mode not saved")
    require(all(not item["confirmed_at"] for item in changed["confirmations"].values()), "Confirmations were not reset")
    require(changed["has_new_conditions"], "New conditions marker missing")
    for role, party in (("dealer", "dealer"), ("leasing", "leasing"), ("distributor", "distributor"), ("read_only", "distributor")):
        view = await get(deal["id"], role)
        require(view["has_new_conditions"], role + ": persisted new-conditions marker missing")
        require(all(item["participant_type"] == party for item in view["expenses"] + view["incomes"]), role + ": another party's financial row leaked")
        require(all(item.get("calculation_base_amount") is None for item in view["expenses"] + view["incomes"]), role + ": editor base leaked")
    api.passed("exact 1 percent persisted while money rounds; all parties see new conditions and reset confirmations")
    records = await delivered(changed)
    api.passed("real outbox Kafka inbox delivery to five permitted users and no unrelated recipient")

    await api.request("admin", "POST", f"/api/v1/admin/monetization/deals/{deal['id']}/confirm", 409,
                      json={"revision": changed["revision"]})
    await confirm_parties(changed)
    rate_only = await adjust(changed, [percent_item(row(changed), "1.01499999")])
    require(rate_only["revision"] == changed["revision"] + 1, "Normalized rate change did not create a revision")
    require(Decimal(str(row(rate_only)["amount"])) == Decimal("1246.91") and Decimal(str(row(rate_only)["percent"])) == Decimal("1.01"),
            "Raw percentage was not normalized before calculating money")
    require(all(not item["confirmed_at"] for item in rate_only["confirmations"].values()), "Normalized percentage edit left old confirmations")
    await delivered(rate_only)
    api.passed("raw percentage normalizes to 1.01 before money calculation and resets confirmations with notification")

    before = await counts(deal["id"])
    same = await adjust(rate_only, [percent_item(row(rate_only), "1.01499999")])
    require(agreement(same) == agreement(rate_only), "Unchanged conditions produced a different deal")
    require(await counts(deal["id"]) == before, "No-op wrote audit or outbox")
    await adjust(changed, [percent_item(row(changed), "1.1")], 409)
    await api.request("dealer", "POST", f"/api/v1/monetization/deals/{deal['id']}/confirm", 409,
                      json={"revision": changed["revision"]})
    require(await counts(deal["id"]) == before, "Stale operations wrote audit/outbox")
    api.passed("no-op and stale revision preserve saved conditions audit and notifications")

    for item in [
        percent_item(row(rate_only), "99"), percent_item(row(rate_only), "0"),
        amount_item(row(rate_only), "0.004"),
        {**percent_item(row(rate_only), "1"), "new_value": "1235"},
        {**percent_item(row(rate_only), "1"), "deal_participant_amount_id": str(uuid4())},
    ]:
        await adjust(rate_only, [item], (400, 409, 422))
        require(agreement(await get(deal["id"])) == agreement(rate_only) and await counts(deal["id"]) == before, "Invalid edit partially persisted")
    await adjust(rate_only, [percent_item(row(rate_only), "1"), percent_item(row(rate_only), "1")], (400, 409, 422))
    await adjust(rate_only, [percent_item(row(rate_only), "1")], 403, role="read_only")
    await api.request("outsider", "GET", "/api/v1/monetization/deals/" + deal["id"], 404)
    api.passed("budget nonpositive ambiguous duplicate foreign-row and access errors are atomic")

    async with AsyncSessionLocal() as session:
        event = (await session.execute(select(NotificationEventOutbox).where(
            NotificationEventOutbox.event_id == UUID(records["dealer"][0]["event_id"])))).scalar_one()
        payload = deepcopy(event.payload)
    try:
        await _publish(payload)
        await asyncio.sleep(2)
    finally:
        await stop_broker()
    require(all([len(await inbox(role, changed["id"], changed["revision"])) == 1 for role in ROLES]), "Kafka replay duplicated inbox")
    api.passed("replayed Kafka event creates no duplicate user notification")

    linked = await get(fixtures["deals"]["api_linked"])
    expense = row(linked, "leasing", "expenses")
    linked = await adjust(linked, [percent_item(row(linked), "10")])
    require(row(linked)["input_mode"] == "percent", "Explicit percent mode was not saved")
    saved_amount = row(linked)["amount"]
    linked_amount = await adjust(linked, [amount_item(row(linked), str(saved_amount))])
    require(linked_amount["revision"] == linked["revision"] + 1 and row(linked_amount)["input_mode"] == "amount",
            "Mode-only change did not persist as conditions")
    linked = await adjust(linked_amount, [percent_item(row(linked_amount), "10")])
    before_distributor = Decimal(str(row(linked, "distributor")["amount"]))
    linked = await adjust(linked, [amount_item(expense, "12000")])
    require(Decimal(str(row(linked)["percent"])) == 10 and Decimal(str(row(linked)["amount"])) == 1200,
            "Saved exact percentage did not follow its changed expense")
    require(Decimal(str(row(linked, "distributor")["amount"])) == before_distributor,
            "Historical amount-mode income changed unexpectedly")
    require(Decimal(str(row(linked, "distributor")["percent"])) == Decimal("16.67"),
            "Amount-mode equivalent percentage was not refreshed")
    api.passed("saved input mode survives sessions; linked percentage follows expense while amount-mode income stays fixed")
    linked_before = await counts(linked["id"])
    await adjust(linked, [amount_item(expense, "1000")], (400, 409))
    require(agreement(await get(linked["id"])) == agreement(linked) and await counts(linked["id"]) == linked_before,
            "Rejected expense decrease partially cascaded")
    api.passed("invalid expense decrease rolls back dependent percentages amounts and audit")

    competing = await asyncio.gather(
        adjust(linked, [percent_item(row(linked), "11")], (200, 409)),
        adjust(linked, [percent_item(row(linked), "12")], (200, 409)),
    )
    require(sum("id" in result for result in competing) == 1, "Concurrent updates both succeeded or both failed")
    linked = await get(linked["id"])
    require(await counts(linked["id"]) == (linked_before[0] + 1, linked_before[1] + 1),
            "Concurrent request added an extra audit or event")
    api.passed("concurrent revisions serialize to one success and one conflict")

    await confirm_parties(rate_only)
    paid = await api.request("admin", "POST", f"/api/v1/admin/monetization/deals/{deal['id']}/confirm",
                            json={"revision": rate_only["revision"]})
    require(paid["status"] == "paid", "Final approval missing")
    await adjust(paid, [percent_item(row(paid), "1.1")], 409)
    require((await get(paid["id"]))["has_new_conditions"], "Approval erased persisted new-conditions marker")
    api.passed("all parties reconfirm before final payment; paid deal keeps marker and rejects edits")

    cents = await get(fixtures["deals"]["api_cent_rounding"])
    cents = await adjust(cents, [amount_item(row(cents), "16.865")])
    require(Decimal(row(cents)["amount"]) == Decimal("16.87") and
            Decimal(row(cents)["percent"]) == Decimal("16.86") and row(cents)["input_mode"] == "amount",
            "16.865 must become authoritative 16.87 with equivalent 16.86 percent")
    api.passed("manual half-kopeck amount rounds to 16.87 and keeps independently derived 16.86 percent")
    cents = await adjust(cents, [percent_item(row(cents), "23.38743238")])
    require(Decimal(row(cents)["percent"]) == Decimal("23.39") and
            Decimal(row(cents)["amount"]) == Decimal("23.40") and row(cents)["input_mode"] == "percent",
            "New percentage must normalize to 23.39 before calculating 23.40")
    cents_before = await counts(cents["id"])
    same_cents = await adjust(cents, [percent_item(row(cents), "23.38743238")])
    require(agreement(same_cents) == agreement(cents) and await counts(cents["id"]) == cents_before,
            "Repeated raw percentage must be no-op after identical normalization")
    api.passed("23.38743238 normalizes to 23.39 before cent calculation; equivalent raw repeat is no-op")
    for invalid in (
        amount_item(row(cents), "0.004"), percent_item(row(cents), "0.004"),
        amount_item(row(cents), "1.234567891"), percent_item(row(cents), "1.234567891"),
        amount_item(row(cents), "9999999999999999.99999999"),
        percent_item(row(cents), "999999999999999999999999999999.99999999"),
    ):
        await adjust(cents, [invalid], (400, 422))
        require(agreement(await get(cents["id"])) == agreement(cents) and
                await counts(cents["id"]) == cents_before,
                "Zero-after-rounding, nine-decimal input or carry overflow was not atomic")
    api.passed("both inputs reject rounded zero nine decimal places and rounding overflow without writes")
    cents = await adjust(cents, [amount_item(row(cents), "0.005")])
    require(Decimal(row(cents)["amount"]) == Decimal("0.01") and Decimal(row(cents)["percent"]) == Decimal("0.01"),
            "Half-kopeck amount did not round up to one kopeck")
    api.passed("0.005 amount is accepted as 0.01")

    groups = await get(fixtures["deals"]["api_cent_groups"])
    first_expense = next(item for item in groups["expenses"] if Decimal(item["amount"]) == Decimal("100.01"))
    first_dealer = next(item for item in groups["incomes"] if
                        item["expense_ref_amount_id"] == first_expense["id"] and item["participant_type"] == "dealer")
    other_incomes = [item for item in groups["incomes"] if item["expense_ref_amount_id"] != first_expense["id"]]
    groups = await adjust(groups, [amount_item(first_dealer, "33.34")])
    require(sum(Decimal(item["amount"]) for item in groups["incomes"] if
                item["expense_ref_amount_id"] == first_expense["id"]) == Decimal("63.35"),
            "Positive residual prevented a valid income edit")
    require([item for item in groups["incomes"] if item["expense_ref_amount_id"] != first_expense["id"]] == other_incomes,
            "Editing the first group changed another group's income")
    api.passed("positive undistributed balance permits saving 33.34 and keeps other groups unchanged")
    groups = await adjust(groups, [amount_item(first_expense, "63.35")])
    require(Decimal(next(item for item in groups["expenses"] if item["id"] == first_expense["id"])["amount"]) == Decimal("63.35"),
            "Equal expense and total income was rejected")
    group_counts = await counts(groups["id"])
    await adjust(groups, [amount_item(first_expense, "63.34")], (400, 409))
    require(agreement(await get(groups["id"])) == agreement(groups) and await counts(groups["id"]) == group_counts,
            "Deficit borrowed another group's positive balance or persisted partially")
    api.passed("63.35 fully distributed expense is valid; 63.34 cannot borrow from independent group")

    historical = await get(fixtures["deals"]["api_cent_history"])
    require(Decimal(row(historical)["percent"]) == Decimal("23.38743238") and
            Decimal(row(historical)["amount"]) == Decimal("28873.00"), "High precision historical fixture is missing")
    require(Decimal(row(historical, "platform")["percent"]) == 1 and
            Decimal(row(historical, "platform")["amount"]) == 1235, "Historical whole-ruble fixture is missing")
    old_incomes = historical["incomes"]
    history_counts = await counts(historical["id"])
    history_expense = row(historical, "leasing", "expenses")
    historical = await adjust(historical, [amount_item(history_expense, str(Decimal(history_expense["amount"]) + 1))])
    require(historical["incomes"] == old_incomes, "Expense change rewrote unrelated historical income terms")
    require(await counts(historical["id"]) == (history_counts[0] + 1, history_counts[1] + 1),
            "Unrelated expense change added historical income audit")
    api.passed("unrelated expense change preserves historical 23.38743238 and 28873 plus 1 percent and 1235")
    history_counts = await counts(historical["id"])
    distributor = row(historical, "distributor")
    require(Decimal(distributor["percent"]) == Decimal("0.40000234") and distributor["input_mode"] == "amount",
            "Historical amount-mode percentage fixture is missing")
    historical_same = await adjust(historical, [amount_item(distributor, "493.82")])
    require(agreement(historical_same) == agreement(historical) and await counts(historical["id"]) == history_counts,
            "Repeating historical authoritative amount changed percentage revision audit or event")
    api.passed("same 493.82 amount preserves historical 0.40000234 percent as no-op")

    await verify_tiny(api)
    private_json(ROOT / "terms.results.json", {"marker": MARKER, "checks": api.checks, "passed": len(api.checks)})
    progress("saved_percent_api_complete", passed=len(api.checks))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seed", "verify", "verify-tiny"))
    args = parser.parse_args()
    asyncio.run({"seed": seed, "verify": verify, "verify-tiny": verify_tiny}[args.action]())
