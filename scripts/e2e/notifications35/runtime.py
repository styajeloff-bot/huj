#!/usr/bin/env python3
"""Local ТЗ35 runtime acceptance harness; never import from production code.

Default mode is a no-I/O plan. Root explicitly starts the isolated Compose stack
and runs seed/smoke with --execute after its health checks pass. This file does
not run Docker, migrate schema, call OTP/SMS, or invoke notification processors
inline. Only fixture setup and a scoped permission revocation use direct SQL.
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
from decimal import Decimal
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

MARKER = "tz35-runtime"
ROLES = ("client", "dealer", "distributor", "leasing_company", "carcraft_employee")
HOST_DIR = Path("/tmp/carcraft-notifications35-followup-v2-runtime")  # noqa: S108 - root-approved disposable bind mount
API_ALLOWLIST = {"http://nginx", "http://localhost:18048", "http://127.0.0.1:18048"}
SMTP_API_ALLOWLIST = {"http://smtp:8025", "http://localhost:18049", "http://127.0.0.1:18049"}
# Exact bootstrap identity contract from migrations 001 and 005. UUIDs in those
# migrations are random, so validate immutable phone/role pairs before selecting
# the precise UUIDs to deactivate in the isolated test database.
BOOTSTRAP_USERS = {
    **{f"+76660{index:06d}": "dealer" for index in range(3, 13)},
    "+76660000001": "carcraft_employee",
    "+76660000002": "carcraft_employee",
    "+76661234568": "dealer",
    "+76661234571": "leasing_company",
    "+76661234572": "leasing_company",
    "+76661234573": "distributor",
    "+76661234574": "distributor",
}

if TYPE_CHECKING:
    from infrastructure.settings import Settings


def identifier(name: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://notifications35.test/{MARKER}/{name}")


def require(condition: bool, explanation: str) -> None:
    if not condition:
        raise RuntimeError(explanation)


def progress(stage: str, **values: object) -> None:
    sys.stdout.write(json.dumps({"stage": stage, **values}, ensure_ascii=False, default=str) + "\n")
    sys.stdout.flush()


def state_directory(args: argparse.Namespace) -> Path:
    directory = Path(args.state_dir).resolve()
    require(directory in {HOST_DIR.resolve(), Path("/runtime")}, "State directory is not an approved disposable path")
    require(directory.is_dir(), "Root must create the disposable directory first")
    return directory


def write_json(path: Path, value: object) -> None:
    # Runtime artifacts only, never a repository file. O_NOFOLLOW prevents a
    # malicious symlink from turning a test-state write into an unrelated write.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(value, output, ensure_ascii=False, indent=2, default=str)
        output.write("\n")


def load_state(directory: Path) -> dict:
    value = json.loads((directory / "fixtures.secret.json").read_text())
    require(value.get("marker") == MARKER, "Unexpected fixture marker")
    require(set(value["users"]) == set(ROLES), "Unexpected fixture role set")
    for role, user in value["users"].items():
        require(user["id"] == str(identifier(f"user/{role}")), "Unexpected fixture user ID")
        require(user["email"] == f"{role}@notifications35.test", "Unexpected fixture email")
    return cast("dict", value)


def guard_runtime(args: argparse.Namespace) -> tuple[Path, Settings]:
    require(args.execute, "Write/network mode requires explicit --execute after root green health")
    directory = state_directory(args)
    require(args.api_url in API_ALLOWLIST, "API URL is not an isolated runtime endpoint")
    require(args.smtp_api_url in SMTP_API_ALLOWLIST, "SMTP API is not the local sink")
    require(args.metrics_url == "http://event-worker:8000/metrics", "Unexpected worker metrics endpoint")
    sys.path.insert(0, args.backend_path)
    from sqlalchemy.engine import make_url

    from infrastructure.settings import settings

    dsn = make_url(settings.database_dsn)
    require(dsn.database == "notifications35_runtime", "Refusing any DB except notifications35_runtime")
    require(dsn.host in {"postgres", "localhost", "127.0.0.1"}, "Unexpected DB host")
    require(dsn.username == "notifications35", "Unexpected DB user")
    require(settings.smtp_host == "smtp", "SMTP must point at the isolated smtp service")
    require(settings.smtp_user.endswith("@notifications35.test"), "SMTP sender must use the test-only domain")
    require(settings.public_url == "http://localhost:18048", "PUBLIC_URL must remain localhost:18048")
    require(settings.jwt_keys_dir == "/runtime-keys/jwt", "Refusing non-runtime JWT signing keys")
    require(bool(settings.s3_endpoint and settings.s3_bucket), "Object storage must be configured")
    require(urlsplit(settings.redis_url).hostname == "redis", "Unexpected Redis host")
    require(all(part.split(":")[0] == "redpanda" for part in settings.kafka_brokers.split(",")), "Unexpected Kafka host")
    return directory, settings


def browser_state(user: dict) -> dict:
    cookies = [{
        "name": name, "value": user[key], "domain": "localhost", "path": "/",
        "httpOnly": True, "secure": False, "sameSite": "Lax",
        "expires": user[f"{key}_expires"],
    } for name, key in (("accessToken", "access_token"), ("refreshToken", "refresh_token"))]
    return {"cookies": cookies, "origins": []}


def browser_artifacts(directory: Path, state: dict) -> None:
    now = time.time()
    links = {}
    for role, user in state["users"].items():
        write_json(directory / f"browser-{role}.secret.json", browser_state(user))
        links[role] = {
            "bootstrap": f"http://localhost:18050/login/{role}",
            "inbox": "http://localhost:18048/notifications",
            "email_preferences": "http://localhost:18048/settings/email",
            "access_token_valid_seconds": max(0, int(user["access_token_expires"] - now)),
        }
    write_json(directory / "browser-links.json", {"marker": MARKER, "viewport_min_width": 768, "roles": links})


async def seed(args: argparse.Namespace) -> None:  # noqa: PLR0915 - sequential one-time fixture recipe
    directory, settings = guard_runtime(args)
    require(not (directory / "fixtures.secret.json").exists(), "Fixtures already exist; use smoke or auth, never reseed over them")
    from sqlalchemy import select, update

    from domain.storefronts import DEFAULT_STOREFRONT_ID
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import (
        ApplicationVehicle,
        LeasingApplication,
        LeasingCompanyApplication,
    )
    from infrastructure.models.companies import (
        Company,
        DistributorDealerLink,
        LeasingCompany,
        LeasingCompanyUser,
    )
    from infrastructure.models.email_preferences import EmailPreferences
    from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
    from infrastructure.models.users import User, UserCompany, UserSession
    from infrastructure.models.vehicles import Vehicle, VehicleWarehouse, Warehouse

    async with AsyncSessionLocal() as session:
        existing_users = (await session.execute(select(User.id, User.phone, User.role, User.is_active).with_for_update())).all()
        actual_users = {row.phone: row.role for row in existing_users}
        require(actual_users == BOOTSTRAP_USERS and len(existing_users) == 17,
            "Runtime bootstrap users differ from the exact 17 migration phone/role pairs")
        bootstrap_ids = [row.id for row in existing_users]
        require(not set(bootstrap_ids) & {identifier(f"user/{role}") for role in ROLES}, "A fixture ID unexpectedly exists")
        bootstrap_report = {"state": "planned", "users": [{"id": str(row.id), "previous_is_active": row.is_active}
            for row in existing_users]}
        write_json(directory / "bootstrap-deactivation.json", bootstrap_report)
        changed = await session.execute(update(User).where(User.id.in_(bootstrap_ids)).values(is_active=False).returning(User.id))
        require(len(changed.all()) == 17, "Scoped bootstrap deactivation did not affect exactly 17 approved rows")
        require(await session.get(Company, identifier("company/buyer")) is None, "Fixture companies already exist")
        if await session.get(Storefront, DEFAULT_STOREFRONT_ID) is None:
            session.add(Storefront(id=DEFAULT_STOREFRONT_ID, is_default=True, is_active=True, slug=None, version=1))
            await session.flush()
        companies = {name: Company(id=identifier(f"company/{name}"), name=f"ТЗ35 runtime {name}",
            company_type=kind, is_active=True) for name, kind in (
                ("buyer", "other"), ("dealer", "dealer"), ("dealer_home", "dealer"),
                ("distributor", "distributor"), ("lc", "leasing_company"))}
        companies["buyer"].director_full_name = "Тестовый Директор ТЗ35"
        companies["buyer"].director_inn = "000000000035"
        session.add_all(companies.values())
        await session.flush()
        primary = {"client": "buyer", "dealer": "dealer_home", "distributor": "distributor", "leasing_company": "lc"}
        target = {**primary, "dealer": "dealer"}
        users = {}
        for index, role in enumerate(ROLES, 1):
            users[role] = User(id=identifier(f"user/{role}"), name=f"ТЗ35 runtime {role}",
                phone=f"+7000003500{index}", email=f"{role}@notifications35.test", role=role,
                company_id=companies[primary[role]].id if role in primary else None,
                is_active=True, email_verified=True, phone_verified=True)
        session.add_all(users.values())
        await session.flush()
        for role, name in target.items():
            session.add(UserCompany(user_id=users[role].id, company_id=companies[name].id,
                sub_role="administrator", can_view_applications=True, can_create_applications=True))
        session.add(UserCompany(user_id=users["dealer"].id, company_id=companies["dealer_home"].id,
            sub_role="administrator", can_view_applications=True, can_create_applications=True))
        lc = LeasingCompany(id=identifier("lc"), company_id=companies["lc"].id, is_active=True)
        warehouse = Warehouse(id=identifier("warehouse"), address="ТЗ35 runtime — local fixture", brand="ТЗ35",
            company_id=companies["dealer"].id, dealer_id=companies["dealer"].id, status="active")
        vehicle = Vehicle(id=identifier("vehicle"), dealer_id=companies["dealer"].id,
            vin="TZ35RUNTIME000001", year=2026, color="ТЗ35 fixture", status="available", is_available=True,
            base_price=Decimal("1000000.00"))
        session.add_all([lc, warehouse, vehicle])
        await session.flush()
        session.add_all([
            LeasingCompanyUser(user_id=users["leasing_company"].id, leasing_company_id=lc.id),
            DistributorDealerLink(distributor_company_id=companies["distributor"].id, dealer_company_id=companies["dealer"].id),
            VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id),
            StorefrontWarehouse(storefront_id=DEFAULT_STOREFRONT_ID, warehouse_id=warehouse.id),
        ])
        app = LeasingApplication(id=identifier("application"), company_id=companies["buyer"].id,
            dealer_company_id=companies["dealer"].id, created_by=users["client"].id,
            status="active", display_number="TZ35-RUNTIME-001", selected_leasing_companies=[lc.id],
            name="ТЗ35 runtime acceptance", total_amount=Decimal("1000000.00"), storefront_id=DEFAULT_STOREFRONT_ID)
        session.add(app)
        await session.flush()
        session.add_all([
            ApplicationVehicle(id=identifier("application-vehicle"), application_id=app.id, vehicle_id=vehicle.id,
                dealer_company_id=companies["dealer"].id, quantity=1, unit_price=Decimal("1000000.00"), total_price=Decimal("1000000.00")),
            LeasingCompanyApplication(application_id=app.id, leasing_company_id=lc.id, status="under_review"),
        ])
        now = datetime.now(UTC)
        state: dict[str, Any] = {"marker": MARKER, "seeded_at": now.isoformat(), "application_id": str(app.id),
            "vehicle_id": str(vehicle.id), "warehouse_id": str(warehouse.id), "leasing_company_id": str(lc.id),
            "companies": {name: str(row.id) for name, row in companies.items()}, "users": {}, "events": {}}
        for role, user in users.items():
            session_id = uuid4()
            access, refresh = generate_tokens(user.id, role, user.company_id, refresh_session_id=session_id)
            refresh_expiry = now + timedelta(days=settings.refresh_token_expiry_days)
            session.add(UserSession(id=session_id, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh),
                expires_at=refresh_expiry, ip_address="127.0.0.1", user_agent="ТЗ35 runtime smoke"))
            session.add(EmailPreferences(user_id=user.id, email_frequency="immediate", exchange_emails=True,
                application_status_emails=True, document_request_emails=True, document_status_emails=True,
                leasing_approval_emails=True, system_emails=True, weekly_digest=True, marketing_emails=False))
            state["users"][role] = {"id": str(user.id), "email": user.email,
                "company_id": str(user.company_id) if user.company_id else None,
                "access_token": access, "refresh_token": refresh,
                "access_token_expires": (now + timedelta(minutes=settings.access_token_expiry_minutes)).timestamp(),
                "refresh_token_expires": refresh_expiry.timestamp()}
        await session.commit()
    bootstrap_report["state"] = "applied"
    write_json(directory / "bootstrap-deactivation.json", bootstrap_report)
    write_json(directory / "fixtures.secret.json", state)
    browser_artifacts(directory, state)
    progress("seeded", users=len(users), application_id=state["application_id"], browser_roles=list(ROLES))


async def renew_auth(args: argparse.Namespace) -> None:
    directory, settings = guard_runtime(args)
    state = load_state(directory)
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.users import User, UserSession

    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        for role, value in state["users"].items():
            user = await session.get(User, UUID(value["id"]))
            if user is None or not user.is_active or user.role != role or user.deleted_at:
                raise RuntimeError("A fixture user is inactive, deleted, or has changed role")
            session_id = uuid4()
            access, refresh = generate_tokens(user.id, user.role, user.company_id, refresh_session_id=session_id)
            expires = now + timedelta(days=settings.refresh_token_expiry_days)
            session.add(UserSession(id=session_id, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh),
                expires_at=expires, ip_address="127.0.0.1", user_agent="ТЗ35 runtime browser renewal"))
            value.update(access_token=access, refresh_token=refresh, refresh_token_expires=expires.timestamp(),
                access_token_expires=(now + timedelta(minutes=settings.access_token_expiry_minutes)).timestamp())
        await session.commit()
    write_json(directory / "fixtures.secret.json", state)
    browser_artifacts(directory, state)
    progress("auth_renewed", roles=list(ROLES))


async def new_scenario(args: argparse.Namespace) -> None:
    """Append a new fixture application; preserve every previous run and event."""
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import (
        ApplicationVehicle,
        LeasingApplication,
        LeasingCompanyApplication,
    )
    from infrastructure.models.companies import Company

    require(bool(state.get("smoke_completed_at")), "Finish/resume the previous scenario before starting another")
    application_id = uuid4()
    display_number = f"TZ35-{str(application_id)[:8]}"
    async with AsyncSessionLocal() as session:
        buyer = await session.get(Company, UUID(state["companies"]["buyer"]))
        require(buyer is not None and buyer.name == "ТЗ35 runtime buyer", "Wrong fixture company")
        assert buyer is not None
        buyer.director_full_name = "Тестовый Директор ТЗ35"
        buyer.director_inn = "000000000035"
        app = LeasingApplication(
            id=application_id, company_id=buyer.id,
            dealer_company_id=UUID(state["companies"]["dealer"]),
            created_by=UUID(state["users"]["client"]["id"]), status="active",
            display_number=display_number, selected_leasing_companies=[UUID(state["leasing_company_id"])],
            name="ТЗ35 runtime acceptance", total_amount=Decimal("1000000.00"),
            storefront_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        session.add(app)
        await session.flush()
        session.add_all([
            ApplicationVehicle(application_id=application_id, vehicle_id=UUID(state["vehicle_id"]),
                dealer_company_id=UUID(state["companies"]["dealer"]), quantity=1,
                unit_price=Decimal("1000000.00"), total_price=Decimal("1000000.00")),
            LeasingCompanyApplication(application_id=application_id,
                leasing_company_id=UUID(state["leasing_company_id"]), status="under_review"),
        ])
        await session.commit()
    write_json(directory / f"completed-{state['application_id']}.secret.json", state)
    for key in ("smoke_started_at", "smoke_completed_at", "exchange_request_id", "editable_application_id", "followup", "context_acceptance"):
        state.pop(key, None)
    state.update(application_id=str(application_id), application_number=display_number, events={})
    write_json(directory / "fixtures.secret.json", state)
    progress("new_scenario", application_id=str(application_id), previous_data="preserved")


async def prepare(args: argparse.Namespace) -> None:
    directory, _ = guard_runtime(args)
    if not (directory / "fixtures.secret.json").exists():
        await seed(args)
        return
    state = load_state(directory)
    if state.get("smoke_completed_at"):
        await new_scenario(args)
    else:
        require(not state.get("smoke_started_at"), "Interrupted scenario: explicitly resume smoke before another E2E run")
    await renew_auth(args)


class Smoke:
    def __init__(self, args: argparse.Namespace, directory: Path, state: dict):
        self.args, self.directory, self.state = args, directory, state
        self.report: dict[str, Any] = {"marker": MARKER, "started_at": datetime.now(UTC).isoformat(), "checks": []}

    async def api(self, role: str | None, method: str, path: str, *, expected: int = 200,
                  body: dict | None = None, headers: dict | None = None) -> Any:
        import httpx
        require(path.startswith("/api/v1/"), "Only the public runtime API is allowed")
        cookies = {"accessToken": self.state["users"][role]["access_token"]} if role else {}
        async with httpx.AsyncClient(base_url=self.args.api_url, cookies=cookies, trust_env=False,
            follow_redirects=False, timeout=30) as client:
            response = await client.request(method, path, json=body, headers=headers)
        require(response.status_code == expected,
            f"{role or 'public'} {method} {path}: expected {expected}, got {response.status_code}; {response.text[:700]}")
        return response.json() if response.content else None

    async def query(self, sql: str, **params: object) -> list[dict]:
        from sqlalchemy import text

        from infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            return [dict(row) for row in (await session.execute(text(sql), params)).mappings()]

    async def checkpoint(self) -> int:
        return int((await self.query("SELECT coalesce(max(sequence), 0) AS value FROM notification_event_outbox"))[0]["value"])

    async def event_after(self, sequence: int, kind: str, aggregate_id: str) -> dict:
        rows = await self.query("SELECT event_id, sequence, payload FROM notification_event_outbox "
            "WHERE sequence > :sequence AND event_type = :kind AND aggregate_id = CAST(:aggregate AS uuid)",
            sequence=sequence, kind=kind, aggregate=aggregate_id)
        require(len(rows) == 1, f"Expected exactly one {kind} outbox event, found {len(rows)}")
        return rows[0]

    async def mail_messages(self) -> list[dict]:
        import httpx
        async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
            response = await client.get(f"{self.args.smtp_api_url}/api/v1/messages", params={"limit": 1000})
        require(response.status_code == 200, f"Mailpit returned {response.status_code}")
        value = response.json()
        require(isinstance(value.get("messages"), list), "Unexpected Mailpit list shape")
        messages = value["messages"]
        for message in messages:
            for address in (message.get("To") or []) + (message.get("Cc") or []) + (message.get("Bcc") or []):
                require(address.get("Address", "").endswith("@notifications35.test"), "Non-fixture recipient detected in local sink")
        return cast("list[dict]", messages)

    async def observe(self, event: dict, expected: dict[str, str], *, exchange: bool = False) -> list[dict]:
        event_id = str(event["event_id"])
        wanted = {self.state["users"][role]["id"]: status for role, status in expected.items()}
        deadline = time.monotonic() + self.args.timeout
        last = {}
        while time.monotonic() < deadline:
            outbox = (await self.query("SELECT published_at, publish_attempts FROM notification_event_outbox WHERE event_id = CAST(:id AS uuid)", id=event_id))[0]
            receipt = await self.query("SELECT event_id FROM notification_event_receipts WHERE event_id = CAST(:id AS uuid)", id=event_id)
            inbox = await self.query("SELECT id, user_id, application_id, action_url, data FROM notifications WHERE event_id = CAST(:id AS uuid)", id=event_id)
            deliveries = await self.query("SELECT user_id, status, message_id, attempt_count, last_error FROM notification_email_deliveries WHERE event_id = CAST(:id AS uuid)", id=event_id)
            actual = {str(row["user_id"]): row["status"] for row in deliveries}
            last = {"published": bool(outbox["published_at"]), "receipt": bool(receipt), "delivery_statuses": actual}
            if receipt:
                require({str(row["user_id"]) for row in inbox} == set(wanted), f"Wrong inbox recipient set for {event_id}: {last}")
                require(set(actual) == set(wanted), f"Wrong delivery recipient set for {event_id}: {last}")
                require(not any(value == "failed" for value in actual.values()), f"Email failed for event {event_id}: {deliveries}")
            if outbox["published_at"] and receipt and actual == wanted:
                messages = await self.mail_messages()
                message_ids = {str(row.get("MessageID", "")).strip("<>") for row in messages}
                sent_ids = {str(row["message_id"]).strip("<>") for row in deliveries if row["status"] == "sent"}
                if not sent_ids <= message_ids:
                    last["missing_smtp_message_ids"] = sorted(sent_ids - message_ids)
                    await asyncio.sleep(1)
                    continue
                self.verify_mail_recipients(deliveries, messages)
                if exchange:
                    require(all(row["application_id"] is None for row in inbox), "Exchange inbox must not forge a leasing application FK")
                for role in expected:
                    listing = await self.api(role, "GET", "/api/v1/notifications?limit=100")
                    require(any(row.get("event_id") == event_id for row in listing["notifications"]), f"{role} HTTP inbox does not expose committed event")
                self.report["checks"].append({"event_id": event_id, "event_type": event["payload"]["event_type"],
                    "outbox_published": True, "receipt": True, "recipients": expected,
                    "smtp_message_ids": sorted(sent_ids), "exchange_null_application_id": exchange})
                progress("event_complete", event_type=event["payload"]["event_type"], recipients=expected)
                write_json(self.directory / "smoke-report.json", self.report)
                return inbox
            await asyncio.sleep(1)
        raise RuntimeError(f"Timed out observing event {event_id}: {last}")

    def verify_mail_recipients(self, deliveries: list[dict], messages: list[dict]) -> None:
        emails = {user["id"]: user["email"] for user in self.state["users"].values()}
        for delivery in deliveries:
            if delivery["status"] != "sent":
                continue
            matching = [message for message in messages
                if message.get("MessageID", "").strip("<>") == delivery["message_id"].strip("<>")]
            require(len(matching) == 1, "Expected exactly one SMTP message for this delivery")
            message = matching[0]
            require([address["Address"] for address in (message.get("To") or [])]
                == [emails[str(delivery["user_id"])]], "SMTP message sent to the wrong fixture recipient")
            require(not message.get("Cc") and not message.get("Bcc"), "Unexpected additional SMTP recipients")

    async def metric(self) -> float:
        import httpx
        deadline = time.monotonic() + self.args.timeout
        async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
            while True:
                try:
                    response = await client.get(self.args.metrics_url)
                    break
                except httpx.ConnectError:
                    require(time.monotonic() < deadline, "Event-worker did not finish starting its subscribers/metrics")
                    await asyncio.sleep(1)
        require(response.status_code == 200, "Event-worker metrics are unavailable")
        total = 0.0
        for line in response.text.splitlines():
            if line.startswith("notification_events_total{") and 'stage="deduplicated"' in line:
                total += float(line.rsplit(" ", 1)[1])
        return total

    async def replay(self, event: dict) -> None:
        from infrastructure.messaging.broker import get_broker
        from infrastructure.messaging.topics import NOTIFICATION_EVENTS
        before_metric = await self.metric()
        before_mail = len(await self.mail_messages())
        event_id = str(event["event_id"])
        before_rows = await self.query("SELECT id, user_id FROM notifications WHERE event_id = CAST(:id AS uuid) ORDER BY id", id=event_id)
        before_deliveries = await self.query("SELECT id, status FROM notification_email_deliveries WHERE event_id = CAST(:id AS uuid) ORDER BY id", id=event_id)
        broker = get_broker()
        await broker.connect()
        try:
            for _ in range(2):
                await broker.publish(event["payload"], topic=NOTIFICATION_EVENTS,
                    key=str(event["payload"]["aggregate_id"]).encode())
        finally:
            await broker.stop()
        deadline = time.monotonic() + self.args.timeout
        while await self.metric() < before_metric + 2:
            require(time.monotonic() < deadline, "Kafka replay was not observed by the event-worker dedup counter")
            await asyncio.sleep(1)
        require(await self.query("SELECT id, user_id FROM notifications WHERE event_id = CAST(:id AS uuid) ORDER BY id", id=event_id) == before_rows,
            "Kafka replay duplicated inbox rows")
        require(await self.query("SELECT id, status FROM notification_email_deliveries WHERE event_id = CAST(:id AS uuid) ORDER BY id", id=event_id) == before_deliveries,
            "Kafka replay duplicated delivery intents")
        require(len(await self.mail_messages()) == before_mail, "Kafka replay caused an extra SMTP message")
        self.report["checks"].append({"replay_event_id": event_id, "kafka_duplicates_consumed": 2, "extra_inbox_delivery_smtp": 0})
        progress("replay_complete", duplicates_consumed=2, extra_inbox_delivery_smtp=0)

    async def dealer_permissions(self, *, can_view: bool, can_create: bool = True) -> None:
        from sqlalchemy import text

        from infrastructure.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("UPDATE user_companies SET can_view_applications = :view, can_create_applications = :create "
                "WHERE user_id = CAST(:user AS uuid) AND company_id = CAST(:company AS uuid) RETURNING user_id"),
                {"view": can_view, "create": can_create, "user": self.state["users"]["dealer"]["id"], "company": self.state["companies"]["dealer"]})
            require(len(result.all()) == 1, "Expected exactly one fixture membership to update")
            await session.commit()

    def remember_event(self, name: str, event: dict) -> None:
        self.state["events"][name] = str(event["event_id"])
        write_json(self.directory / "fixtures.secret.json", self.state)

    async def saved_event(self, name: str) -> dict | None:
        value = self.state["events"].get(name)
        if not value:
            return None
        rows = await self.query("SELECT event_id, sequence, payload FROM notification_event_outbox WHERE event_id = CAST(:id AS uuid)", id=value)
        require(len(rows) == 1, "Saved fixture event no longer exists")
        return rows[0]

    async def run(self) -> None:  # noqa: PLR0915 - ordered acceptance checklist, not a reusable framework
        require(not self.state.get("smoke_completed_at"), "Smoke already completed")
        require(not self.state.get("smoke_started_at") or self.args.resume, "Interrupted smoke requires explicit --resume, never repeat business mutations")
        await self.api(None, "GET", "/api/v1/health")
        await self.metric()
        for role in ROLES:
            me = await self.api(role, "GET", "/api/v1/auth/me")
            require(me["user"]["id"] == self.state["users"][role]["id"], "Authenticated as the wrong fixture user")
        self.state.setdefault("smoke_started_at", datetime.now(UTC).isoformat())
        write_json(self.directory / "fixtures.secret.json", self.state)
        progress("authenticated", roles=list(ROLES))
        app_id = self.state["application_id"]
        finalized = await self.saved_event("finalized")
        if finalized is None:
            # The initial interrupted probe committed exactly this known fixture
            # event before its first artifact checkpoint. Recover it read-only.
            if self.args.resume:
                finalized = await self.event_after(0, "leasing.application_finalized", app_id)
            else:
                checkpoint = await self.checkpoint()
                await self.api("carcraft_employee", "PUT", f"/api/v1/applications/{app_id}/status", body={"status": "rejected"})
                finalized = await self.event_after(checkpoint, "leasing.application_finalized", app_id)
            self.remember_event("finalized", finalized)
        generic_inbox = await self.observe(finalized, dict.fromkeys(ROLES, "sent"))
        for role in ROLES:
            notice = next(row for row in generic_inbox if str(row["user_id"]) == self.state["users"][role]["id"])
            query = urlsplit(notice["action_url"]).query
            await self.api(role, "GET", f"/api/v1/applications/{app_id}" + (f"?{query}" if query else ""))
        published = await self.saved_event("published")
        if published is None:
            checkpoint = await self.checkpoint()
            created = await self.api("leasing_company", "POST", "/api/v1/exchange/requests/", expected=201, body={
                "vehicle_id": self.state["vehicle_id"], "quantity": 2,
                "expiration_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                "warehouses": [{"warehouse_id": self.state["warehouse_id"], "dealer_id": self.state["companies"]["dealer"], "dealer_comment": "ТЗ35 runtime"}],
            })
            self.state["exchange_request_id"] = created["request"]["id"]
            published = await self.event_after(checkpoint, "exchange.request_published", self.state["exchange_request_id"])
            self.remember_event("published", published)
        request_id = self.state["exchange_request_id"]
        exchange_inbox = await self.observe(published, {"dealer": "sent"}, exchange=True)
        await self.replay(published)
        notice = exchange_inbox[0]
        query = parse_qs(urlsplit(notice["action_url"]).query)
        require(query.get("notification_company_id") == [self.state["companies"]["dealer"]], "Secondary dealer action lacks the correct company selector")
        selector = "?" + urlencode({"notification_company_id": self.state["companies"]["dealer"]})
        dealer_detail = f"/api/v1/exchange/requests/dealer/{request_id}"
        await self.api("dealer", "GET", dealer_detail + selector)
        await self.api("dealer", "GET", dealer_detail, expected=403)
        await self.api("dealer", "GET", dealer_detail + f"?notification_company_id={identifier('unknown-company')}", expected=403)
        await self.api("distributor", "GET", f"/api/v1/exchange/distributor/requests/{request_id}")
        listing = await self.api("distributor", "GET", "/api/v1/exchange/distributor/requests")
        require("items" in listing and "pagination" in listing and "requests" not in listing, "New distributor list must use items/pagination")
        await self.api("distributor", "PATCH", f"/api/v1/exchange/requests/{request_id}", expected=403, body={"quantity": 99})
        try:
            await self.api("dealer", "PUT", "/api/v1/email-preferences", body={"exchange_emails": False})
            changed = await self.saved_event("preference_changed")
            if changed is None:
                checkpoint = await self.checkpoint()
                await self.api("leasing_company", "PATCH", f"/api/v1/exchange/requests/{request_id}", body={"quantity": 3})
                changed = await self.event_after(checkpoint, "exchange.request_changed", request_id)
                self.remember_event("preference_changed", changed)
            await self.observe(changed, {"dealer": "skipped_preference", "distributor": "sent"}, exchange=True)
        finally:
            await self.api("dealer", "PUT", "/api/v1/email-preferences", body={"exchange_emails": True})
        try:
            await self.dealer_permissions(can_view=True, can_create=False)
            await self.api("dealer", "GET", dealer_detail + selector)
            checkpoint = await self.checkpoint()
            await self.api("dealer", "POST", "/api/v1/exchange/bids/" + selector, expected=403,
                body={"request_id": request_id, "price": "900000.00"})
            require(await self.checkpoint() == checkpoint, "Forbidden write unexpectedly created an outbox event")
            await self.dealer_permissions(can_view=False)
            await self.api("dealer", "GET", dealer_detail + selector, expected=403)
            changed = await self.saved_event("revoked_changed")
            if changed is None:
                checkpoint = await self.checkpoint()
                await self.api("leasing_company", "PATCH", f"/api/v1/exchange/requests/{request_id}", body={"quantity": 4})
                changed = await self.event_after(checkpoint, "exchange.request_changed", request_id)
                self.remember_event("revoked_changed", changed)
            await self.observe(changed, {"distributor": "sent"}, exchange=True)
        finally:
            await self.dealer_permissions(can_view=True)
        bid = await self.saved_event("bid_created")
        if bid is None:
            checkpoint = await self.checkpoint()
            await self.api("dealer", "POST", "/api/v1/exchange/bids/" + selector, expected=201,
                body={"request_id": request_id, "price": "900000.00"})
            bid = await self.event_after(checkpoint, "exchange.bid_created", request_id)
            self.remember_event("bid_created", bid)
        await self.observe(bid, {"leasing_company": "sent", "distributor": "sent"}, exchange=True)
        self.report["checks"].append({"rights": "secondary selector, unknown selector, read revoke, create revoke, distributor read-only",
            "preferences": "inbox preserved; email skipped then restored", "generic_action_links": list(ROLES)})
        self.report["completed_at"] = datetime.now(UTC).isoformat()
        self.report["result"] = "PASS"
        self.report["smtp_scope"] = "Mailpit accepted test-domain messages inside isolated Compose; no external email delivery"
        self.state["smoke_completed_at"] = self.report["completed_at"]
        write_json(self.directory / "fixtures.secret.json", self.state)
        write_json(self.directory / "smoke-report.json", self.report)
        browser_artifacts(self.directory, self.state)
        progress("smoke_pass", checks=len(self.report["checks"]), report="/runtime/smoke-report.json")


async def smoke(args: argparse.Namespace) -> None:
    directory, _ = guard_runtime(args)
    test = Smoke(args, directory, load_state(directory))
    try:
        await test.run()
    except Exception as exc:
        test.report.update(result="FAIL", error_type=type(exc).__name__, error=str(exc)[:2000])
        write_json(directory / "smoke-report.json", test.report)
        raise


async def regressions(args: argparse.Namespace) -> None:
    """Real HTTP contracts for the old gate fixes; no handler or DB assertions."""
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    case = Smoke(args, directory, state)
    created_ids = []
    for path in ("/api/v1/applications", "/api/v1/applications/draft"):
        payload = {"source_type": "platform", "company_id": state["companies"]["buyer"], "name": "ТЗ35 E2E editable",
            "vehicles": [{"vehicle_id": state["vehicle_id"], "quantity": 1, "custom_price": "1000000.00"}]}
        await case.api("client", "POST", path, expected=422, body=payload)
        headers = {"Idempotency-Key": str(uuid4())}
        created = await case.api("client", "POST", path, expected=201, body=payload, headers=headers)
        replayed = await case.api("client", "POST", path, body=payload, headers=headers)
        require(replayed == created, "Idempotency replay changed the exact JSON response")
        await case.api("client", "POST", path, expected=409, body={**payload, "name": "Conflicting name"}, headers=headers)
        created_ids.append(created["application_id"])
    app_id, foreign_id = created_ids
    detail = await case.api("client", "GET", f"/api/v1/applications/{app_id}")
    foreign = await case.api("client", "GET", f"/api/v1/applications/{foreign_id}")
    line_id = detail["items"][0]["id"]
    foreign_line_id = foreign["items"][0]["id"]
    update = {"line_id": line_id, "kind": "vehicle", "comment": "ТЗ35 verified comment", "regions": []}
    await case.api("client", "PUT", f"/api/v1/applications/{app_id}/items", body={"items": [update]})
    async def saved_comment() -> str:
        value = await case.api("client", "GET", f"/api/v1/applications/{app_id}")
        comment = next(item["comment"] for item in value["items"] if item["id"] == line_id)
        if not isinstance(comment, str):
            raise TypeError("Updated item comment is not a string")
        return comment
    require(await saved_comment() == "ТЗ35 verified comment", "Item update not visible through GET")
    await case.api("client", "PUT", f"/api/v1/applications/{app_id}/items", expected=422,
        body={"items": [{**update, "kind": "special_equipment"}]})
    await case.api("client", "PUT", f"/api/v1/applications/{app_id}/items", expected=404,
        body={"items": [{**update, "comment": "Must rollback"}, {**update, "line_id": foreign_line_id}]})
    require(await saved_comment() == "ТЗ35 verified comment", "Rejected mixed update partially changed an item")
    await case.api("leasing_company", "PUT", f"/api/v1/applications/{app_id}/items", expected=403,
        body={"items": [{**update, "comment": "Forbidden"}]})
    require(await saved_comment() == "ТЗ35 verified comment", "Forbidden update changed an item")
    state["editable_application_id"] = app_id
    write_json(directory / "fixtures.secret.json", state)
    write_json(directory / "http-regressions-report.json", {"result": "PASS",
        "checks": ["create and draft missing-key/replay/conflict", "item update/read",
            "wrong kind", "foreign line and atomic rollback", "unauthorized write"], "application_id": app_id})
    progress("http_regressions_pass", application_id=app_id)


async def dwh_regression(args: argparse.Namespace) -> None:
    """Kafka -> actual event-worker -> ClickHouse, including nullable batch."""
    directory, settings = guard_runtime(args)
    state = load_state(directory)
    from aiokafka import AIOKafkaProducer

    from infrastructure.clickhouse import get_clickhouse_client

    request_ids = [str(uuid4()), str(uuid4())]
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_brokers)
    await producer.start()
    try:
        for request_id, expiration in zip(request_ids, ("2099-09-08", None), strict=True):
            payload = {"request_id": request_id, "lc_user_id": state["users"]["leasing_company"]["id"],
                "vehicle_id": state["vehicle_id"], "quantity": 1, "expiration_date": expiration,
                "file_name": "2099-09-08", "updated_at": "2026-09-07T10:00:00+00:00", "_deleted": False}
            await producer.send_and_wait("exchange_request.changed.v1", json.dumps(payload).encode(), key=b"notifications35-date-regression")
    finally:
        await producer.stop()
    client = get_clickhouse_client()
    require(client is not None, "Isolated ClickHouse client unavailable")
    deadline = time.monotonic() + args.timeout
    rows = []
    while time.monotonic() < deadline:
        rows = client.query("SELECT toString(request_id), toString(expiration_date), file_name "
            "FROM dwh_exchange_requests FINAL WHERE request_id IN {ids:Array(UUID)}",
            parameters={"ids": request_ids}).result_rows
        if len(rows) == 2:
            break
        await asyncio.sleep(1)
    actual = {row[0]: row[1:] for row in rows}
    require(actual == {request_ids[0]: ("2099-09-08", "2099-09-08"), request_ids[1]: (None, "2099-09-08")},
        f"Kafka to ClickHouse typed date/null/string mismatch: {actual}")
    # Exercise the installed HTTP driver against real ClickHouse: DWH consumers
    # share this singleton across asyncio.to_thread reads and serialized writes.
    # A default shared session rejects overlapping queries before network I/O.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(6)
    def concurrent_read(_: int) -> bool:
        barrier.wait(timeout=10)
        return client.query("SELECT sleep(0.15), 42").result_rows == [(0, 42)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        require(all(pool.map(concurrent_read, range(6))), "Concurrent stateless ClickHouse reads failed")
    write_json(directory / "dwh-regression-report.json", {"result": "PASS", "request_ids": request_ids,
        "checks": ["ISO calendar date persisted", "NULL preserved", "String column unchanged", "six concurrent stateless HTTP queries"]})
    progress("dwh_regression_pass", rows=2, concurrent_queries=6)


async def outage_state(args: argparse.Namespace) -> None:
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    case = Smoke(args, directory, state)
    event = await case.event_after(0, "exchange.bid_updated", state["exchange_request_id"])
    event_id = str(event["event_id"])
    expected_status = "retry_wait" if args.mode == "outage-wait" else "sent"
    expected_attempts = 1 if args.mode == "outage-wait" else 2
    deadline = time.monotonic() + (75 if args.mode == "outage-wait" else 120)
    rows = []
    while time.monotonic() < deadline:
        rows = await case.query("SELECT user_id, status, attempt_count, message_id FROM notification_email_deliveries "
            "WHERE event_id=CAST(:id AS uuid) ORDER BY user_id", id=event_id)
        if len(rows) == 2 and all(row["status"] == expected_status and row["attempt_count"] == expected_attempts for row in rows):
            break
        await asyncio.sleep(1)
    require(len(rows) == 2 and all(row["status"] == expected_status and row["attempt_count"] == expected_attempts for row in rows),
        f"SMTP outage/recovery did not reach {expected_status}: {rows}")
    expected_users = {state["users"][role]["id"] for role in ("distributor", "leasing_company")}
    require({str(row["user_id"]) for row in rows} == expected_users, "Wrong outage recipients")
    for role in ("distributor", "leasing_company"):
        listed = await case.api(role, "GET", "/api/v1/notifications?limit=100")
        require(any(row["event_id"] == event_id for row in listed["notifications"]), "Inbox absent during SMTP outage")
    message_ids = sorted(row["message_id"] for row in rows)
    if args.mode == "outage-wait":
        write_json(directory / "smtp-outage-checkpoint.json", {"event_id": event_id, "message_ids": message_ids})
    else:
        checkpoint = json.loads((directory / "smtp-outage-checkpoint.json").read_text())
        require(checkpoint == {"event_id": event_id, "message_ids": message_ids}, "SMTP retry replaced message identity")
        messages = await case.mail_messages()
        case.verify_mail_recipients(rows, messages)
        for message_id in message_ids:
            matching = [message for message in messages if message.get("MessageID", "").strip("<>") == message_id.strip("<>")]
            require(len(matching) == 1, "SMTP retry produced a duplicate or missing message")
        write_json(directory / "smtp-outage-report.json", {"result": "PASS", "event_id": event_id,
            "message_ids": message_ids, "inbox_available_during_outage": True, "attempt_count": 2,
            "automatic_scheduler_retry": True, "exactly_one_captured_message_per_delivery": True})
    progress(args.mode, result="PASS", recipients=2, expected_status=expected_status)


async def dlq_regression(args: argparse.Namespace) -> None:
    directory, settings = guard_runtime(args)
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

    consumer = AIOKafkaConsumer("notification.events.dlq.v1", bootstrap_servers=settings.kafka_brokers,
        group_id=f"notifications35-dlq-{uuid4()}", auto_offset_reset="earliest", enable_auto_commit=False)
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_brokers)
    await consumer.start()
    await producer.start()
    try:
        source = await producer.send_and_wait("notification.events.v1", b"notifications35-invalid-json-probe", key=uuid4().bytes)
        async with asyncio.timeout(30):
            async for record in consumer:
                body = json.loads(record.value)
                if (body.get("partition"), body.get("offset")) != (source.partition, source.offset):
                    continue
                require(body["source_topic"] == "notification.events.v1", "Wrong DLQ source topic")
                require(body["errors"] == [{"type": "json_invalid"}], "Wrong DLQ diagnostic")
                require(set(body) == {"source_topic", "partition", "offset", "correlation_id", "errors"}, "DLQ retained unexpected fields")
                require(b"notifications35-invalid-json-probe" not in record.value, "DLQ retained arbitrary raw input")
                write_json(directory / "dlq-regression-report.json", {"result": "PASS", "partition": source.partition, "offset": source.offset})
                progress("dlq_regression_pass")
                break
    finally:
        await producer.stop()
        await consumer.stop()


async def browser_permissions(args: argparse.Namespace) -> None:
    """Change only the deterministic synthetic dealer membership for UI E2E."""
    directory, _ = guard_runtime(args)
    state = load_state(directory)
    case = Smoke(args, directory, state)
    await case.dealer_permissions(can_view=True, can_create=args.mode == "dealer-write-restore")
    progress(args.mode, company_id=state["companies"]["dealer"], result="PASS")


async def first_preferences(args: argparse.Namespace) -> None:
    """Fresh synthetic actor, without a pre-created preferences row or memberships."""
    directory, settings = guard_runtime(args)
    load_state(directory)
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.email_preferences import EmailPreferences
    from infrastructure.models.users import User, UserSession

    actor_path = directory / "first-preferences.secret.json"
    async with AsyncSessionLocal() as session:
        if args.mode == "first-preferences-cleanup":
            if not actor_path.exists():
                return
            actor = json.loads(actor_path.read_text())
            user_id = UUID(actor["id"])
            require(actor.get("marker") == MARKER and actor["email"] == f"first-settings-{user_id.hex}@notifications35.test",
                "Unexpected first-preferences fixture")
            user = await session.get(User, user_id)
            if user is None:
                # The identity file precedes commit; an interrupted preparation
                # can leave no persisted actor and therefore nothing to revoke.
                return
            require(user.email == actor["email"] and user.phone == actor["phone"]
                and user.role == "client" and user.company_id is None, "First-preferences actor changed ownership")
            user.is_active = False
            await session.commit()
            progress("first_preferences_deactivated")
            return
        user_id, session_id = uuid4(), uuid4()
        user = User(id=user_id, phone=f"+7{user_id.int % 10**10:010d}",
            name="ТЗ35 first email settings", email=f"first-settings-{user_id.hex}@notifications35.test",
            role="client", is_active=True, email_verified=True, phone_verified=True)
        session.add(user)
        await session.flush()
        require(await session.get(EmailPreferences, user_id) is None, "Fresh actor unexpectedly has preferences")
        now = datetime.now(UTC)
        access, refresh = generate_tokens(user_id, "client", None, refresh_session_id=session_id)
        refresh_expiry = now + timedelta(days=settings.refresh_token_expiry_days)
        session.add(UserSession(id=session_id, user_id=user_id, refresh_token_hash=hash_refresh_token(refresh),
            expires_at=refresh_expiry, ip_address="127.0.0.1", user_agent="ТЗ35 first-settings E2E"))
        actor = {"marker": MARKER, "id": str(user_id), "email": user.email, "phone": user.phone,
            "access_token": access, "refresh_token": refresh,
            "access_token_expires": (now + timedelta(minutes=settings.access_token_expiry_minutes)).timestamp(),
            "refresh_token_expires": refresh_expiry.timestamp()}
        # Persist cleanup identity before commit so interrupted runs remain scoped.
        write_json(actor_path, actor)
        await session.commit()
    write_json(directory / "browser-first-preferences.secret.json", browser_state(actor))
    progress("first_preferences_ready", preferences_rows=0)


def bootstrap(args: argparse.Namespace) -> None:
    require(args.execute, "Starting the localhost bootstrap requires explicit --execute")
    directory = state_directory(args)
    require(directory == HOST_DIR.resolve(), "Cookie bootstrap must run on the host, not inside Docker")
    state = load_state(directory)
    require(all(value["access_token_expires"] > time.time() for value in state["users"].values()), "Run auth inside the container to renew expired fixture cookies")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_values: object) -> None:
            return

        def do_GET(self) -> None:
            if self.headers.get("Host") not in {"localhost:18050", "127.0.0.1:18050"}:
                self.send_error(403)
                return
            match = re.fullmatch(r"/login/([a-z_]+)", self.path)
            if not match or match[1] not in ROLES:
                self.send_error(404)
                return
            # Reread to support cookie renewal without restarting the bootstrap.
            current = load_state(directory)["users"][match[1]]
            if current["access_token_expires"] <= time.time():
                self.send_error(409, "Fixture cookie expired; renew auth inside the isolated container")
                return
            self.send_response(303)
            self.send_header("Location", "http://localhost:18048/notifications")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Length", "0")
            for name, key in (("accessToken", "access_token"), ("refreshToken", "refresh_token")):
                cookie = SimpleCookie()
                cookie[name] = current[key]
                cookie[name]["path"] = "/"
                cookie[name]["httponly"] = True
                cookie[name]["samesite"] = "Lax"
                cookie[name]["max-age"] = int(current[f"{key}_expires"] - time.time())
                self.send_header("Set-Cookie", cookie[name].OutputString())
            self.end_headers()

    progress("bootstrap_listening", host="127.0.0.1", port=18050, roles=list(ROLES), tokens="never printed or put into URLs")
    ThreadingHTTPServer(("127.0.0.1", 18050), Handler).serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "seed", "prepare", "new-scenario", "smoke", "auth", "regressions", "dwh", "dlq",
        "outage-wait", "outage-recovered", "dealer-readonly", "dealer-write-restore",
        "first-preferences-prepare", "first-preferences-cleanup", "bootstrap"), nargs="?", default="plan")
    parser.add_argument("--execute", action="store_true", help="Root confirms isolated runtime health and authorizes this mode")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted fixture observations without repeating saved business events")
    parser.add_argument("--state-dir", default="/runtime")
    parser.add_argument("--backend-path", default="/app")
    parser.add_argument("--api-url", default="http://nginx")
    parser.add_argument("--smtp-api-url", default="http://smtp:8025")
    parser.add_argument("--metrics-url", default="http://event-worker:8000/metrics")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    if args.mode == "plan":
        progress("plan", network_io=False, database_io=False, repository_changes=False,
            execution_order=["seed --execute", "smoke --execute", "bootstrap --execute --state-dir /tmp/carcraft-notifications35-followup-v2-runtime"],
            roles=list(ROLES), database="notifications35_runtime", api="http://nginx", browser="http://localhost:18048",
            smtp_sink="http://smtp:8025", auth="ES256 runtime key + persisted refresh sessions; HttpOnly localhost cookies; no OTP/SMS",
            checks=["public API -> DB outbox -> Kafka -> event-worker -> HTTP inbox -> Taskiq -> Mailpit",
                "Kafka replay consumed twice, no duplicate inbox/email", "email preferences preserve inbox", "fresh read/write permissions and secondary company action URLs"])
    elif args.mode == "bootstrap":
        bootstrap(args)
    else:
        asyncio.run({"seed": seed, "prepare": prepare, "smoke": smoke, "auth": renew_auth, "new-scenario": new_scenario,
            "regressions": regressions, "dwh": dwh_regression, "dlq": dlq_regression,
            "outage-wait": outage_state, "outage-recovered": outage_state,
            "first-preferences-prepare": first_preferences, "first-preferences-cleanup": first_preferences,
            "dealer-readonly": browser_permissions, "dealer-write-restore": browser_permissions}[args.mode](args))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        progress("stopped")
    except Exception as error:
        progress("failed", error_type=type(error).__name__, error=str(error)[:2000])
        raise SystemExit(1) from None
