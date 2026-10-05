"""Real task 22320 checks against an isolated Docker application."""
from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4, uuid5

ROOT = Path("/runtime")
HOST_ROOT = Path("/tmp/carcraft-22320-e2e")
BASE_URL = "http://localhost:18320"
MARKER = "application-sources-22320"


def identifier(name):
    return uuid5(UUID("a2222320-0000-4000-8000-000000000001"), name)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def progress(stage, **values):
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False, default=str), flush=True)


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    path.chmod(0o600)


def guard():
    from infrastructure.settings import settings
    require(settings.db_host == "postgres" and settings.db_name == "applicationsources22320", "Refusing non-fixture DB")
    require(settings.s3_bucket == "applicationsources22320" and settings.s3_endpoint == "http://minio:9000", "Refusing external storage")
    require(settings.jwt_keys_dir == "/runtime/jwt" and Path.cwd() == ROOT and not (ROOT / ".env").exists(), "Refusing project credentials")
    require(not settings.dadata_api_key and not settings.smsc_login and not settings.smtp_host, "Refusing external credentials")
    return settings


def keys():
    guard()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    directory = ROOT / "jwt"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not (directory / "e2e.pem").exists():
        key = ec.generate_private_key(ec.SECP256R1())
        (directory / "e2e.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (directory / "e2e.pub.pem").write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    for path in directory.iterdir():
        path.chmod(0o600)
    progress("local_keys_ready")


def migrate(check=False):
    guard()
    from alembic import command
    from alembic.config import Config
    config = Config("/source/alembic.ini")
    config.set_main_option("script_location", "/source/alembic")
    config.set_main_option("prepend_sys_path", "/source")
    command.upgrade(config, "head")
    if check:
        command.check(config)
    progress("migration_complete", check=check)


class API:
    def __init__(self, state):
        self.state = state

    async def request(self, role, method, path, expected=200, raw=False, **kwargs):
        import httpx
        actor = self.state["users"].get(role)
        cookies = {"accessToken": actor["access_token"], "csrfToken": actor["csrf"]} if actor else {}
        headers = {"Origin": BASE_URL}
        if actor:
            headers["X-CSRF-Token"] = actor["csrf"]
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(base_url="http://backend:3002", trust_env=False, cookies=cookies, headers=headers, timeout=60) as client:
            response = await client.request(method, path, **kwargs)
        allowed = (expected,) if isinstance(expected, int) else expected
        require(response.status_code in allowed, f"{role} {method} {path}: HTTP {response.status_code}; {response.text[:1200]}")
        return response if raw else (response.json() if response.content else None)


async def seed():
    settings = guard()
    import aioboto3
    from sqlalchemy import update
    from domain.storefronts import DEFAULT_STOREFRONT_ID
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingApplication
    from infrastructure.models.companies import Company, DistributorBrand, DistributorDealerLink, LeasingCompany, LeasingCompanyUser
    from infrastructure.models.special_equipment import SpecialEquipmentMark, SpecialEquipmentModel, SpecialEquipmentModification, SpecialEquipmentProduct
    from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
    from infrastructure.models.support import DealerGroup, DealerGroupMember
    from infrastructure.models.users import User, UserCompany, UserSession
    from infrastructure.models.vehicles import Warehouse, WarehouseMark
    load_and_validate_key_configuration()
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key) as s3:
        buckets = await s3.list_buckets()
        if not any(b["Name"] == settings.s3_bucket for b in buckets["Buckets"]):
            await s3.create_bucket(Bucket=settings.s3_bucket)
    state_path = ROOT / "state.secret.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        require(state["marker"] == MARKER, "Refusing unrelated fixture")
    else:
        state = {"marker": MARKER, "users": {}, "companies": {}, "products": {}, "applications": {}}
        async with AsyncSessionLocal() as session:
            require(await session.get(Company, identifier("company/dealer")) is None, "Partial fixture requires investigation")
            companies = {}
            for index, (alias, role) in enumerate([("leasing", "leasing_company"), ("dealer", "dealer"), ("outsider", "dealer"), ("distributor", "distributor"), ("client", "other"), ("foreign_client", "other")], 1):
                company = Company(id=identifier("company/" + alias), name="22320 " + alias, inn=f"000022320{index}", company_type=role, is_active=True, legal_address="Москва, тестовая улица, дом 1")
                session.add(company)
                companies[alias] = company
                state["companies"][alias] = {"company_id": str(company.id), "name": company.name}
            await session.flush()
            lc = LeasingCompany(id=identifier("lc/leasing"), company_id=companies["leasing"].id, is_active=True)
            session.add(lc)
            state["companies"]["leasing"]["leasing_company_id"] = str(lc.id)
            session.add(DistributorDealerLink(distributor_company_id=companies["distributor"].id, dealer_company_id=companies["dealer"].id))
            mark = SpecialEquipmentMark(id=identifier("mark"), code="e2e22320", name="22320 Марка", slug="e2e22320", is_active=True)
            session.add(mark)
            await session.flush()
            model = SpecialEquipmentModel(id=identifier("model"), mark_id=mark.id, code="e2e22320-model", name="22320 Модель", slug="e2e22320-model", is_active=True)
            session.add(model)
            await session.flush()
            modification = SpecialEquipmentModification(id=identifier("modification"), model_id=model.id, code="e2e22320-modification", name="22320 Комплектация", slug="e2e22320-modification", is_active=True)
            session.add(modification)
            await session.flush()
            state["catalog"] = {"mark_id": str(mark.id), "model_id": str(model.id), "modification_id": str(modification.id), "brand": mark.name, "model": model.name}
            if await session.get(Storefront, DEFAULT_STOREFRONT_ID) is None:
                session.add(Storefront(id=DEFAULT_STOREFRONT_ID, is_default=True, is_active=True, version=1))
            await session.flush()
            for alias in ("dealer", "distributor", "outsider"):
                warehouse = Warehouse(id=identifier("warehouse/" + alias), name="22320 " + alias, owner_company_id=companies[alias].id, owner_company_type="distributor" if alias == "distributor" else "dealer", address="Москва, склад 22320", is_active=True)
                session.add(warehouse)
                await session.flush()
                session.add(WarehouseMark(warehouse_id=warehouse.id, mark_id=mark.id))
                session.add(StorefrontWarehouse(storefront_id=DEFAULT_STOREFRONT_ID, warehouse_id=warehouse.id))
                for index in range(40):
                    key = f"{alias}/{index}"
                    product_id = identifier("product/" + key)
                    product = SpecialEquipmentProduct(id=product_id, code="E2E22320-" + key.replace("/", "-"), modification_id=modification.id, seller_company_id=companies["dealer" if alias == "distributor" else alias].id, warehouse_id=warehouse.id,
                        slug="e2e22320-" + key.replace("/", "-"), price=Decimal("1000000"), condition="new", no_vin=False, vin="E22320" + product_id.hex[:11].upper(), manufacture_year=2026, publication_status="published", sale_status="available", published_at=datetime.now(UTC))
                    session.add(product)
                    state["products"][key] = str(product_id)
            product = SpecialEquipmentProduct(id=identifier("product/no-warehouse"), code="E2E22320-NO-WH", modification_id=modification.id, seller_company_id=companies["dealer"].id, warehouse_id=None,
                slug="e2e22320-no-warehouse", price=Decimal("1000000"), condition="new", no_vin=True, manufacture_year=2026, publication_status="published", sale_status="available", published_at=datetime.now(UTC))
            session.add(product)
            state["products"]["no-warehouse"] = str(product.id)
            for index, (alias, role, company_alias) in enumerate([("admin", "carcraft_employee", None), ("dealer", "dealer", "dealer"), ("outsider", "dealer", "outsider"), ("leasing", "leasing_company", "leasing"), ("distributor", "distributor", "distributor"), ("client", "client", "client"), ("foreign_client", "client", "foreign_client")], 1):
                company_id = companies[company_alias].id if company_alias else None
                user = User(id=identifier("user/" + alias), name="22320 " + alias, phone=f"+700022320{index:02}", email=alias+"@task22320.test", role=role, company_id=company_id, is_active=True, phone_verified=True, email_verified=True)
                session.add(user)
                await session.flush()
                if company_id:
                    session.add(UserCompany(user_id=user.id, company_id=company_id, sub_role="administrator", can_view_applications=True, can_create_applications=True))
                if alias == "leasing":
                    session.add(LeasingCompanyUser(id=identifier("lc-user"), user_id=user.id, leasing_company_id=lc.id))
                state["users"][alias] = {"id": str(user.id), "role": role, "company_id": str(company_id) if company_id else None}
            for index, source in enumerate((None, "dealer_account"), 1):
                key = "legacy-null" if source is None else "legacy-dealer-account"
                app = LeasingApplication(id=identifier(key), company_id=companies["client"].id, dealer_company_id=companies["dealer"].id, created_by=identifier("user/client"), source_type=source, storefront_id=DEFAULT_STOREFRONT_ID, name="22320 "+key, display_number=f"23-0320{index}", status="active", total_amount=Decimal("1000000"))
                session.add(app)
                state["applications"][key] = {"id": str(app.id), "source_type": source, "display_number": app.display_number}
            await session.commit()
    async with AsyncSessionLocal() as session:
        if await session.get(DealerGroup, identifier("dealer-group")) is None:
            session.add(DealerGroup(id=identifier("dealer-group"), distributor_company_id=identifier("company/distributor"), name="22320 group", created_by=identifier("user/admin"), is_active=True))
            await session.flush()
            session.add(DealerGroupMember(id=identifier("dealer-group-member"), dealer_group_id=identifier("dealer-group"), dealer_company_id=identifier("company/dealer"), created_by=identifier("user/admin")))
            session.add(DistributorBrand(id=identifier("distributor-brand"), distributor_company_id=identifier("company/distributor"), brand_id=identifier("mark"), is_active=True))
        await session.commit()
    async with AsyncSessionLocal() as session:
        storefront_id = identifier("storefront")
        if await session.get(Storefront, storefront_id) is None:
            session.add(Storefront(id=storefront_id, slug="e2e22320", is_default=False, is_active=True, version=1))
            await session.flush()
            session.add(StorefrontWarehouse(storefront_id=storefront_id, warehouse_id=identifier("warehouse/distributor")))
        await session.commit()
    # Separate actual stock matching groups: source follows the product allocated
    # into the application, so dealer/distributor inventory must not substitute.
    async with AsyncSessionLocal() as session:
        for alias in ("dealer", "distributor", "outsider"):
            mod_id = identifier("modification/" + alias)
            if await session.get(SpecialEquipmentModification, mod_id) is None:
                session.add(SpecialEquipmentModification(id=mod_id, model_id=identifier("model"), code="e2e22320-mod-"+alias, name="22320 "+alias, slug="e2e22320-mod-"+alias, is_active=True))
                await session.flush()
            product_ids = [UUID(value) for key, value in state["products"].items() if key.startswith(alias+"/")]
            await session.execute(update(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id.in_(product_ids)).values(modification_id=mod_id))
        await session.commit()
    async with AsyncSessionLocal() as session:
        for actor in state["users"].values():
            user = await session.get(User, UUID(actor["id"]))
            require(user is not None and user.is_active, "Fixture user missing")
            sid = uuid4()
            access, refresh = generate_tokens(user.id, user.role, user.company_id, refresh_session_id=sid)
            session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh), expires_at=datetime.now(UTC)+timedelta(days=1), ip_address="127.0.0.1", user_agent=MARKER))
            actor.update(access_token=access, refresh_token=refresh, csrf=secrets.token_urlsafe(24))
        await session.commit()
    private_json(state_path, state)
    storages = {}
    for alias, actor in state["users"].items():
        cookies = [{"name": key, "value": value, "domain": "localhost", "path": "/", "expires": time.time()+86400, "httpOnly": http, "secure": False, "sameSite": "Lax"} for key, value, http in [("accessToken", actor["access_token"], True), ("refreshToken", actor["refresh_token"], True), ("csrfToken", actor["csrf"], False)]]
        filename = alias + ".storage.json"
        private_json(ROOT / filename, {"cookies": cookies, "origins": []})
        storages[alias] = str(HOST_ROOT / filename)
    manifest = {"marker": MARKER, "base_url": BASE_URL, "storage_states": storages, "companies": state["companies"], "catalog": state["catalog"], "products": state["products"], "applications": state["applications"], "storefront_slug": "e2e22320", "user_ids": {role: actor["id"] for role, actor in state["users"].items()}}
    private_json(ROOT / "manifest.json", manifest)
    progress("fixture_ready")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["keys", "migrate", "check", "seed", "verify"])
    args = parser.parse_args()
    if args.action == "keys":
        keys()
    elif args.action in {"migrate", "check"}:
        migrate(check=args.action == "check")
    elif args.action == "seed":
        asyncio.run(seed())
    else:
        from acceptance import verify
        asyncio.run(verify())
