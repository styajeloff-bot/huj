"""Real HTTP regression for every purpose on application transport lines."""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from acceptance import API, ROOT, guard, private_json, progress, require


async def catalog_fixture():
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from infrastructure.models.special_equipment import SpecialEquipmentMark, SpecialEquipmentModel, SpecialEquipmentModification, SpecialEquipmentProduct
    from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
    from infrastructure.models.vehicles import Warehouse, WarehouseMark
    from domain.storefronts import DEFAULT_STOREFRONT_ID

    suffix = uuid4().hex[:10]
    async with AsyncSessionLocal() as session:
        seller = Company(id=uuid4(), name="22286 purpose seller", inn="8" + str(uuid4().int % 10**9).zfill(9), company_type="dealer", is_active=True)
        session.add(seller)
        mark = SpecialEquipmentMark(id=uuid4(), code="purpose-"+suffix, name="Purpose "+suffix, slug="purpose-"+suffix)
        session.add(mark)
        await session.flush()
        model = SpecialEquipmentModel(id=uuid4(), mark_id=mark.id, code="purpose-model-"+suffix, name="Purpose model", slug="purpose-model-"+suffix)
        session.add(model)
        await session.flush()
        warehouse = Warehouse(id=uuid4(), name="Purpose warehouse", owner_company_id=seller.id, owner_company_type="dealer", address="Москва", is_active=True)
        session.add(warehouse)
        if await session.get(Storefront, DEFAULT_STOREFRONT_ID) is None:
            session.add(Storefront(id=DEFAULT_STOREFRONT_ID, is_default=True, is_active=True, version=1))
        await session.flush()
        session.add(WarehouseMark(warehouse_id=warehouse.id, mark_id=mark.id))
        session.add(StorefrontWarehouse(storefront_id=DEFAULT_STOREFRONT_ID, warehouse_id=warehouse.id))
        products = []
        modifications = []
        for index in range(9):
            code = f"purpose-{suffix}-{index}"
            modification = SpecialEquipmentModification(id=uuid4(), model_id=model.id, code=code, name=code, slug=code)
            session.add(modification)
            await session.flush()
            product = SpecialEquipmentProduct(id=uuid4(), code=code, slug=code, modification_id=modification.id, seller_company_id=seller.id, warehouse_id=warehouse.id, price=Decimal("1000000"), condition="new", no_vin=False, vin=f"X22{suffix.upper()}{index:04d}", manufacture_year=2026, publication_status="published", sale_status="available", published_at=datetime.now(UTC))
            session.add(product)
            products.append(str(product.id)); modifications.append(str(modification.id))
        await session.commit()
    return products, modifications


async def verify():
    guard()
    state = json.loads((ROOT / "state.secret.json").read_text())
    manifest = json.loads((ROOT / "manifest.json").read_text())
    api = API(state)
    products, modifications = await catalog_fixture()
    company_id = state["companies"]["client"]["company_id"]
    legacy = "Перевозка; сотрудников, клиентов"
    async def create(vehicles, endpoint="/api/v1/applications/draft"):
        result = await api.request("client", "POST", endpoint, expected=201, headers={"Idempotency-Key": str(uuid4())}, json={"source_type": "platform", "company_id": company_id, "vehicles": vehicles, "calculation": {"total_amount": "2000000", "down_payment_percent": 20, "lease_term_months": 36}})
        return result["application_id"]
    def vehicle(index, **values):
        return {"product_id": products[index], "quantity": 1, "custom_price": "1000000", **values}
    async def read(app_id):
        response = await api.request("client", "GET", f"/api/v1/questionnaire/{app_id}")
        return response["questionnaire"]
    async def projection(app_id, expected):
        q = await read(app_id)
        require(q["vehicle_purchase_purpose"] == {"vehicles": sorted(expected, key=lambda row: row["vehicle_id"])}, "Purpose projection mismatch")
        from sqlalchemy import func, select
        from infrastructure.database import AsyncSessionLocal
        from infrastructure.models.applications import ApplicationQuestionnaire
        async with AsyncSessionLocal() as session:
            count = await session.scalar(select(func.count()).select_from(ApplicationQuestionnaire).where(ApplicationQuestionnaire.application_id == UUID(app_id)))
            require(count == 1, "More than one questionnaire per application")
        return q
    app_id = await create([vehicle(0, leasing_purposes=["business", "staff"]), vehicle(1, leasing_purpose=legacy)])
    detail = await api.request("client", "GET", f"/api/v1/applications/{app_id}")
    by_product = {row["vehicle_id"]: row["id"] for row in detail["vehicles"]}
    first, second = by_product[products[0]], by_product[products[1]]
    q = await projection(app_id, [{"vehicle_id": first, "purposes": ["business", "staff"]}, {"vehicle_id": second, "purposes": [legacy]}])
    q_id = q["id"]
    await api.request("client", "PUT", f"/api/v1/questionnaire/{app_id}", json={"vehicle_purchase_purpose": {"vehicles": [{"vehicle_id": str(uuid4()), "purposes": ["forged"]}]}})
    require((await read(app_id))["vehicle_purchase_purpose"] == q["vehicle_purchase_purpose"], "Direct questionnaire write forged application purposes")
    update = {"items": [{"line_id": first, "kind": "vehicle", "leasing_purposes": ["personal", "business"]}, {"line_id": second, "kind": "vehicle", "leasing_purposes": [legacy, "staff"]}]}
    await api.request("outsider", "PUT", f"/api/v1/applications/{app_id}/items", expected=(403,404), json=update)
    before_update = await read(app_id)
    await api.request("client", "PUT", f"/api/v1/applications/{app_id}/items", json=update)
    after_update = await projection(app_id, [{"vehicle_id": first, "purposes": ["personal", "business"]}, {"vehicle_id": second, "purposes": [legacy, "staff"]}])
    require(datetime.fromisoformat(after_update["updated_at"]) > datetime.fromisoformat(before_update["updated_at"]), "Changed purposes did not update questionnaire timestamp")
    await api.request("client", "PUT", f"/api/v1/applications/{app_id}/items", json=update)
    require((await read(app_id))["updated_at"] == after_update["updated_at"], "Unchanged purpose projection changed questionnaire timestamp")
    await api.request("client", "PUT", f"/api/v1/applications/{app_id}/items", expected=422, json={"items": [{"line_id": first, "kind": "vehicle", "leasing_purposes": ["invented"]}]})
    await api.request("client", "PUT", f"/api/v1/applications/{app_id}/items", json={"items": [{"line_id": first, "kind": "vehicle", "leasing_purposes": []}]})
    await projection(app_id, [{"vehicle_id": first, "purposes": []}, {"vehicle_id": second, "purposes": [legacy, "staff"]}])
    before_remove = await read(app_id)
    await api.request("admin", "DELETE", f"/api/v1/distributor/application-vehicles/{second}")
    after_remove = await projection(app_id, [{"vehicle_id": first, "purposes": []}])
    require(datetime.fromisoformat(after_remove["updated_at"]) > datetime.fromisoformat(before_remove["updated_at"]), "Removed transport did not update questionnaire timestamp")
    await api.request("client", "PUT", f"/api/v1/applications/{app_id}/vehicles", json={"vehicles": [vehicle(2, leasing_purposes=["taxi", "business"])]})
    detail = await api.request("client", "GET", f"/api/v1/applications/{app_id}")
    replacement = detail["vehicles"][0]["id"]
    final = await projection(app_id, [{"vehicle_id": replacement, "purposes": ["taxi", "business"]}])
    require(final["id"] == q_id and replacement != first, "Replacement changed questionnaire identity or retained old line")
    # The manual/model-order path has no catalog product ID. The application line UUID remains authoritative.
    manual = await create([{"product_id": None, "modification_id": modifications[8], "is_model_order": True, "quantity": 1, "custom_price": "1000000", "leasing_purposes": ["management", "staff"]}], endpoint="/api/v1/applications")
    detail = await api.request("client", "GET", f"/api/v1/applications/{manual}")
    await projection(manual, [{"vehicle_id": detail["vehicles"][0]["id"], "purposes": ["management", "staff"]}])
    # No artificial count cap: every supplied legacy-compatible selection is projected.
    many_selected = [f"Цель технической проверки {index}" for index in range(31)]
    many = await create([{"product_id": None, "modification_id": modifications[8], "is_model_order": True, "quantity": 1, "custom_price": "1000000", "leasing_purposes": many_selected}])
    require((await read(many))["vehicle_purchase_purpose"]["vehicles"][0]["purposes"] == many_selected, "Selected purposes were capped or truncated")
    # Both equipment creation paths must initialize the whole questionnaire even
    # during provider outages, without losing the already inserted purpose projection.
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company
    from application.special_equipment_commerce import CreateLeasingApplicationCommand, create_leasing_application
    async with AsyncSessionLocal() as session:
        company = await session.get(Company, UUID(company_id))
        require(company is not None, "Fixture company missing")
        expected_name = company.full_name or company.name
        expected_inn = company.inn
    default_documents = {
        "loans_credits_leasing": "Данные о кредитах, займах и лизинге отсутствуют",
        "third_party_guarantees": "Данные о поручительствах за третьих лиц отсутствуют",
        "additional_collateral_available": "Данные о возможности предоставления дополнительного обеспечения отсутствуют",
        "state_defense_order": "Документ о гособоронзаказе не предоставлен",
        "director_appointment_document": "Документ о назначении руководителя не предоставлен",
    }
    async def initialized_equipment(app_id, purposes):
        q = await read(app_id)
        require(q["full_company_name"] == expected_name and q["inn"] == expected_inn, "Equipment questionnaire omitted company fallback")
        for field, text in default_documents.items():
            require(q[field] == {"status": "missing", "text": text, "documents": []}, "Equipment questionnaire omitted document absence: " + field)
        for field in ("postal_address_matches_legal", "website_in_blocked_domains_registry", "director_is_pdl", "director_name_changed"):
            require(q[field] is False, "Equipment questionnaire omitted default flag: " + field)
        require(len(q["vehicle_purchase_purpose"]["vehicles"]) == 1, "Equipment initialization duplicated or removed purpose rows")
        await projection(app_id, [{"vehicle_id": q["vehicle_purchase_purpose"]["vehicles"][0]["vehicle_id"], "purposes": purposes}])
        return q
    mode_path = ROOT / "provider-mode.json"
    previous_mode = mode_path.read_text() if mode_path.exists() else None
    private_json(mode_path, "unavailable")
    try:
        # Direct product command has no current public create endpoint; use its
        # real transaction then verify access and persisted data through HTTP.
        async with AsyncSessionLocal() as session:
            direct = await create_leasing_application(CreateLeasingApplicationCommand(
                source_type="platform", user_id=UUID(state["users"]["client"]["id"]),
                company_id=UUID(company_id), product_id=UUID(products[6]), actor_role="client",
                leasing_purposes=["business", "personal"], down_payment_percent=Decimal("20"), lease_term_months=36,
            ), session)
            await session.commit()
        await initialized_equipment(str(direct["application_id"]), ["business", "personal"])
        cart = await api.request("client", "POST", "/api/v1/special-equipment/cart-items", expected=(200,201), json={"product_id": products[3], "quantity": 1})
        equipment = await api.request("client", "POST", "/api/v1/special-equipment/leasing-applications", expected=201, headers={"Idempotency-Key": str(uuid4())}, json={"source_type": "platform", "company_id": company_id, "cart_item_ids": [cart["cart_item"]["id"]], "leasing_purposes": ["business", "staff"], "down_payment_percent": "20", "lease_term_months": 36})
        await initialized_equipment(equipment["application_id"], ["business", "staff"])
    finally:
        if previous_mode is None:
            mode_path.unlink(missing_ok=True)
        else:
            mode_path.write_text(previous_mode)
    se_id = equipment["application_id"]
    detail = await api.request("client", "GET", f"/api/v1/applications/{se_id}")
    se_line = detail["items"][0]["id"]
    se_q = await read(se_id)
    require(len(se_q["vehicle_purchase_purpose"]["vehicles"]) == 1, "Equipment mirror duplicated questionnaire transport")
    await api.request("client", "PUT", f"/api/v1/applications/{se_id}/items", json={"items": [{"line_id": se_line, "kind": "special_equipment", "leasing_purposes": ["management", "personal"]}]})
    require((await read(se_id))["vehicle_purchase_purpose"]["vehicles"][0]["purposes"] == ["management", "personal"], "Equipment item update did not sync mirror")
    # Common checkout endpoint must retain arrays on both adapters.
    cart = await api.request("client", "POST", "/api/v1/special-equipment/cart-items", expected=(200,201), json={"product_id": products[5], "quantity": 1})
    mixed = await api.request("client", "POST", "/api/v1/commerce/leasing-applications", expected=201, headers={"Idempotency-Key": str(uuid4())}, json={"source_type": "platform", "company_id": company_id, "down_payment_percent": "20", "lease_term_months": 36, "items": [{"item": {"type": "vehicle", "id": products[4]}, "quantity": 1, "leasing_purposes": ["business", "staff"]}, {"item": {"type": "special_equipment", "id": products[5]}, "quantity": 1, "cart_item_ids": [cart["cart_item"]["id"]], "leasing_purposes": ["management", "other"], "leasing_purpose_comment": legacy}]})
    mixed_q = await read(mixed["application_id"])
    actual = [entry["purposes"] for entry in mixed_q["vehicle_purchase_purpose"]["vehicles"]]
    require(len(actual) == 2 and ["business", "staff"] in actual and ["management", legacy] in actual, "Common commerce adapter dropped selected purposes")
    manifest["purpose_ui_application_id"] = app_id
    manifest["purpose_ui_line_id"] = replacement
    private_json(ROOT / "manifest.json", manifest)
    progress("purpose_acceptance_passed", application_id=app_id, paths=["draft", "create", "items", "replace", "delete", "equipment-cart", "equipment-direct-command", "commerce"], checks=["all-purposes", "timestamps-change-only", "equipment-defaults", "source-outage-fallback"])


if __name__ == "__main__":
    asyncio.run(verify())
