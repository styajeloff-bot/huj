"""Real HTTP/DB regression: transport line UUIDs do not satisfy required purposes."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

from acceptance import API, ROOT, db_questionnaire, guard, new_application, progress, require
from purpose_acceptance import catalog_fixture


async def require_no_delivery(app_id):
    from sqlalchemy import func, select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingCompanyApplication
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(LeasingCompanyApplication).where(
            LeasingCompanyApplication.application_id == UUID(app_id)))
    require(count == 0, "Failed required-purpose gate created LC links")
    require((await db_questionnaire(app_id))["questionnaire_completed_at"] is None, "Failed gate set delivery timestamp")


async def verify():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    lc_ids = [state["companies"][alias]["leasing_company_id"] for alias in ("lc_a", "lc_b")]
    settings_paths = [f"/api/v1/leasing/companies/{lc_id}/questionnaire-settings" for lc_id in lc_ids]
    saved_rules = [(await api.request("admin", "GET", path))["fields"] for path in settings_paths]
    products, _ = await catalog_fixture()

    async def configure(required):
        await api.request("admin", "PUT", settings_paths[0], json={"fields": [
            {"field": "vehicle_purchase_purpose", "enabled": True, "required": required}
        ]})
        await api.request("admin", "PUT", settings_paths[1], json={"fields": []})

    async def create(start):
        response = await api.request("client", "POST", "/api/v1/applications", expected=201,
            headers={"Idempotency-Key": str(uuid4())}, json={
                "source_type": "platform", "company_id": state["companies"]["client"]["company_id"],
                "name": "22286 required purposes",
                "vehicles": [{"product_id": products[index], "quantity": 1, "custom_price": "1000000", "leasing_purposes": []} for index in (start, start + 1)],
                "calculation": {"total_amount": "2000000", "down_payment_percent": 20, "lease_term_months": 36},
            })
        app_id = response["application_id"]
        detail = await api.request("client", "GET", f"/api/v1/applications/{app_id}")
        return app_id, [item["id"] for item in detail["vehicles"]]

    async def assign(app_id, expected):
        response = await api.request("admin", "PUT", f"/api/v1/admin/applications/{app_id}/assign-leasing-companies",
            expected=expected, json={"leasing_company_ids": lc_ids})
        if expected == 422:
            require("Цели приобретения ТС" in response["detail"], "Assignment failed for an unrelated reason")
            await require_no_delivery(app_id)
        return response

    async def set_purposes(app_id, line_id, purposes):
        await api.request("client", "PUT", f"/api/v1/applications/{app_id}/items",
            json={"items": [{"line_id": line_id, "kind": "vehicle", "leasing_purposes": purposes}]})

    try:
        await configure(True)
        # Existing incomplete application without positions must not pass either.
        no_positions = await new_application(state)
        await api.request("client", "PUT", f"/api/v1/questionnaire/{no_positions}", json={})
        await assign(no_positions, 422)

        app_id, lines = await create(0)
        before = await db_questionnaire(app_id)
        require(len(before["vehicle_purchase_purpose"]["vehicles"]) == 2, "Fixture has no real transport positions")
        require(all(not item["purposes"] for item in before["vehicle_purchase_purpose"]["vehicles"]), "Fixture already has purposes")
        await assign(app_id, 422)
        await set_purposes(app_id, lines[0], ["business"])
        await assign(app_id, 422)
        await set_purposes(app_id, lines[1], ["staff"])
        result = await assign(app_id, 200)
        after = await db_questionnaire(app_id)
        require(result["new_links_count"] == 2 and after["questionnaire_completed_at"], "Complete purposes did not deliver to both LCs")
        require(after["id"] == before["id"], "Gate replaced questionnaire")

        await configure(False)
        optional_app, _ = await create(2)
        result = await assign(optional_app, 200)
        require(result["new_links_count"] == 2 and (await db_questionnaire(optional_app))["questionnaire_completed_at"], "Optional purposes became a new mandatory requirement")
        progress("required_vehicle_purposes_assignment_passed", application_id=app_id, optional_application_id=optional_app)
    finally:
        for path, fields in zip(settings_paths, saved_rules, strict=True):
            await api.request("admin", "PUT", path, json={"fields": [
                {key: item[key] for key in ("field", "enabled", "required")} for item in fields
            ]})


if __name__ == "__main__":
    asyncio.run(verify())
