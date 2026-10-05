"""HTTP acceptance of immutable application sources and monetization."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from runtime import API, ROOT, guard, identifier, private_json, progress, require

PATHS = {
    "application": "/api/v1/applications",
    "draft": "/api/v1/applications/draft",
    "commerce": "/api/v1/commerce/leasing-applications",
    "special": "/api/v1/special-equipment/leasing-applications",
}
PREFIXES = {"platform": "AP", "dealer_site": "ADE", "distributor_site": "ADI"}


def items(response):
    for key in ("applications", "items"):
        if key in response:
            return response[key]
    raise AssertionError("Unknown list envelope: " + str(list(response)))


def no_source(value):
    if isinstance(value, dict):
        require("source_type" not in value, "Client response leaked source_type")
        for child in value.values():
            no_source(child)
    elif isinstance(value, list):
        for child in value:
            no_source(child)


async def verify():
    guard()
    from sqlalchemy import delete, select, update
    from sqlalchemy.exc import DBAPIError
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication, LeasingCompanyApplication, LeasingProposal, ApplicationVehicle
    state = json.loads((ROOT / "state.secret.json").read_text())
    manifest = json.loads((ROOT / "manifest.json").read_text())
    api = API(state)
    apps = state["applications"]

    def save():
        private_json(ROOT / "state.secret.json", state)
        manifest["applications"] = apps
        private_json(ROOT / "manifest.json", manifest)

    async def body_for(kind, product_ids, source):
        common = {"company_id": state["companies"]["client"]["company_id"], "source_type": source}
        if kind in {"application", "draft"}:
            return {**common, "name": "22320 source acceptance", "vehicles": [{"product_id": value, "quantity": 1, "custom_price": "1000000"} for value in product_ids]}
        cart_ids = []
        for value in product_ids:
            cart = await api.request("client", "POST", "/api/v1/special-equipment/cart-items", expected=(200,201), json={"product_id": value, "quantity": 1})
            cart_ids.append(cart["cart_item"]["id"])
        if kind == "commerce":
            return {**common, "name": "22320 source acceptance", "items": [{"item": {"type": "special_equipment", "id": value}, "quantity": 1, "cart_item_ids":[cart_ids[index]]} for index, value in enumerate(product_ids)]}
        return {**common, "cart_item_ids": cart_ids}

    async def create(label, kind, owner, source, expected_source, product_index, *, role="client", extra_owner=None):
        if label in apps:
            return apps[label]
        product_ids = [state["products"][f"{owner}/{product_index}"]]
        if extra_owner:
            product_ids.append(state["products"][f"{extra_owner}/{product_index}"])
        requests = state.setdefault("requests", {})
        if label not in requests:
            requests[label] = await body_for(kind, product_ids, source)
            save()
        payload = requests[label]
        if role == "dealer":
            payload["company_id"] = state["companies"]["dealer"]["company_id"]
        headers = {"Idempotency-Key": str(identifier("create-v3/" + label))}
        created = await api.request(role, "POST", PATHS[kind], expected=(200,201), json=payload, headers=headers)
        if role == "client":
            no_source(created)
        else:
            require(created.get("source_type") == expected_source, "Creation response omitted or changed source")
        replay = await api.request(role, "POST", PATHS[kind], expected=200, json=payload, headers=headers)
        require(replay == created, "Idempotency changed exact source projection")
        conflict = {**payload, "source_type": "dealer_site" if source != "dealer_site" else "platform"}
        await api.request(role, "POST", PATHS[kind], expected=409, json=conflict, headers=headers)
        app_id = created["application_id"]
        detail = await api.request("admin", "GET", "/api/v1/applications/" + app_id)
        require(detail["source_type"] == expected_source, f"{label}: expected {expected_source}, actual {detail.get('source_type')}")
        require(not (detail["display_number"] or "").startswith(tuple(PREFIXES.values())), "Prefix altered stored number")
        if role == "client":
            no_source(await api.request("client", "GET", "/api/v1/applications/" + app_id))
        async with AsyncSessionLocal() as session:
            require((await session.get(LeasingApplication, UUID(app_id))).source_type == expected_source, "Source missing in database")
            session.add(LeasingCompanyApplication(id=identifier("lca/" + label), application_id=UUID(app_id), leasing_company_id=UUID(state["companies"]["leasing"]["leasing_company_id"]), status="under_review", submitted_at=datetime.now(UTC)))
            await session.commit()
        apps[label] = {"id": app_id, "source_type": expected_source, "display_number": detail["display_number"], "lca_id": str(identifier("lca/" + label)), "product_ids": product_ids}
        save()
        return apps[label]

    for offset, kind in enumerate(PATHS):
        for index, source in enumerate(PREFIXES):
            owner = "dealer" if source == "dealer_site" else "distributor"
            await create(kind + "-" + source, kind, owner, source, source, offset * 3 + index)
    await create("direct-distributor-input-dealer", "draft", "dealer", "distributor_site", "dealer_site", 13)
    await create("direct-dealer-input-distributor", "draft", "distributor", "dealer_site", "distributor_site", 14)
    await create("mixed-dealer-first", "draft", "dealer", "dealer_site", "dealer_site", 15, extra_owner="distributor")
    await create("mixed-distributor-first", "draft", "distributor", "dealer_site", "distributor_site", 16, extra_owner="dealer")
    await create("dealer-actor-platform", "draft", "dealer", "platform", "platform", 17, role="dealer")
    progress("source_creation_matrix_passed", applications=len(apps))

    for kind in PATHS:
        payload = await body_for(kind, [state["products"]["dealer/20"]], "platform")
        headers = {"Idempotency-Key": str(uuid4())}
        missing = dict(payload)
        missing.pop("source_type")
        await api.request("client", "POST", PATHS[kind], expected=422, json=missing, headers=headers)
        await api.request("client", "POST", PATHS[kind], expected=422, json={**payload, "source_type": "exchange"}, headers=headers)
        await api.request("guest", "POST", PATHS[kind], expected=401, json=payload, headers=headers)
    payload = await body_for("draft", [state["products"]["no-warehouse"]], "dealer_site")
    await api.request("client", "POST", PATHS["draft"], expected=400, json=payload, headers={"Idempotency-Key": str(uuid4())})
    progress("source_validation_and_auth_passed")

    # Establish the existing dealer assignment before exercising participant UI.
    # Creation provenance is already asserted above; assignment cannot rewrite it.
    async with AsyncSessionLocal() as session:
        ui_ids = [UUID(apps["draft-" + source]["id"]) for source in PREFIXES]
        await session.execute(update(LeasingApplication).where(LeasingApplication.id.in_(ui_ids)).values(dealer_company_id=identifier("company/dealer")))
        await session.execute(update(ApplicationVehicle).where(ApplicationVehicle.application_id.in_(ui_ids)).values(dealer_company_id=identifier("company/dealer")))
        await session.commit()
    listing_paths = [("admin", "/api/v1/admin/applications"), ("dealer", "/api/v1/applications"), ("distributor", "/api/v1/applications"), ("leasing", "/api/v1/leasing/applications")]
    source_ids = {source: apps["draft-" + source]["id"] for source in PREFIXES}
    for role, path in listing_paths:
        def listing(response):
            rows = items(response)
            return [row["application"] for row in rows] if role == "leasing" else rows
        for source, prefix in PREFIXES.items():
            app = apps["draft-" + source]
            filtered = listing(await api.request(role, "GET", path, params={"source_type": source, "limit": 100}))
            require(app["id"] in {row["id"] for row in filtered}, role + " source filter missing target")
            require(all(row.get("source_type") == source for row in filtered), role + " filter leaked another source")
            number = app["display_number"]
            digits = "".join(char for char in number if char.isdigit())
            for query in (number, digits, prefix + " " + number, prefix.lower() + digits):
                result = listing(await api.request(role, "GET", path, params={"search": query, "limit": 100}))
                require(app["id"] in {row["id"] for row in result}, role + " search missed " + query)
            wrong = "ADI" if source != "distributor_site" else "ADE"
            result = listing(await api.request(role, "GET", path, params={"search": wrong + digits, "limit": 100}))
            require(app["id"] not in {row["id"] for row in result}, role + " wrong prefix matched")
        multiple = listing(await api.request(role, "GET", path, params={"source_type": "dealer_site,distributor_site", "limit": 100}))
        require({source_ids["dealer_site"], source_ids["distributor_site"]} <= {row["id"] for row in multiple}, role + " multi filter missed sources")
        require(all(row.get("source_type") in {"dealer_site", "distributor_site"} for row in multiple), role + " multi filter included platform")
        await api.request(role, "GET", path, expected=400, params={"source_type": "unknown"})
    for role in ("outsider", "foreign_client"):
        for app in (apps["draft-platform"], apps["draft-dealer_site"], apps["draft-distributor_site"]):
            await api.request(role, "GET", "/api/v1/applications/" + app["id"], expected=(403,404))
        listed = items(await api.request(role, "GET", "/api/v1/applications", params={"source_type": "platform,dealer_site,distributor_site", "limit":100}))
        require(not ({row["id"] for row in listed} & set(source_ids.values())), "Source filter expanded access")
    client_list = await api.request("client", "GET", "/api/v1/applications", params={"limit":100})
    client_filtered = await api.request("client", "GET", "/api/v1/applications", params={"source_type":"not-a-source", "limit":100})
    no_source(client_list)
    no_source(client_filtered)
    require({row["id"] for row in items(client_list)} == {row["id"] for row in items(client_filtered)}, "Client filter was applied")
    for key in ("legacy-null", "legacy-dealer-account"):
        detail = await api.request("admin", "GET", "/api/v1/applications/" + apps[key]["id"])
        require(detail.get("source_type") == apps[key]["source_type"], "Historical source rewritten")
    progress("source_role_filters_search_visibility_passed")

    app = apps["mixed-dealer-first"]
    async with AsyncSessionLocal() as session:
        await session.execute(delete(LeasingCompanyApplication).where(LeasingCompanyApplication.id == UUID(app["lca_id"])))
        await session.commit()
    await api.request("client", "PUT", "/api/v1/applications/" + app["id"] + "/conditions", json={"lease_term_months": 36, "source_type":"platform"})
    detail = await api.request("admin", "GET", "/api/v1/applications/" + app["id"])
    require(detail["source_type"] == "dealer_site", "Conditions changed immutable source")
    line = detail["items"][0]
    await api.request("client", "PUT", "/api/v1/applications/" + app["id"] + "/items", json={"items":[{"line_id":line["id"], "kind":line["type"], "comment":"22320 source remains", "regions":[]}]})
    require((await api.request("admin","GET","/api/v1/applications/"+app["id"]))["source_type"] == "dealer_site", "Item edit changed source")
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(update(LeasingApplication).where(LeasingApplication.id == UUID(app["id"])).values(source_type="platform"))
            await session.flush()
        except DBAPIError:
            await session.rollback()
        else:
            await session.rollback()
            raise AssertionError("Database allowed rewriting immutable source")
    progress("source_immutable_passed")

    for source in PREFIXES:
        app = apps["application-" + source]
        program_payload = {
            "name":"22320 " + source, "status":"inactive", "leasing_company_id":state["companies"]["leasing"]["leasing_company_id"],
            "dealer_company_id":state["companies"]["dealer"]["company_id"], "distributor_company_id":state["companies"]["distributor"]["company_id"],
            "period_start":str(datetime.now(UTC).date() - timedelta(days=1)),
            "sources":[{"source_type":source, "expenses":[{"local_id":"expense", "participant_type":"leasing", "base_type":"property_value", "calc_type":"percent", "value":"1"}], "incomes":[]}],
        }
        existing = items(await api.request("admin", "GET", "/api/v1/monetization/deals", params={"page_size":100}))
        prior = [deal for deal in existing if deal["application_number"] == app["display_number"]]
        if prior:
            require(len(prior) == 1, "Duplicate monetization capture")
            saved = await api.request("admin","GET","/api/v1/monetization/deals/"+prior[0]["id"])
            require(saved["source_type"] == source and saved["application_id"] == app["id"] and saved["program_name"] == program_payload["name"], "Persisted monetization source mismatch")
            app["deal_id"] = saved["id"]
            save()
            continue
        program = await api.request("admin","POST","/api/v1/admin/monetization/programs",expected=201,json=program_payload)
        await api.request("admin","PATCH","/api/v1/admin/monetization/programs/"+program["id"],json={"status":"active"})
        async with AsyncSessionLocal() as session:
            await session.execute(update(LeasingApplication).where(LeasingApplication.id==UUID(app["id"])).values(dealer_company_id=UUID(state["companies"]["dealer"]["company_id"])))
            await session.execute(update(ApplicationVehicle).where(ApplicationVehicle.application_id==UUID(app["id"])).values(dealer_company_id=UUID(state["companies"]["dealer"]["company_id"])))
            await session.execute(update(LeasingCompanyApplication).where(LeasingCompanyApplication.id==UUID(app["lca_id"])).values(status="selected_lc"))
            session.add(LeasingProposal(id=identifier("proposal/"+source),leasing_company_application_id=UUID(app["lca_id"]),kind="final",total_amount=Decimal("1000000"),down_payment=Decimal("200000"),down_payment_percent=Decimal("20"),lease_term_months=36,monthly_payment=Decimal("30000"),client_decision_action="accepted"))
            await session.commit()
        await api.request("dealer","POST","/api/v1/leasing/applications/"+app["id"]+"/confirm-deal",expected=403)
        confirmed = await api.request("leasing","POST","/api/v1/leasing/applications/"+app["id"]+"/confirm-deal")
        require(confirmed["status"]=="deal", "LCA did not enter deal")
        deals = items(await api.request("admin","GET","/api/v1/monetization/deals",params={"page_size":100}))
        matched = [deal for deal in deals if deal["application_number"] == app["display_number"]]
        require(len(matched)==1, "LCA transition did not capture exactly one deal for "+source)
        deal = await api.request("admin","GET","/api/v1/monetization/deals/"+matched[0]["id"])
        require(deal["source_type"]==source and deal["program_id"]==program["id"], "Monetization used wrong source conditions")
        repeated = await api.request("leasing","POST","/api/v1/leasing/applications/"+app["id"]+"/confirm-deal")
        require(repeated["status"]=="deal", "Confirm replay failed")
        app["deal_id"] = deal["id"]
        save()
    for source in ("quick_deal_dealer","quick_deal_distributor","leasing_to_dealer","dealer_to_leasing"):
        payload = {**program_payload, "name":"22320 forbidden", "sources":[{"source_type":source,"expenses":[],"incomes":[]}]}
        await api.request("admin","POST","/api/v1/admin/monetization/programs",expected=(400,422),json=payload)
    progress("source_monetization_real_lca_transition_passed")
    private_json(ROOT/"http-results.json", {"result":"PASS", "checked_at":datetime.now(UTC), "checks":["four creation routes and idempotency", "three sources and first warehouse", "actor platform override", "mixed composition first item", "required/invalid source and auth", "four roles filters and normalized prefix search", "foreign company isolation", "client source omission and filter ignored", "historical values", "source immutability", "three real LCA transitions and monetization source matching"]})
    save()
    progress("source_http_acceptance_passed")
