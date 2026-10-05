"""Real HTTP/S3/Kafka checks in the isolated task 22296 Docker stack."""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4, uuid5

ROOT = Path("/runtime")
FIXTURE_TARGETS = {
    "documentregistry22296": {"bucket": "documentregistry22296", "host_root": "/tmp/carcraft-22296-e2e"},
    "documentregistry22296_followup": {"bucket": "documentregistry22296-followup", "host_root": "/tmp/carcraft-22296-e2e-followup"},
}
MARKER = "document-registry-22296"


def identifier(name: str) -> UUID:
    return uuid5(UUID("a2222296-0000-4000-8000-000000000001"), name)


def require(condition: object, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def progress(stage: str, **values: object) -> None:
    print(json.dumps({"stage": stage, **values}, ensure_ascii=False, default=str), flush=True)


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    path.chmod(0o600)


def fixture_target(settings):
    target = FIXTURE_TARGETS.get(settings.db_name)
    require(settings.db_host == "postgres" and target is not None, "Refusing non-fixture DB")
    require(settings.s3_bucket == target["bucket"], "Refusing database/bucket mismatch")
    return {"database": settings.db_name, **target}


def guard():
    from infrastructure.settings import settings
    target = fixture_target(settings)
    marker = ROOT / "fixture-target.json"
    if marker.exists():
        require(json.loads(marker.read_text()) == target, "Refusing mismatched runtime directory")
    else:
        require(settings.db_name == "documentregistry22296", "Initialize the separate fixture runtime first")
    require(settings.jwt_keys_dir == "/runtime/jwt", "Refusing non-fixture JWT keys")
    require(Path.cwd() == ROOT and not (ROOT / ".env").exists(), "Refusing project dotenv")
    require(not settings.dadata_api_key and not settings.smsc_login and not settings.smtp_host, "Refusing external credentials")
    require(settings.s3_endpoint == "http://minio:9000", "Refusing external S3")
    return settings


def keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from infrastructure.settings import settings
    target = fixture_target(settings)
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = ROOT / "fixture-target.json"
    if marker.exists():
        require(json.loads(marker.read_text()) == target, "Refusing to reuse another fixture runtime")
    else:
        require(not (ROOT / "state.secret.json").exists(), "Refusing to relabel an existing fixture runtime")
        private_json(marker, target)
    directory = ROOT / "jwt"
    directory.mkdir(exist_ok=True, mode=0o700)
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
        headers = {"Origin": "http://localhost:18296"}
        if actor:
            headers["X-CSRF-Token"] = actor["csrf"]
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(base_url="http://backend:3002", trust_env=False, cookies=cookies, headers=headers, timeout=60) as client:
            response = await client.request(method, path, **kwargs)
        allowed = (expected,) if isinstance(expected, int) else expected
        require(response.status_code in allowed, f"{role} {method} {path}: HTTP {response.status_code}; {response.text[:1200]}")
        return response if raw else (response.json() if response.content else None)


def pdf(label="Document registry E2E 22296"):
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(60, 800, label)
    document.showPage()
    document.save()
    return buffer.getvalue()


async def seed():
    settings = guard()
    import aioboto3
    from infrastructure.auth import generate_tokens, hash_refresh_token
    from infrastructure.crypto.key_configuration import load_and_validate_key_configuration
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.companies import Company, LeasingCompany
    from infrastructure.models.users import User, UserCompany, UserSession
    from infrastructure.models.special_equipment import SpecialEquipmentMark, SpecialEquipmentModel
    load_and_validate_key_configuration()
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key_id, aws_secret_access_key=settings.s3_secret_access_key) as s3:
        buckets = await s3.list_buckets()
        if not any(b["Name"] == settings.s3_bucket for b in buckets["Buckets"]):
            await s3.create_bucket(Bucket=settings.s3_bucket)
    state_path = ROOT / "state.secret.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        require(state.get("database", "documentregistry22296") == settings.db_name, "Refusing state from another database")
        # Every run needs fresh signed sessions; browser-cookie expiry alone
        # cannot extend the JWT inside yesterday's saved fixture.
        async with AsyncSessionLocal() as session:
            for alias, actor in state["users"].items():
                user = await session.get(User, UUID(actor["id"]))
                require(user is not None and user.is_active and user.name == "22296 " + alias, "Fixture user changed unexpectedly")
                sid = uuid4()
                access, refresh = generate_tokens(user.id, user.role, user.company_id, refresh_session_id=sid)
                session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh), expires_at=datetime.now(UTC)+timedelta(days=1), ip_address="127.0.0.1", user_agent=MARKER))
                actor.update(access_token=access, refresh_token=refresh, csrf=secrets.token_urlsafe(24))
            await session.commit()
        private_json(state_path, state)
    else:
        state = {"marker": MARKER, "database": settings.db_name, "users": {}, "companies": {}}
        async with AsyncSessionLocal() as session:
            require(await session.get(Company, identifier("company/dealer")) is None, "Partial fixture requires investigation")
            companies = {}
            entries = [("leasing", "leasing_company"), ("leasing2", "leasing_company"), ("dealer", "dealer"), ("dealer2", "dealer"), ("distributor", "distributor"), ("client", "other")]
            for index, (alias, role) in enumerate(entries, 1):
                company = Company(id=identifier("company/" + alias), name="22296 " + alias, inn=f"000022296{index}", company_type=role, is_active=True)
                session.add(company)
                companies[alias] = company
                state["companies"][alias] = {"company_id": str(company.id), "name": company.name}
            await session.flush()
            for alias in ("leasing", "leasing2"):
                lc = LeasingCompany(id=identifier("lc/"+alias), company_id=companies[alias].id, is_active=True)
                session.add(lc)
                state["companies"][alias]["leasing_company_id"] = str(lc.id)
            mark = SpecialEquipmentMark(id=identifier("mark"), code="e2e22296", name="22296 Марка", slug="e2e22296")
            session.add(mark)
            await session.flush()
            model = SpecialEquipmentModel(id=identifier("model"), mark_id=mark.id, code="e2e22296-model", name="22296 Модель", slug="e2e22296-model")
            session.add(model)
            state["catalog"] = {"mark_id": str(mark.id), "model_id": str(model.id), "brand": mark.name, "model": model.name}
            roles = [("admin", "carcraft_employee", None), ("admin2", "carcraft_employee", None), ("dealer", "dealer", "dealer"), ("outsider", "dealer", "dealer2"), ("leasing", "leasing_company", "leasing"), ("leasing2", "leasing_company", "leasing2"), ("distributor", "distributor", "distributor"), ("client", "client", "client")]
            for index, (alias, role, company_alias) in enumerate(roles, 1):
                company_id = companies[company_alias].id if company_alias else None
                user = User(id=identifier("user/"+alias), name="22296 " + alias, phone=f"+700022296{index:02}", email=alias+"@documentregistry22296.test", role=role, company_id=company_id, is_active=True, phone_verified=True, email_verified=True)
                session.add(user)
                await session.flush()
                if company_id:
                    session.add(UserCompany(user_id=user.id, company_id=company_id, sub_role="administrator", can_view_applications=True, can_create_applications=True))
                sid = uuid4()
                access, refresh = generate_tokens(user.id, role, company_id, refresh_session_id=sid)
                session.add(UserSession(id=sid, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh), expires_at=datetime.now(UTC)+timedelta(days=1), ip_address="127.0.0.1", user_agent=MARKER))
                state["users"][alias] = {"id": str(user.id), "role": role, "company_id": str(company_id) if company_id else None, "access_token": access, "refresh_token": refresh, "csrf": secrets.token_urlsafe(24)}
            await session.commit()
        private_json(state_path, state)
    host_root = Path(FIXTURE_TARGETS[settings.db_name]["host_root"])
    storages = {}
    for alias, user in state["users"].items():
        cookies = [{"name": key, "value": value, "domain": "localhost", "path": "/", "expires": time.time()+86400, "httpOnly": http, "secure": False, "sameSite": "Lax"} for key, value, http in [("accessToken", user["access_token"], True), ("refreshToken", user["refresh_token"], True), ("csrfToken", user["csrf"], False)]]
        filename = alias + ".storage.json"
        private_json(ROOT/filename, {"cookies": cookies, "origins": []})
        storages[alias] = str(host_root/filename)
    private_json(ROOT/"manifest.json", {"marker": MARKER, "database": settings.db_name, "base_url": "http://localhost:18296", "storage_states": storages, "companies": state["companies"], "catalog": state["catalog"]})
    progress("fixture_manifest_ready", path=str(host_root/"manifest.json"))


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
        from registry import verify
        asyncio.run(verify())
