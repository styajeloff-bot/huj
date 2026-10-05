#!/usr/bin/env python3
"""Task 22242 acceptance against the isolated, migrated PostgreSQL and HTTP API.

Inside the backend image (mount this script and /tmp/carcraft-22242-runtime at
/runtime), run: python /path/to/runtime.py seed|verify|auth|bootstrap --execute
Use --backend-path /app when backend imports are rooted at /app (the default).
No Docker, migrations, production users, OTP, or unit-test doubles are involved.
Seed once; verify consumes ONLY API fixtures and is intentionally not replayable.
The operations themselves are repeated to verify idempotency. Browser fixtures
are separate through http://carcraft-22242.localhost:18243/login/{role}.
The bootstrap container's 3003 must be published ONLY at 127.0.0.1:18243.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

MARKER = "task22242-runtime"
NAMESPACE = uuid5(NAMESPACE_URL, "https://task22242.test/runtime")
PUBLIC_URL = "http://carcraft-22242.localhost:18242"
API_URL = "http://backend:3002"
STATE_PATH = Path("/runtime/fixtures.secret.json")
ADMIN = "carcraft_employee"
ROLES = (ADMIN, "dealer", "distributor", "leasing_company", "client")
BLOCKERS = (
    "leasing_applications", "application_vehicles", "purchase_orders",
    "exchange_requests", "shopping_cart", "user_favorites", "exchange_cart_items",
    "compensations", "application_applied_supports",
    "leasing_application_vehicle_calculations", "calculation_history", "guest_cart_transfers",
)
PRICE = 2500000


class AcceptanceFailure(RuntimeError):
    """Only messages explicitly constructed here are safe to print."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def check(message: str) -> None:
    print(f"PASS {message}", flush=True)


def identifier(name: str) -> UUID:
    return uuid5(NAMESPACE, name)


def guard(args: argparse.Namespace):
    require(args.execute, "Use --execute only in the isolated carcraft-22242 project")
    require(Path("/runtime").is_dir() and Path("/runtime").resolve() == Path("/runtime"),
            "Expected the dedicated /runtime bind mount")
    sys.path.insert(0, args.backend_path)
    from sqlalchemy.engine import make_url

    from infrastructure.settings import settings

    dsn = make_url(settings.database_dsn)
    require(dsn.get_backend_name() == "postgresql", "Real PostgreSQL is required")
    require(dsn.host == "postgres" and dsn.database == "notifications35_runtime"
            and dsn.username == "notifications35", "Wrong isolated DB host/name/user")
    require(settings.public_url == PUBLIC_URL, "PUBLIC_URL must equal http://carcraft-22242.localhost:18242")
    require(str(settings.jwt_keys_dir) == "/runtime-keys/jwt", "Wrong JWT_KEYS_DIR")
    # Secondary services may be called by the real API after commit.
    require(bool(settings.s3_endpoint and settings.s3_bucket),
            "Object storage must be configured")
    return settings


def save_state(state: dict, *, create: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    flags |= os.O_EXCL if create else os.O_TRUNC
    fd = os.open(STATE_PATH, flags, 0o600)
    with os.fdopen(fd, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(state, output, ensure_ascii=False, indent=2)
        output.write("\n")


def load_state() -> dict:
    fd = os.open(STATE_PATH, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        require(os.fstat(source.fileno()).st_mode & 0o077 == 0, "Fixture secret must have mode 0600")
        state = json.load(source)
    require(state.get("marker") == MARKER and state.get("ready") is True, "Incomplete/wrong fixture state")
    require(set(state["users"]) == set(ROLES), "Unexpected fixture roles")
    for role in ROLES:
        require(state["users"][role]["id"] == str(identifier(f"user/{role}")), "Unexpected fixture user")
    for name, warehouse in state["warehouses"].items():
        require(warehouse["id"] == str(identifier(f"warehouse/{name}")), "Unexpected fixture warehouse")
    for name, vehicle in state["vehicles"].items():
        require(vehicle["id"] == str(identifier(f"vehicle/{name}")), "Unexpected fixture vehicle")
    return state


async def insert(session, model, **values) -> None:
    """Core INSERT preserves ORM defaults without ordering unrelated pending ORM rows."""
    await session.execute(model.__table__.insert().values(**values))


async def issue_auth(session, state: dict, settings) -> None:
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.models.users import User, UserSession

    now = datetime.now(UTC)
    for role in ROLES:
        user = await session.get(User, identifier(f"user/{role}"))
        require(user is not None and user.role == role and user.is_active and not user.deleted_at,
                f"Fixture user changed: {role}")
        session_id = identifier(f"session/{role}/{now.isoformat()}")
        access, refresh = generate_tokens(user.id, role, user.company_id, refresh_session_id=session_id)
        expiry = now + timedelta(days=settings.refresh_token_expiry_days)
        await insert(session, UserSession, id=session_id, user_id=user.id,
                     refresh_token_hash=hash_refresh_token(refresh), expires_at=expiry,
                     ip_address="127.0.0.1", user_agent=MARKER)
        state["users"][role] = {
            "id": str(user.id), "access_token": access, "refresh_token": refresh,
            "access_token_expires": (now + timedelta(minutes=settings.access_token_expiry_minutes)).timestamp(),
            "refresh_token_expires": expiry.timestamp(),
        }


async def add_blocker(session, kind: str, name: str, *, suffix: str = "") -> None:
    """Each target gets exactly one selected blocker; prerequisite rows have no target vehicle."""
    from infrastructure.models import applications as a
    from infrastructure.models.cart_transfers import GuestCartTransfer
    from infrastructure.models.compensations import CompensationModel
    from infrastructure.models.exchange import ExchangeCartItem, ExchangeRequest
    from infrastructure.models.payments import PurchaseOrder
    from infrastructure.models.support import ApplicationAppliedSupport
    from infrastructure.models.users import UserFavorite

    vehicle_id = identifier(f"vehicle/{name}")
    row_id = identifier(f"blocker/{kind}/{name}/{suffix}")
    client_id = identifier("user/client")
    if kind in {"leasing_applications", "application_vehicles", "application_applied_supports",
                "leasing_application_vehicle_calculations", "compensations"}:
        app_id = identifier(f"application/{kind}/{name}/{suffix}")
        await insert(session, a.LeasingApplication, id=app_id, company_id=identifier("company/client"),
                     dealer_company_id=identifier("company/dealer"), created_by=client_id,
                     name=f"22242 {kind}", display_number=f"22242-{app_id.hex[:12]}", status="active",
                     vehicle_id=vehicle_id if kind == "leasing_applications" else None, total_amount=PRICE)
        if kind == "leasing_applications":
            return
        if kind == "application_vehicles":
            await insert(session, a.ApplicationVehicle, id=row_id, application_id=app_id,
                         vehicle_id=vehicle_id, dealer_company_id=identifier("company/dealer"),
                         quantity=1, unit_price=PRICE, total_price=PRICE)
        elif kind == "leasing_application_vehicle_calculations":
            await insert(session, a.LeasingApplicationVehicleCalculation, id=row_id,
                         leasing_application_id=app_id, vehicle_id=vehicle_id,
                         quantity=1, unit_price=PRICE, total_amount=PRICE)
        else:
            support_id = identifier(f"support/{kind}/{name}/{suffix}")
            await insert(session, ApplicationAppliedSupport, id=support_id, application_id=app_id,
                         vehicle_id=vehicle_id if kind == "application_applied_supports" else None,
                         name="22242 acceptance support", support_type="down_payment_compensation")
            if kind == "compensations":
                await insert(session, CompensationModel, id=row_id, applied_support_id=support_id,
                             application_id=app_id, source="platform", vehicle_id=vehicle_id,
                             payer="dealer", recipient="client", calculation_base="base_price",
                             value_type="sum", value=1000, amount=1000)
        return
    common = {"id": row_id, "vehicle_id": vehicle_id}
    if kind == "purchase_orders":
        await insert(session, PurchaseOrder, **common, user_id=client_id, purchase_type="reservation",
                     status="cancelled", total_price=PRICE, cancelled_at=datetime.now(UTC),
                     cancellation_reason="22242: cancelled orders still block deletion")
    elif kind == "exchange_requests":
        await insert(session, ExchangeRequest, **common, lc_user_id=identifier("user/leasing_company"),
                     lc_company_id=identifier("company/leasing_company"), status="open")
    elif kind == "shopping_cart":
        await insert(session, a.ShoppingCart, **common, user_id=client_id, quantity=1)
    elif kind == "user_favorites":
        await insert(session, UserFavorite, **common, user_id=client_id)
    elif kind == "exchange_cart_items":
        await insert(session, ExchangeCartItem, **common, user_id=identifier("user/leasing_company"))
    elif kind == "calculation_history":
        await insert(session, a.CalculationHistory, id=row_id, user_id=client_id,
                     vehicle_ids=[vehicle_id], total_amount=PRICE, calculation_type=MARKER)
    elif kind == "guest_cart_transfers":
        await insert(session, GuestCartTransfer, user_id=client_id, transfer_id=row_id,
                     vehicle_id=vehicle_id, quantity=1)
    else:
        raise AcceptanceFailure(f"Unknown blocker: {kind}")


async def seed(settings) -> None:
    from domain.storefronts import DEFAULT_STOREFRONT_ID
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.catalog import CarModel, Mark, VehicleCategory
    from infrastructure.models.companies import Company, DistributorDealerLink, LeasingCompany, LeasingCompanyUser
    from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
    from infrastructure.models.users import User, UserCompany
    from infrastructure.models.vehicles import Vehicle, VehicleWarehouse, VehicleWarehouseTransfer, Warehouse

    state = {"marker": MARKER, "ready": False, "users": {}, "warehouses": {}, "vehicles": {}}
    # Reserve before touching DB: concurrent seed/reseed fails closed. A failed
    # seed keeps this non-ready receipt and must be investigated, not overwritten.
    save_state(state, create=True)
    async with AsyncSessionLocal() as session, session.begin():
        if await session.get(Storefront, DEFAULT_STOREFRONT_ID) is None:
            await insert(session, Storefront, id=DEFAULT_STOREFRONT_ID, is_default=True, is_active=True, version=1)
        for role in ROLES:
            company_id = None if role == ADMIN else identifier(f"company/{role}")
            if company_id:
                await insert(session, Company, id=company_id, name=f"22242 runtime {role}",
                             company_type="other" if role == "client" else role, is_active=True)
            await insert(session, User, id=identifier(f"user/{role}"), role=role,
                         name=f"22242 runtime {role}", phone=f"+7002224200{ROLES.index(role)}",
                         email=f"{role}@task22242.test", company_id=company_id,
                         is_active=True, email_verified=True, phone_verified=True)
            if company_id:
                await insert(session, UserCompany, user_id=identifier(f"user/{role}"), company_id=company_id,
                             sub_role="administrator", can_view_applications=True, can_create_applications=True)
        await insert(session, LeasingCompany, id=identifier("leasing-company"),
                     company_id=identifier("company/leasing_company"), is_active=True)
        await insert(session, LeasingCompanyUser, id=identifier("leasing-company-user"),
                     user_id=identifier("user/leasing_company"),
                     leasing_company_id=identifier("leasing-company"))
        await insert(session, DistributorDealerLink, distributor_company_id=identifier("company/distributor"),
                     dealer_company_id=identifier("company/dealer"))
        category = "22242 acceptance cars"
        await insert(session, VehicleCategory, id=category)
        await insert(session, Mark, id=str(identifier("mark")), name="22242 Acceptance", country="Россия")
        await insert(session, CarModel, id=str(identifier("model")), mark_id=str(identifier("mark")),
                     name="Runtime sedan", category=category, year_from=2026)
        for group in ("browser", "api"):
            scenarios = {
                "single": ["free", "history", "favorites", "no-vin"],
                "bulk": ["free", "history", "favorites", "multi", "late"],
                "unbind": [f"car-{index:03}" for index in range(45 if group == "browser" else 205)],
                "other": ["untouched"],
            }
            if group == "api":
                scenarios.update(blockers=list(BLOCKERS) + ["multi"],
                                 late=["favorite", "history-array", "guest"], rollback=["first", "second"],
                                 concurrent=["cart-writer-first", "cart-delete-first",
                                             "array-writer-first", "array-delete-first"])
            for scenario, names in scenarios.items():
                key = f"{group}/{scenario}"
                warehouse_id = identifier(f"warehouse/{key}")
                state["warehouses"][key] = {"id": str(warehouse_id), "vehicles": []}
                await insert(session, Warehouse, id=warehouse_id, brand="22242 Acceptance",
                             address=f"22242 {group} / {scenario}", status="active",
                             dealer_id=identifier("company/dealer"), company_id=identifier("company/dealer"))
                await insert(session, StorefrontWarehouse, storefront_id=DEFAULT_STOREFRONT_ID,
                             warehouse_id=warehouse_id)
                for item in names:
                    name = f"{key}/{item}"
                    vehicle_id = identifier(f"vehicle/{name}")
                    vin = None if item == "no-vin" else f"T22242{vehicle_id.hex[:11].upper()}"
                    state["vehicles"][name] = {"id": str(vehicle_id), "vin": vin or "", "warehouse": key}
                    state["warehouses"][key]["vehicles"].append(name)
                    await insert(session, Vehicle, id=vehicle_id, vin=vin,
                                 dealer_id=identifier("company/dealer"), mark_id=str(identifier("mark")),
                                 model_id=str(identifier("model")), year=2026, base_price=PRICE,
                                 color="Белый" if item != "free" else "Синий", status="available", is_available=True,
                                 images=[f"vehicles/task22242-{vehicle_id}.png"] if scenario == "rollback" else None)
                    await insert(session, VehicleWarehouse, id=identifier(f"binding/{name}"),
                                 vehicle_id=vehicle_id, warehouse_id=warehouse_id)
        for name in state["vehicles"]:
            group, scenario, item = name.split("/")
            if item == "history" or (scenario == "unbind" and item == "car-000") or scenario == "rollback":
                await insert(session, VehicleWarehouseTransfer, id=identifier(f"transfer/{name}"),
                             vehicle_id=identifier(f"vehicle/{name}"),
                             source_warehouse_id=identifier(f"warehouse/{group}/other"),
                             destination_warehouse_id=identifier(f"warehouse/{group}/{scenario}"),
                             actor_user_id=identifier(f"user/{ADMIN}"))
            if scenario == "blockers" and item != "multi":
                await add_blocker(session, item, name)
            if item in {"favorites", "multi"} or (scenario == "unbind" and item == "car-000"):
                await add_blocker(session, "user_favorites", name)
            if item == "multi":
                await add_blocker(session, "shopping_cart", name)
                await add_blocker(session, "calculation_history", name)
                await add_blocker(session, "calculation_history", name, suffix="second")
        await issue_auth(session, state, settings)
    state["ready"] = True
    save_state(state)
    check(f"seed: {len(ROLES)} users, {len(state['warehouses'])} warehouses, {len(state['vehicles'])} vehicles")
    for key, warehouse in state["warehouses"].items():
        if key.startswith("browser/"):
            print(f"BROWSER {key}: {warehouse['id']} ({len(warehouse['vehicles'])} cars)", flush=True)


async def renew(settings) -> None:
    from infrastructure.database import AsyncSessionLocal

    state = load_state()
    async with AsyncSessionLocal() as session, session.begin():
        await issue_auth(session, state, settings)
    save_state(state)
    check("auth renewed for all five fixtures; tokens only in /runtime/fixtures.secret.json")


def bootstrap() -> None:
    load_state()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_values: object) -> None:
            pass

        def do_GET(self) -> None:
            # Host-only cookies are deliberately set from the task hostname, never a
            # configurable host/domain. No proxy, static-file, or token endpoint.
            if self.headers.get("Host") != "carcraft-22242.localhost:18243":
                self.send_error(403)
                return
            match = re.fullmatch(r"/login/([a-z_]+)", self.path)
            if not match or match[1] not in ROLES:
                self.send_error(404)
                return
            try:
                user = load_state()["users"][match[1]]
                require(user["access_token_expires"] > time.time(), "Expired fixture auth; run auth --execute")
            except Exception:
                self.send_error(409, "Fixture authentication unavailable; run auth --execute")
                return
            self.send_response(303)
            self.send_header("Location", PUBLIC_URL + "/workspace/warehouses")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", "0")
            for name, key in (("accessToken", "access_token"), ("refreshToken", "refresh_token")):
                cookie = SimpleCookie()
                cookie[name] = user[key]
                cookie[name]["path"] = "/"
                cookie[name]["httponly"] = True
                cookie[name]["samesite"] = "Lax"
                cookie[name]["max-age"] = int(user[f"{key}_expires"] - time.time())
                self.send_header("Set-Cookie", cookie[name].OutputString())
            self.end_headers()

    print("BOOTSTRAP 0.0.0.0:3003; publish 127.0.0.1:18243; /login/" + " | /login/".join(ROLES), flush=True)
    ThreadingHTTPServer(("0.0.0.0", 3003), Handler).serve_forever()


async def snapshot(state: dict, names: list[str]) -> dict:
    """Full business rows, not just counts; exclude mutable worker scheduling fields."""
    from sqlalchemy import column, func, select, table as sql_table, text

    from infrastructure.database import AsyncSessionLocal

    ids = [UUID(state["vehicles"][name]["id"]) for name in names]
    warehouse_ids = list({UUID(state["warehouses"][state["vehicles"][name]["warehouse"]]["id"]) for name in names})
    filters = dict.fromkeys(BLOCKERS, "vehicle_id = ANY(CAST(:ids AS uuid[]))")
    filters.update(vehicles="id = ANY(CAST(:ids AS uuid[]))",
                   vehicle_warehouses="vehicle_id = ANY(CAST(:ids AS uuid[]))",
                   vehicle_warehouse_transfers="vehicle_id = ANY(CAST(:ids AS uuid[]))",
                   warehouses="id = ANY(CAST(:warehouses AS uuid[]))",
                   calculation_history="vehicle_ids && CAST(:ids AS uuid[])")
    result = {}
    async with AsyncSessionLocal() as session:
        for table, predicate in filters.items():
            relation = sql_table(table).alias("t")
            query = select(func.to_jsonb(relation.table_valued())).where(text(predicate))
            rows = (await session.execute(query,
                                          {"ids": ids, "warehouses": warehouse_ids})).scalars().all()
            result[table] = sorted(json.dumps(row, sort_keys=True, default=str) for row in rows)
        for table, key in (("mark", "mark"), ("model", "model")):
            relation = sql_table(table).alias("t")
            query = select(func.to_jsonb(relation.table_valued())).where(column("id") == str(identifier(key)))
            rows = (await session.execute(query)).scalars().all()
            result[table] = sorted(json.dumps(row, sort_keys=True) for row in rows)
        for table, key, fields in (
            ("object_storage_deletion_jobs", "entity_id", "id, entity_type, entity_id, object_key"),
            ("vehicle_deletion_outbox", "vehicle_id", "id, vehicle_id, payload"),
        ):
            relation = sql_table(table)
            subset = (select(*(column(field.strip()) for field in fields.split(",")))
                      .select_from(relation).where(column(key).in_(ids)).subquery("t"))
            rows = (await session.execute(select(func.to_jsonb(subset.table_valued())))).scalars().all()
            result[table] = sorted(json.dumps(row, sort_keys=True) for row in rows)
    return result


class API:
    def __init__(self, client, state: dict):
        self.client = client
        self.state = state

    def vehicle(self, name: str) -> str:
        require(name.startswith("api/"), "Refusing browser vehicle mutation")
        return "/api/v1/admin/vehicles/" + self.state["vehicles"][name]["id"]

    def warehouse(self, name: str) -> str:
        require(name.startswith("api/"), "Refusing browser warehouse mutation")
        return "/api/v1/admin/warehouses/" + self.state["warehouses"][name]["id"] + "/vehicles"

    async def request(self, method: str, path: str, status: int = 200, *, body=None, role=ADMIN, code=None) -> dict:
        from infrastructure.settings import settings

        # An explicit empty Cookie header also prevents a response cookie in
        # the shared HTTP client jar from authenticating the anonymous cases.
        headers = {"Cookie": ""}
        if role is not None:
            headers["Cookie"] = "accessToken=" + self.state["users"][role]["access_token"]
            if settings.csrf_enabled:
                csrf = str(identifier(f"csrf/{role}"))
                headers["Cookie"] += f"; {settings.csrf_cookie_name}={csrf}"
                headers[settings.csrf_header_name] = csrf
        response = await self.client.request(method, path, headers=headers, json=body)
        require(response.status_code == status,
                f"{method} {path} role={role}: expected {status}, got {response.status_code}")
        if status >= 500:
            return {}
        payload = response.json()
        require(isinstance(payload, dict), f"{method} {path}: response must be an object")
        if code:
            detail = payload.get("detail")
            error = detail if isinstance(detail, dict) else payload
            require(error.get("code") == code, f"{method} {path}: expected error code {code}")
        return payload


def reasons(payload: dict, expected: dict[str, int], *, summary: bool = False) -> None:
    actual = payload["blocking_reasons"]
    require(len(actual) == len(expected), "Unexpected number of blocker types")
    require({reason["type"]: reason["count"] for reason in actual} == expected, "Incorrect blocker counts/types")
    require(all(isinstance(reason["description"], str) and reason["description"].strip() for reason in actual),
            "Blocker descriptions must be nonempty")
    if summary:
        require(all(reason["vehicle_count"] > 0 for reason in actual), "Missing unique vehicle counts")


async def rollback_checks(api: API, state: dict) -> None:
    """Inject commit failure after DELETE/cleanup using a task-UUID-only deferred trigger."""
    from sqlalchemy import text

    from infrastructure.database import AsyncSessionLocal

    names = state["warehouses"]["api/rollback"]["vehicles"]
    before = await snapshot(state, names)
    ids = ", ".join(f"'{identifier(f'vehicle/{name}')}'::uuid" for name in names)
    function = "task22242_acceptance_fail_commit"
    trigger = "task22242_acceptance_fail_commit"
    installed = False
    async with AsyncSessionLocal() as session:
        require(not (await session.execute(text("SELECT 1 FROM pg_proc WHERE proname = :name"),
                                           {"name": function})).first(), "Stale task22242 rollback trigger; inspect before rerun")
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(text(f"""
                CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  IF OLD.id IN ({ids}) THEN
                    RAISE EXCEPTION 'task22242 injected commit failure' USING ERRCODE = 'P0001';
                  END IF;
                  RETURN OLD;
                END $$
            """))
            await session.execute(text(f"""
                CREATE CONSTRAINT TRIGGER {trigger} AFTER DELETE ON public.vehicles
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.{function}()
            """))
        installed = True
        await api.request("DELETE", api.vehicle(names[0]), 500, body={"confirmation": "УДАЛИТЬ"})
        require(await snapshot(state, names) == before, "Single deletion failed to roll back all DB rows/queue jobs")
        await api.request("POST", api.warehouse("api/rollback") + "/bulk-delete", 500,
                          body={"confirmed": True, "confirmation": "УДАЛИТЬ"})
        require(await snapshot(state, names) == before, "Bulk deletion failed to roll back all DB rows/queue jobs")
        check("single + bulk injected commit failure: vehicles, bindings, transfers, queue receipts rolled back")
    finally:
        if installed:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(text(f"DROP TRIGGER {trigger} ON public.vehicles"))
                await session.execute(text(f"DROP FUNCTION public.{function}()"))


async def wait_blocked_by(blocker_pid: int, pending: asyncio.Task, *, waiter_pid: int | None = None) -> int:
    """Observe an actual PostgreSQL lock wait, rather than assuming task scheduling order."""
    from sqlalchemy import text

    from infrastructure.database import AsyncSessionLocal

    deadline = time.monotonic() + 45
    async with AsyncSessionLocal() as observer:
        while time.monotonic() < deadline:
            require(not pending.done(), "Concurrent operation finished before the expected PostgreSQL lock wait")
            rows = (await observer.execute(text("""
                SELECT pid FROM pg_stat_activity
                WHERE datname = current_database() AND :blocker = ANY(pg_blocking_pids(pid))
            """), {"blocker": blocker_pid})).scalars().all()
            await observer.rollback()  # Refresh pg_stat_activity snapshot on the next poll.
            matching = [pid for pid in rows if waiter_pid is None or pid == waiter_pid]
            if matching:
                return matching[0]
            await asyncio.sleep(0.1)
    raise AcceptanceFailure("Timed out observing the expected PostgreSQL lock dependency")


async def cancel_pending(pending: asyncio.Task | None) -> None:
    if pending is not None:
        if not pending.done():
            pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)


async def concurrent_checks(api: API, state: dict) -> None:
    """Real HTTP DELETE races with committed/uncommitted INSERT on independent DB connections."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from infrastructure.database import AsyncSessionLocal

    for label, kind in (("cart", "shopping_cart"), ("array", "calculation_history")):
        name = f"api/concurrent/{label}-writer-first"
        before = await snapshot(state, [name])
        pending = None
        async with AsyncSessionLocal() as writer:
            try:
                await writer.execute(text("SET LOCAL statement_timeout = '60s'"))
                writer_pid = (await writer.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                await add_blocker(writer, kind, name)
                # The INSERT's reference guard retains KEY SHARE until commit.
                pending = asyncio.create_task(api.request(
                    "DELETE", api.vehicle(name), 409, body={"confirmation": "УДАЛИТЬ"},
                    code="vehicle_has_blocking_relations"))
                await wait_blocked_by(writer_pid, pending)
                await writer.commit()
                result = await asyncio.wait_for(pending, timeout=60)
                reasons(result, {kind: 1})
            finally:
                await writer.rollback()
                await cancel_pending(pending)
        after = await snapshot(state, [name])
        require(len(after[kind]) == 1 and not before[kind], "Concurrent writer receipt missing")
        after[kind] = []
        require(after == before, "Writer-first race changed the vehicle, bindings, history or queue")
        check(f"concurrent {kind} writer-first: observed API blocked by uncommitted INSERT, commit -> DELETE 409")

    # Hold only these fixture DELETEs immediately before deletion, after the
    # real API has acquired FOR UPDATE and checked blockers. An advisory lock
    # released by a separate connection provides a deterministic rendezvous.
    names = [f"api/concurrent/{label}-delete-first" for label in ("cart", "array")]
    ids = ", ".join(f"'{identifier(f'vehicle/{name}')}'::uuid" for name in names)
    lock_key = identifier("concurrency-gate").int % (2**63 - 1)
    function = "task22242_acceptance_delete_gate"
    installed = False
    async with AsyncSessionLocal() as session:
        require(not (await session.execute(text("SELECT 1 FROM pg_proc WHERE proname = :name"),
                                           {"name": function})).first(), "Stale task22242 concurrency gate; inspect before rerun")
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(text(f"""
                CREATE FUNCTION public.{function}() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                  IF OLD.id IN ({ids}) THEN
                    PERFORM pg_advisory_xact_lock({lock_key});
                  END IF;
                  RETURN OLD;
                END $$
            """))
            await session.execute(text(f"""
                CREATE TRIGGER {function} BEFORE DELETE ON public.vehicles
                FOR EACH ROW EXECUTE FUNCTION public.{function}()
            """))
        installed = True
        for label, kind in (("cart", "shopping_cart"), ("array", "calculation_history")):
            name = f"api/concurrent/{label}-delete-first"
            deletion = None
            insertion = None
            async with AsyncSessionLocal() as gate, AsyncSessionLocal() as writer:
                try:
                    await gate.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
                    gate_pid = (await gate.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    deletion = asyncio.create_task(api.request(
                        "DELETE", api.vehicle(name), body={"confirmation": "УДАЛИТЬ"}))
                    delete_pid = await wait_blocked_by(gate_pid, deletion)
                    await writer.execute(text("SET LOCAL statement_timeout = '60s'"))
                    writer_pid = (await writer.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                    require(len({gate_pid, delete_pid, writer_pid}) == 3, "Concurrent checks need independent connections")
                    insertion = asyncio.create_task(add_blocker(writer, kind, name))
                    await wait_blocked_by(delete_pid, insertion, waiter_pid=writer_pid)
                    await gate.commit()  # Let the real API finish its DELETE and COMMIT.
                    result = await asyncio.wait_for(deletion, timeout=60)
                    require(result["deleted"] is True, "Delete-first operation did not delete")
                    try:
                        await asyncio.wait_for(insertion, timeout=60)
                    except IntegrityError as exc:
                        require(getattr(exc.orig, "sqlstate", None) == "23503",
                                "Concurrent INSERT failed for a reason other than missing vehicle")
                    else:
                        raise AcceptanceFailure("Concurrent INSERT created an orphan after DELETE committed")
                finally:
                    await gate.rollback()
                    await cancel_pending(deletion)
                    await cancel_pending(insertion)
                    await writer.rollback()
            after = await snapshot(state, [name])
            require(not after["vehicles"] and not after["vehicle_warehouses"] and not after[kind],
                    "Delete-first race left a vehicle/binding/orphan")
            require(len(after["vehicle_deletion_outbox"]) == 1, "Delete-first race lost/duplicated the durable tombstone")
            check(f"concurrent {kind} delete-first: observed INSERT blocked by real API, DELETE commit -> SQLSTATE 23503")
    finally:
        if installed:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(text(f"DROP TRIGGER {function} ON public.vehicles"))
                await session.execute(text(f"DROP FUNCTION public.{function}()"))


async def verify() -> None:
    import httpx

    from infrastructure.database import AsyncSessionLocal

    state = load_state()
    require(not state.get("verification_started"), "verify already consumed API fixtures; use a fresh isolated seed")
    require(all(user["access_token_expires"] > time.time() + 180 for user in state["users"].values()),
            "Run auth --execute before verify (need at least 3 minutes token validity)")
    # Chrome may mutate its own browser/ fixtures concurrently. API.vehicle /
    # warehouse enforce the api/ prefix; compare only the API control warehouse.
    protected_names = state["warehouses"]["api/other"]["vehicles"]
    protected_before = await snapshot(state, protected_names)
    async with httpx.AsyncClient(base_url=API_URL, timeout=90, follow_redirects=False, trust_env=False) as client:
        api = API(client, state)
        for role in ROLES:
            me = await api.request("GET", "/api/v1/auth/me", role=role)
            require(me["user"]["id"] == state["users"][role]["id"] and me["user"]["role"] == role,
                    f"Real /auth/me identity mismatch: {role}")
        check("real ES256 auth and /auth/me for five roles")
        single = api.vehicle("api/single/free")
        bulk = api.warehouse("api/bulk")
        unbind = api.warehouse("api/unbind")
        endpoints = [("GET", single + "/deletion-check", None),
                     ("DELETE", single, {"confirmation": "УДАЛИТЬ"}),
                     ("GET", bulk + "/deletion-check", None),
                     ("POST", bulk + "/bulk-delete", {"confirmed": True, "confirmation": "УДАЛИТЬ"}),
                     ("DELETE", unbind, {"confirmed": True})]
        # Readiness before marking the one-shot mutation phase.
        await api.request("GET", single + "/deletion-check")
        state["verification_started"] = datetime.now(UTC).isoformat()
        save_state(state)
        unchanged_names = [name for name in state["vehicles"] if name.startswith("api/")]
        unchanged = await snapshot(state, unchanged_names)
        for role in (None, *ROLES[1:]):
            for method, path, body in endpoints:
                await api.request(method, path, 401 if role is None else 403, body=body, role=role)
        require(await snapshot(state, unchanged_names) == unchanged, "Denied requests changed DB state")
        check("all five endpoints including GET: anonymous 401; four external roles 403; DB unchanged")
        for body in (None, {}, {"confirmation": "wrong"}, {"reason": "not confirmation"}):
            await api.request("DELETE", single, 400, body=body, code="confirmation_mismatch")
        for body in (None, {}, {"confirmed": False}):
            await api.request("DELETE", unbind, 400, body=body, code="confirmation_required")
            await api.request("POST", bulk + "/bulk-delete", 400, body=body, code="confirmation_required")
        for body in ({"confirmed": True}, {"confirmed": True, "confirmation": "wrong"}):
            await api.request("POST", bulk + "/bulk-delete", 400, body=body, code="confirmation_mismatch")
        require(await snapshot(state, unchanged_names) == unchanged, "Bad confirmations changed DB state")
        check("missing/incorrect confirmations return contracted 400, with DB unchanged")
        for kind in BLOCKERS:
            name = "api/blockers/" + kind
            result = await api.request("GET", api.vehicle(name) + "/deletion-check")
            require(result["can_delete"] is False, f"Blocker ignored: {kind}")
            reasons(result, {kind: 1})
            result = await api.request("DELETE", api.vehicle(name), 409, body={"confirmation": "УДАЛИТЬ"},
                                       code="vehicle_has_blocking_relations")
            detail = result.get("detail")
            problem = detail if isinstance(detail, dict) else result
            require(problem["deleted"] is False, f"Blocked delete reported success: {kind}")
            reasons(problem, {kind: 1})
            check(f"blocker {kind}: GET false, DELETE 409")
        multi = await api.request("GET", api.vehicle("api/blockers/multi") + "/deletion-check")
        reasons(multi, {"user_favorites": 1, "shopping_cart": 1, "calculation_history": 2})
        require(await snapshot(state, unchanged_names) == unchanged, "Blocked delete changed business rows")
        check("multiple blockers/counts, cancelled order, UUID array; all refused deletes preserve DB rows")
        for item, kind in (("favorite", "user_favorites"), ("history-array", "calculation_history"),
                           ("guest", "guest_cart_transfers")):
            name = "api/late/" + item
            require((await api.request("GET", api.vehicle(name) + "/deletion-check"))["can_delete"] is True,
                    "Late-blocker fixture not initially free")
            async with AsyncSessionLocal() as session, session.begin():
                await add_blocker(session, kind, name)
            before = await snapshot(state, [name])
            await api.request("DELETE", api.vehicle(name), 409, body={"confirmation": "УДАЛИТЬ"},
                              code="vehicle_has_blocking_relations")
            require(await snapshot(state, [name]) == before, "Late blocker or vehicle removed")
        check("post-GET late blockers: FK favorite, no-FK guest transfer and calculation UUID array")
        await rollback_checks(api, state)
        await concurrent_checks(api, state)
        for item in ("free", "history", "no-vin"):
            name = "api/single/" + item
            before = await snapshot(state, [name])
            result = await api.request("GET", api.vehicle(name) + "/deletion-check")
            require(result["can_delete"] is True and result["vin"] == state["vehicles"][name]["vin"],
                    "Free/VIN contract mismatch")
            reasons(result, {})
            result = await api.request("DELETE", api.vehicle(name), body={
                "confirmation": state["vehicles"][name]["vin"] if item == "free" else "УДАЛИТЬ"})
            require(result["deleted"] is True and result["vehicle_id"] == state["vehicles"][name]["id"],
                    "Wrong single deletion response")
            require(result["cleaned_relations"]["vehicle_warehouses"] == 1
                    and result["cleaned_relations"]["vehicle_warehouse_transfers"] == (1 if item == "history" else 0),
                    "Incorrect cleaned relation counts")
            after = await snapshot(state, [name])
            require(not any(after[key] for key in ("vehicles", "vehicle_warehouses", "vehicle_warehouse_transfers")),
                    "Single deletion left inventory rows")
            require(all(after[key] == before[key] for key in ("warehouses", "mark", "model")),
                    "Single deletion changed warehouse/catalog references")
            require(len(after["vehicle_deletion_outbox"]) == 1, "Single deletion lost/duplicated durable tombstone")
            payload = json.loads(after["vehicle_deletion_outbox"][0])["payload"]
            require(payload["_deleted"] is True and payload["vehicle_id"] == state["vehicles"][name]["id"],
                    "Incorrect deletion outbox payload")
            await api.request("DELETE", api.vehicle(name), 404, body={"confirmation": "УДАЛИТЬ"}, code="vehicle_not_found")
            await api.request("GET", api.vehicle(name) + "/deletion-check", 404, code="vehicle_not_found")
            require(await snapshot(state, [name]) == after, "Repeated DELETE changed persistent side-effect receipts")
        check("single delete: VIN/word/no VIN, transfer cleanup, repeat 404 without further effects")
        summary = await api.request("GET", bulk + "/deletion-check")
        require((summary["requested_count"], summary["deletable_count"], summary["blocked_count"]) == (5, 3, 2),
                "Bulk preview counted vehicles incorrectly")
        reasons(summary, {"user_favorites": 2, "shopping_cart": 1, "calculation_history": 2}, summary=True)
        require({r["type"]: r["vehicle_count"] for r in summary["blocking_reasons"]}
                == {"user_favorites": 2, "shopping_cart": 1, "calculation_history": 1}, "Summary double-counted a vehicle")
        async with AsyncSessionLocal() as session, session.begin():
            await add_blocker(session, "calculation_history", "api/bulk/late")
        skipped_names = ["api/bulk/" + item for item in ("favorites", "multi", "late")]
        skipped_before = await snapshot(state, skipped_names)
        for expected_deleted in (2, 0):
            result = await api.request("POST", bulk + "/bulk-delete", body={"confirmed": True, "confirmation": "УДАЛИТЬ"})
            require((result["requested_count"], result["deleted_count"], result["skipped_count"])
                    == (expected_deleted + 3, expected_deleted, 3), "Bulk result counts are inconsistent")
            require(len(result["skipped"]) == 3 and {row["vehicle_id"] for row in result["skipped"]}
                    == {state["vehicles"][name]["id"] for name in skipped_names}, "Incomplete skipped vehicle list")
            for row in result["skipped"]:
                name = next(name for name in skipped_names if state["vehicles"][name]["id"] == row["vehicle_id"])
                require(row["vin"] == state["vehicles"][name]["vin"], "Wrong skipped VIN")
                reasons(row, {"user_favorites": 1} if name.endswith("favorites") else
                        {"calculation_history": 1} if name.endswith("late") else
                        {"user_favorites": 1, "shopping_cart": 1, "calculation_history": 2})
            require(await snapshot(state, skipped_names) == skipped_before, "Bulk altered blocked inventory or business rows")
        deleted = await snapshot(state, ["api/bulk/free", "api/bulk/history"])
        require(not any(deleted[key] for key in ("vehicles", "vehicle_warehouses", "vehicle_warehouse_transfers")),
                "Bulk left permitted cars/bindings/history")
        require(len(deleted["vehicle_deletion_outbox"]) == 2, "Bulk deletion lost/duplicated durable tombstones")
        check("bulk summary unique counts, late blocker skipped, full reasons/VIN, repeat deletes 0, blocked DB unchanged")
        names = state["warehouses"]["api/unbind"]["vehicles"]
        before = await snapshot(state, names)
        page = await api.request("GET", unbind + "?page=1&limit=20")
        require(len(page["vehicles"]) == 20 and len(names) > 200, "Pagination fixture not larger than a page")
        for count in (len(names), 0):
            result = await api.request("DELETE", unbind, body={"confirmed": True})
            require(result["unbound_count"] == count, "Wrong unbound_count")
        after = await snapshot(state, names)
        require(not after["vehicle_warehouses"], "Unbind left hidden-page bindings")
        before["vehicle_warehouses"] = []
        require(after == before, "Unbind changed cars, history, business links, warehouse or queue")
        empty = await api.request("GET", unbind + "/deletion-check")
        require((empty["requested_count"], empty["deletable_count"], empty["blocked_count"]) == (0, 0, 0),
                "Empty warehouse preview is not empty")
        reasons(empty, {})
        empty = await api.request("POST", unbind + "/bulk-delete", body={"confirmed": True, "confirmation": "УДАЛИТЬ"})
        require((empty["requested_count"], empty["deleted_count"], empty["skipped_count"], empty["skipped"])
                == (0, 0, 0, []), "Empty warehouse bulk delete is not idempotent")
        missing = "/api/v1/admin/warehouses/" + str(identifier("absent-warehouse")) + "/vehicles"
        await api.request("GET", missing + "/deletion-check", 404, code="warehouse_not_found")
        await api.request("DELETE", missing, 404, body={"confirmed": True}, code="warehouse_not_found")
        await api.request("POST", missing + "/bulk-delete", 404,
                          body={"confirmed": True, "confirmation": "УДАЛИТЬ"}, code="warehouse_not_found")
        require(await snapshot(state, protected_names) == protected_before, "Other warehouse changed")
        check("unbind 205 cars across pages including blocked car, repeat 0; all other DB rows preserved")
        check("other warehouse unchanged; browser fixtures excluded from all API mutation targets")
    state["verified_at"] = datetime.now(UTC).isoformat()
    save_state(state)
    print("ACCEPTED API/DB checks complete. Worker/S3/Kafka delivery still needs coordinator acceptance.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "seed", "auth", "bootstrap", "verify"), nargs="?", default="plan")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend-path", default="/app")
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)  # SQL/HTTP exception logs must never expose token parameters.
    if args.mode == "plan":
        print("22242: seed --execute; verify --execute; auth --execute (renew); bootstrap --execute")
        print("Requires /runtime mount, real migrated DB and backend:3002; bootstrap listens 0.0.0.0:3003.")
        print("Only API fixtures consumed by verify; no Docker/migrations/commits. Secrets: /runtime/fixtures.secret.json (0600).")
        return
    try:
        settings = guard(args)
        if args.mode == "bootstrap":
            bootstrap()
        elif args.mode == "seed":
            asyncio.run(seed(settings))
        elif args.mode == "auth":
            asyncio.run(renew(settings))
        else:
            asyncio.run(verify())
    except AcceptanceFailure as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as exc:
        # Do not print SQLAlchemy parameter dumps, JWTs, HTTP headers or DSNs.
        print(f"FAIL {type(exc).__name__}; inspect isolated service logs/state (secret details suppressed)", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
