"""Persistent financial HTTP E2E on isolated 22296 fixtures; no mocked calculation."""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from monetization import PROGRAMS, program_payload, source_bid, state
from runtime import API, ROOT, private_json, progress, require

DEALS = "/api/v1/monetization/deals/"


def money(actual: str | Decimal | None, expected: str | Decimal, message: str) -> None:
    require(actual is not None and Decimal(actual) == Decimal(expected), message)


def amount_row(row: dict[str, Any], *, amount: str, raw: str, clip: str, limit: str | None, label: str) -> None:
    money(row["amount"], amount, label + ": effective money")
    money(row["original_amount"], amount, label + ": original money")
    money(row["raw_amount"], raw, label + ": formula before limits")
    require(row["clip"] == clip, label + ": clip direction")
    require("applied_limit" in row, label + ": missing nullable applied_limit contract")
    if limit is None:
        require(row["applied_limit"] is None, label + ": invented applied limit")
    else:
        money(row["applied_limit"], limit, label + ": exact applied limit")
    require(not {"condition_min", "condition_max"} & row.keys(), label + ": internal aliases exposed")


async def captured_case(api: API, actors: dict[str, Any], kind: str, *, expense: dict[str, str] | None = None, income: dict[str, str] | None = None) -> dict[str, Any]:
    """Arrange a source, then create conditions/capture/read them via real HTTP."""
    from sqlalchemy import select

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    run = uuid4().hex[:10]
    vin = "F22296" + run.upper() + "0"
    name = f"22296-financial-{kind}-{run}"
    payload = program_payload(actors, name, vin=vin, expense=expense, income=income)
    program = await api.request("admin", "POST", PROGRAMS, 201, json=payload)
    persisted = await api.request("admin", "GET", PROGRAMS + "/" + program["id"])
    for collection in ("expenses", "incomes"):
        for field in ("value", "min", "max"):
            expected = payload["sources"][0][collection][0].get(field)
            actual = persisted["sources"][0][collection][0].get(field)
            if expected is None:
                require(actual is None, kind + ": unexpected saved " + field)
            else:
                money(actual, expected, kind + ": lost saved " + field)
    bid = await source_bid(actors, vin, name, 333000000 + int(run[:5], 16))
    await api.request("leasing", "PUT", "/api/v1/exchange/bids/" + bid["bid_id"] + "/approve")
    async with AsyncSessionLocal() as session:
        ids = (await session.scalars(select(models.deals.c.id).where(
            models.deals.c.exchange_request_id == UUID(bid["request_id"])))).all()
    require(len(ids) == 1, kind + ": expected exactly one captured deal")
    result = await api.request("admin", "GET", DEALS + str(ids[0]))
    await api.request("admin", "PATCH", PROGRAMS + "/" + program["id"], json={"status": "inactive"})
    return result


async def verify_access(api: API, deal: dict[str, Any]) -> None:
    path = DEALS + deal["id"]
    await api.request("guest", "GET", path, expected=401)
    await api.request("client", "GET", path, expected=403)
    await api.request("outsider", "GET", path, expected=404)
    leasing = await api.request("leasing", "GET", path)
    dealer = await api.request("dealer", "GET", path)
    require(len(leasing["expenses"]) == 1 and not leasing["incomes"], "Leasing ACL leaked income")
    require(not dealer["expenses"] and len(dealer["incomes"]) == 1, "Dealer ACL leaked expense")
    money(leasing["expenses"][0]["applied_limit"], "100000", "Visible leasing limit disappeared")
    require(dealer["incomes"][0]["applied_limit"] is None, "Dealer inherited another participant's limit")
    require(not leasing["can_adjust"] and not dealer["can_adjust"], "Partner gained financial edit permission")
    await api.request("dealer", "POST", "/api/v1/admin/monetization/deals/" + deal["id"] + "/adjust-conditions", 403,
        json={"revision": deal["revision"], "items": [{"deal_participant_amount_id": deal["expenses"][0]["id"],
            "input_mode": "amount", "new_value": "125000"}]})
    after = await api.request("admin", "GET", path)
    require(after["revision"] == deal["revision"] and after["expenses"] == deal["expenses"], "Forbidden edit changed financial data")


async def historical_cases(api: API, actors: dict[str, Any]) -> dict[str, str]:
    from sqlalchemy import update

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models import monetization as models

    historical = await captured_case(api, actors, "historical", expense={"max": "100000.49"})
    # Reconstruct the persisted pre-105ea1eb contract: final money was rounded to
    # whole rubles while the immutable source retained its exact fractional max.
    async with AsyncSessionLocal() as session:
        for row, amount in ((historical["expenses"][0], "100000"), (historical["incomes"][0], "30000")):
            await session.execute(update(models.amounts).where(models.amounts.c.id == UUID(row["id"])).values(amount=Decimal(amount)))
        await session.commit()
    historical = await api.request("admin", "GET", DEALS + historical["id"])
    amount_row(historical["expenses"][0], amount="100000", raw="120150", clip="max", limit="100000.49", label="Historical fractional threshold")
    require(historical["revision"] == 1 and not historical["has_new_conditions"], "Reading historical limit rewrote history")

    missing = await captured_case(api, actors, "source-missing", expense={"max": "100000"})
    # The nullable FK is an existing supported historical condition, not a new
    # deletion behavior. Only this private fixture loses its source association.
    async with AsyncSessionLocal() as session:
        await session.execute(update(models.amounts).where(models.amounts.c.id == UUID(missing["expenses"][0]["id"])).values(source_participant_id=None))
        await session.commit()
    missing = await api.request("admin", "GET", DEALS + missing["id"])
    amount_row(missing["expenses"][0], amount="100000", raw="120150", clip="max", limit=None, label="Missing source threshold")
    require(missing["expenses"][0]["original_calc_type"] is None, "Missing source invented original formula")
    return {"historical": historical["id"], "source_missing": missing["id"]}


async def manual_override(api: API, actors: dict[str, Any]) -> dict[str, str]:
    """Program limits govern the original snapshot, not the explicit new terms."""
    deal = await captured_case(api, actors, "manual-override", expense={"max": "100000"})
    original_expense = deal["expenses"][0]
    original_income = deal["incomes"][0]
    path = DEALS + deal["id"]
    adjust = "/api/v1/admin/monetization/deals/" + deal["id"] + "/adjust-conditions"
    # Persist an authoritative income percentage so an expense override also
    # proves that the existing dependent-income recalculation is preserved.
    deal = await api.request("admin", "POST", adjust, json={"revision": deal["revision"], "items": [
        {"deal_participant_amount_id": original_income["id"], "input_mode": "percent", "new_percent": "30"}]})
    for role in ("leasing", "dealer"):
        await api.request(role, "POST", path + "/confirm", json={"revision": deal["revision"]})
    previous_revision = deal["revision"]
    deal = await api.request("admin", "POST", adjust, json={"revision": previous_revision, "items": [
        {"deal_participant_amount_id": original_expense["id"], "input_mode": "amount", "new_value": "125000"}]})
    money(deal["expenses"][0]["amount"], "125000", "Manual amount must be allowed above original maximum")
    money(deal["incomes"][0]["amount"], "37500", "Dependent authoritative percentage was lost")
    require(deal["revision"] == previous_revision + 1 and deal["confirmations_reset"], "Manual override did not reset confirmations once")
    for confirmation in deal["confirmations"].values():
        require(confirmation["confirmed_at"] is None, "Manual override retained stale confirmation")
    await api.request("admin", "POST", adjust, 409, json={"revision": previous_revision, "items": [
        {"deal_participant_amount_id": original_expense["id"], "input_mode": "amount", "new_value": "126000"}]})
    reloaded = await api.request("admin", "GET", path)
    require(reloaded["revision"] == deal["revision"] and reloaded["expenses"] == deal["expenses"], "Stale edit partly changed money")
    deal = await api.request("admin", "POST", adjust, json={"revision": deal["revision"], "items": [
        {"deal_participant_amount_id": original_expense["id"], "input_mode": "percent", "new_percent": "6"}]})
    money(deal["expenses"][0]["amount"], "144180", "Manual percentage unexpectedly reapplied original maximum")
    money(deal["incomes"][0]["amount"], "43254", "Manual percentage did not cascade to linked income")
    reloaded = await api.request("admin", "GET", path)
    expense = reloaded["expenses"][0]
    for field in ("original_amount", "raw_amount", "clip", "applied_limit", "original_percent"):
        require(expense[field] == original_expense[field], "Manual override rewrote original " + field)
    require(expense["input_mode"] == "percent" and reloaded["has_new_conditions"], "New terms lost their persisted mode/marker")
    money(expense["percent"], "6", "New percentage did not survive reload")
    money(reloaded["incomes"][0]["original_amount"], "30000", "Income original snapshot changed")
    below = await captured_case(api, actors, "manual-below-minimum", expense={"min": "150000"})
    below = await api.request("admin", "POST", "/api/v1/admin/monetization/deals/" + below["id"] + "/adjust-conditions",
        json={"revision": below["revision"], "items": [{"deal_participant_amount_id": below["expenses"][0]["id"],
            "input_mode": "percent", "new_percent": "5"}]})
    below = await api.request("admin", "GET", DEALS + below["id"])
    money(below["expenses"][0]["amount"], "120150", "Manual percentage must also be allowed below original minimum")
    money(below["expenses"][0]["original_amount"], "150000", "Manual override rewrote original minimum result")
    money(below["expenses"][0]["applied_limit"], "150000", "Manual override lost original minimum")
    require(below["expenses"][0]["clip"] == "min", "Manual override replaced original minimum direction")
    progress("financial_manual_override_contract_passed", revisions=reloaded["revision"], below_minimum=True)
    return {"manual_override": deal["id"], "manual_below_minimum": below["id"]}


async def verify() -> None:
    actors = state()
    api = API(actors)
    manifest = json.loads((ROOT / "monetization.manifest.json").read_text())
    cases = manifest["cases"]
    require(len(cases) >= 8, "Financial base matrix missing; run monetization.py seed")
    for case in cases:
        result = await api.request("admin", "GET", DEALS + case["deal_id"])
        for side in ("expense", "income"):
            row = result[side + "s"][0]
            # Each baseline expense is 5% of 2,403,000; every income is 30% of
            # the bounded expense before rounding. Expected amounts are constants.
            raw = "120150" if side == "expense" else str(Decimal(case["expense"]) * Decimal("0.30"))
            amount_row(row, amount=case[side], raw=raw, clip=case[side + "_clip"],
                limit=case[side + "_limit"], label=case["kind"] + " " + side)
        reloaded = await api.request("admin", "GET", DEALS + case["deal_id"])
        require(reloaded["expenses"] == result["expenses"] and reloaded["incomes"] == result["incomes"], "GET lost immutable limits")
        if case["kind"] == "maximum":
            await verify_access(api, result)
    progress("financial_primary_percent_matrix_passed", cases=len(cases))

    extras = {}
    for kind, expense, income, amount, clip, limit, income_amount, income_raw, income_clip, income_limit in [
        ("fixed_maximum", {"base_type": "none", "calc_type": "amount", "value": "120150", "max": "100000"}, {}, "100000", "max", "100000", "30000", "30000", "none", None),
        ("fixed_minimum", {"base_type": "none", "calc_type": "amount", "value": "120150", "min": "150000"}, {}, "150000", "min", "150000", "45000", "45000", "none", None),
        ("fixed_income_maximum", {}, {"base_type": "none", "calc_type": "amount", "value": "50000", "max": "25000"}, "120150", "none", None, "25000", "50000", "max", "25000"),
        ("fixed_income_minimum", {}, {"base_type": "none", "calc_type": "amount", "value": "10000", "min": "50000"}, "120150", "none", None, "50000", "10000", "min", "50000"),
        ("property_income_maximum", {}, {"base_type": "property_value", "value": "1", "max": "20000"}, "120150", "none", None, "20000", "24030", "max", "20000"),
    ]:
        result = await captured_case(api, actors, kind, expense=expense, income=income)
        amount_row(result["expenses"][0], amount=amount, raw="120150", clip=clip, limit=limit, label=kind + " expense")
        amount_row(result["incomes"][0], amount=income_amount, raw=income_raw, clip=income_clip, limit=income_limit, label=kind + " income")
        extras[kind] = result["id"]
    extras.update(await historical_cases(api, actors))
    extras.update(await manual_override(api, actors))
    private_json(ROOT / "financial.manifest.json", {"marker": "monetization-22296-financial", "deals": extras})
    progress("financial_limits_http_passed", base_cases=len(cases), extra_cases=len(extras))


if __name__ == "__main__":
    asyncio.run(verify())
