"""Seed isolated, real employee-list fixtures; never touches production data."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

if len(Path(__file__).resolve().parents) > 3:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from sqlalchemy.engine import make_url

from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.database import AsyncSessionLocal
from infrastructure.models.companies import Company, DistributorBrand
from infrastructure.models.special_equipment import SpecialEquipmentMark
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.user_company_access import (
    UserCompanyAccessRule,
    UserCompanySectionAccess,
)
from infrastructure.models.users import User, UserCompany, UserSession
from infrastructure.models.vehicles import City, Warehouse, WarehouseAccessRule
from infrastructure.settings import settings

MARKER = "E2E22398"


def ident(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, "carcraft/22398/" + key)


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)


async def main() -> None:  # noqa: PLR0912, PLR0915 — explicit isolated fixture graph
    database = make_url(settings.database_dsn)
    if not database.database or not any(
        x in database.database.lower() for x in ("e2e", "22398")
    ):
        raise RuntimeError("22398 fixture requires an isolated E2E database")
    output = Path(os.environ["E2E_22398_ARTIFACT_DIR"])
    base_url = os.environ.get("E2E_BASE_URL", "http://localhost:18398")
    host = urlparse(base_url).hostname
    if host not in {"localhost", "127.0.0.1", "nginx"}:
        raise RuntimeError("Fixture cookies require a local E2E origin")
    companies = {
        key: str(ident("company/" + key))
        for key in (
            "dealer",
            "distributor",
            "second",
            "outsider",
            "client",
            "leasing_company",
        )
    }
    brands = {key: str(ident("brand/" + key)) for key in ("a", "b", "foreign")}
    warehouses = {
        key: str(ident("warehouse/" + key))
        for key in (
            "dealer-a",
            "dealer-b",
            "distributor-a",
            "distributor-b",
            "outsider-a",
        )
    }
    actors = {}
    users = {}
    async with AsyncSessionLocal() as session:
        for index, key in enumerate(companies):
            role = (
                key if key in {"distributor", "client", "leasing_company"} else "dealer"
            )
            await session.merge(
                Company(
                    id=ident("company/" + key),
                    name=f"{MARKER} {key}",
                    inn=f"223980000{index:01}",
                    company_type="other" if role == "client" else role,
                )
            )
        for key in brands:
            await session.merge(
                SpecialEquipmentMark(
                    id=ident("brand/" + key),
                    name=f"{MARKER} Brand {key}",
                    code=f"e2e22398-{key}",
                    slug=f"e2e22398-{key}",
                    is_active=True,
                )
            )
        await session.merge(City(id=ident("city"), name="Москва E2E22398"))
        await session.flush()
        for key in warehouses:
            company = key.split("-")[0]
            brand = "foreign" if company == "outsider" else key.split("-")[1]
            await session.merge(
                Warehouse(
                    id=ident("warehouse/" + key),
                    name=f"{MARKER} {key}",
                    address=f"{MARKER} address {key}",
                    city_id=ident("city") if key.endswith("-a") else None,
                    owner_company_id=ident("company/" + company),
                    owner_company_type="distributor"
                    if company == "distributor"
                    else "dealer",
                    brand_id=ident("brand/" + brand),
                    is_active=True,
                )
            )
        for key in ("a", "b"):
            await session.merge(
                DistributorBrand(
                    id=ident("distributor-brand/" + key),
                    distributor_company_id=ident("company/distributor"),
                    brand_id=ident("brand/" + key),
                    is_active=True,
                )
            )
        definitions = [
            ("admin", "carcraft_employee", None),
            ("dealer", "dealer", "dealer"),
            ("distributor", "distributor", "distributor"),
            ("outsider", "dealer", "outsider"),
            ("blocked", "dealer", "dealer"),
        ]
        definitions += [
            (mode, "dealer", "dealer")
            for mode in (
                "default",
                "all",
                "selected",
                "except_selected",
                "none",
                "inactive",
                "multi",
            )
        ]
        definitions += [(f"page{index:02}", "dealer", "dealer") for index in range(22)]
        definitions += [
            ("client", "client", "client"),
            ("leasing", "leasing_company", "leasing_company"),
            ("kk_company", "carcraft_employee", "client"),
            ("mutation", "dealer", "dealer"),
            ("kk_dealer", "carcraft_employee", "second"),
        ]
        for index, (alias, role, company) in enumerate(definitions, 1):
            user = await session.merge(
                User(
                    id=ident("user/" + alias),
                    name=f"{MARKER} {alias}",
                    phone=f"+700022398{index:02}",
                    role=role,
                    company_id=ident("company/" + company) if company else None,
                    is_active=True,
                    phone_verified=True,
                )
            )
            await session.flush()
            users[alias] = {"id": str(user.id), "name": user.name, "phone": user.phone}
            if company:
                await session.merge(
                    UserCompany(
                        id=ident("uc/" + alias),
                        user_id=user.id,
                        company_id=ident("company/" + company),
                        role=(
                            "client"
                            if alias == "kk_company"
                            else "dealer"
                            if alias == "kk_dealer"
                            else role
                        ),
                        sub_role="administrator"
                        if alias in {"dealer", "distributor", "outsider"}
                        else ("manager" if alias == "default" else "employee"),
                        is_active=alias != "inactive",
                        can_view_applications=True,
                        can_create_applications=True,
                    )
                )
                users[alias]["user_company_id"] = str(ident("uc/" + alias))
            if alias in {
                "admin",
                "dealer",
                "distributor",
                "outsider",
                "blocked",
                "default",
            }:
                sid = uuid4()
                access, refresh = generate_tokens(
                    user.id, role, user.company_id, refresh_session_id=sid
                )
                session.add(
                    UserSession(
                        id=sid,
                        user_id=user.id,
                        refresh_token_hash=hash_refresh_token(refresh),
                        expires_at=datetime.now(UTC) + timedelta(days=1),
                        user_agent=MARKER,
                    )
                )
                actors[alias] = {
                    "cookies": [
                        {
                            "name": key,
                            "value": value,
                            "domain": host,
                            "path": "/",
                            "expires": time.time() + 86400,
                            "httpOnly": http_only,
                            "secure": False,
                            "sameSite": "Lax",
                        }
                        for key, value, http_only in (
                            ("accessToken", access, True),
                            ("refreshToken", refresh, True),
                            ("csrfToken", "e2e22398-local", False),
                        )
                    ],
                    "origins": [],
                }
        await session.flush()
        await session.merge(
            UserCompany(
                id=ident("uc/multi-second"),
                user_id=ident("user/multi"),
                company_id=ident("company/second"),
                role="client",
                is_active=True,
            )
        )
        await session.merge(
            UserCompanySectionAccess(
                id=ident("section/blocked"),
                user_company_id=ident("uc/blocked"),
                section_code="employees",
                can_view=False,
            )
        )
        for mode in ("all", "selected", "except_selected", "none"):
            for obj, selected in (
                ("brand", "brand/a"),
                ("warehouse", "warehouse/dealer-a"),
            ):
                await session.merge(
                    UserCompanyAccessRule(
                        id=ident(f"rule/{mode}/{obj}"),
                        user_company_id=ident("uc/" + mode),
                        access_object=obj,
                        access_type=mode,
                        object_id=str(ident(selected))
                        if mode in {"selected", "except_selected"}
                        else None,
                        object_name="Stale name must not be displayed",
                        is_active=True,
                    )
                )
        # selected must not grant a brand or warehouse outside the company baseline.
        for obj, selected in (
            ("brand", "brand/foreign"),
            ("warehouse", "warehouse/outsider-a"),
        ):
            await session.merge(
                UserCompanyAccessRule(
                    id=ident(f"rule/selected/foreign/{obj}"),
                    user_company_id=ident("uc/selected"),
                    access_object=obj,
                    access_type="selected",
                    object_id=str(ident(selected)),
                    object_name="Foreign forbidden",
                    is_active=True,
                )
            )
        await session.merge(
            WarehouseAccessRule(
                id=ident("invisible-grant"),
                warehouse_id=ident("warehouse/outsider-a"),
                target_type="dealer",
                target_id=ident("company/dealer"),
                warehouse_access_type="A",
                brand_id=ident("brand/foreign"),
                is_visible=False,
                is_active=True,
            )
        )
        for key in ("one", "two"):
            await session.merge(
                DealerGroup(
                    id=ident("group/" + key),
                    distributor_company_id=ident("company/distributor"),
                    name=f"{MARKER} {key}",
                    created_by=ident("user/admin"),
                    is_active=True,
                )
            )
            await session.flush()
            await session.merge(
                DealerGroupMember(
                    id=ident("member/" + key),
                    dealer_group_id=ident("group/" + key),
                    dealer_company_id=ident("company/dealer"),
                    created_by=ident("user/admin"),
                )
            )
        await session.commit()
    for alias, state in actors.items():
        save(output / f"{alias}.storage.json", state)
    save(
        output / "manifest.json",
        {
            "marker": MARKER,
            "base_url": base_url,
            "companies": companies,
            "brands": brands,
            "warehouses": warehouses,
            "users": users,
        },
    )
    sys.stdout.write("22398 fixture ready\n")


if __name__ == "__main__":
    asyncio.run(main())
