#!/usr/bin/env python3
"""22242 §11: real HTTP/PostgreSQL/S3 settings transfer acceptance, no unit suite.

Mount beside runtime.py at /e2e; /runtime maps to /tmp/carcraft-22242-runtime.
Run seed --execute using the current API, then verify --execute once the new routes are ready. Seed also
writes storefront-settings-browser-{update,copy,invalid}.json for Chrome.
Verify must precede Chrome mutations: full export round-trip includes the
default storefront and the three dedicated synthetic storefronts, and refuses
to run if any other storefront is present. No Docker or worker/fault controls.
validate resumes only the malformed tail from hidden-home after the coordinator
has confirmed the preceding phases passed; it never repeats seed/copy/import.
concurrency separately probes both role-writer/import lock orders after the
coordinator builds the fix. It restores the source fixture's exact override.
legacy checks obsolete persisted visibility keys without migrating rows; only
source/browser role overrides are temporarily replaced and restored exactly.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import copy
import hashlib
import json
import logging
import os
import time
from io import BytesIO
from pathlib import Path
from uuid import UUID

import runtime as rt

BASE = "/api/v1/admin/storefronts"
TRANSFER = BASE + "/settings"
SLUGS = {name: f"t22242-settings-{name}" for name in ("source", "untouched", "browser", "copy", "browser-copy")}
MANIFEST = Path("/runtime/storefront-settings-state.json")
FIELDS = {"is_active", "contact_email", "contact_phone", "public_ui", "appearance", "section_visibility", "logo"}
INVALID = (400, 422)


def ident(name: str) -> UUID:
    return rt.identifier("storefront-settings/" + name)


def encode(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode()


def write_artifact(name: str, data: bytes, *, exclusive: bool = True) -> None:
    rt.require(name.startswith("storefront-settings-") and "/" not in name, "Unexpected runtime artifact name")
    fd = os.open(Path("/runtime") / name, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW |
                 (os.O_EXCL if exclusive else os.O_TRUNC), 0o600)
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        output.write(data)


def save(state: dict, *, exclusive: bool = False) -> None:
    write_artifact(MANIFEST.name, encode(state), exclusive=exclusive)


def load() -> dict:
    fd = os.open(MANIFEST, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as source:
        state = json.load(source)
    rt.require(state.get("marker") == "task22242-storefront-settings" and state.get("ready"), "Wrong/incomplete settings fixtures")
    rt.require(state["ids"] == {key: str(ident(key)) for key in ("source", "untouched", "browser")}, "Wrong settings fixture IDs")
    return state


def png(color=(35, 95, 170, 255)) -> bytes:
    from PIL import Image

    output = BytesIO()
    Image.new("RGBA", (184, 35), color).save(output, format="PNG")
    return output.getvalue()


def font() -> bytes:
    """Small real OpenType font, generated in memory; never a fake storage object."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder([".notdef", "space", "A"])
    builder.setupCharacterMap({32: "space", 65: "A"})
    glyphs = {}
    for name in (".notdef", "space", "A"):
        pen = TTGlyphPen(None)
        if name != "space":
            pen.moveTo((50, 0))
            pen.lineTo((300, 700))
            pen.lineTo((550, 0))
            pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(dict.fromkeys(glyphs, (600, 0)))
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Task22242 Acceptance", "styleName": "Regular",
                            "uniqueFontIdentifier": str(ident("font")), "fullName": "Task22242 Acceptance Regular",
                            "psName": "Task22242Acceptance-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    builder.setupPost()
    builder.setupMaxp()
    builder.font.flavor = "woff2"
    output = BytesIO()
    builder.font.save(output)
    return output.getvalue()


class API:
    def __init__(self, client, auth: dict, settings):
        self.client, self.auth, self.settings = client, auth, settings

    async def request(self, method: str, path: str, *, file: bytes | None = None,
                      data: dict | None = None, body: dict | None = None,
                      expected: tuple[int, ...] = (200,), role=rt.ADMIN):
        headers = {"Cookie": ""}
        if role is not None:
            user = self.auth["users"][role]
            rt.require(user["access_token_expires"] > time.time() + 30, "Run runtime.py auth --execute")
            headers["Cookie"] = "accessToken=" + user["access_token"]
            if self.settings.csrf_enabled:
                csrf = str(ident("csrf/" + role))
                headers["Cookie"] += f"; {self.settings.csrf_cookie_name}={csrf}"
                headers[self.settings.csrf_header_name] = csrf
        kwargs = {"headers": headers}
        if file is not None:
            kwargs.update(files={"file": ("task22242-settings.json", file, "application/json")}, data=data or {})
        elif body is not None:
            kwargs["json"] = body
        response = await self.client.request(method, path, **kwargs)
        rt.require(response.status_code in expected,
                   f"{method} {path} role={role}: expected {expected}, got {response.status_code}")
        return response

    async def export(self) -> tuple[dict, bytes]:
        response = await self.request("GET", TRANSFER + "/export")
        rt.require("application/json" in response.headers.get("content-type", ""), "Export MIME must be JSON")
        rt.require("attachment" in response.headers.get("content-disposition", "").lower(), "Export must be a download")
        value = response.json()
        rt.require(isinstance(value, dict) and "/" in value and value["/"]["is_active"] is True, "Missing/default storefront export contract")
        for block in value.values():
            rt.require(set(block) == FIELDS, "Export contains omitted/unknown fields")
            rt.require(set(block["appearance"]) == {"colors", "border_radius", "color_overrides"}, "Export leaked font or effective appearance")
            rt.require(set(block["section_visibility"]) <= {"public", "dealer", "distributor", "leasing_company"}, "Export leaked global admin scope")
            if block["logo"] is not None:
                rt.require(set(block["logo"]) == {"content_type", "data_base64"}, "Logo must be self-contained original bytes")
                base64.b64decode(block["logo"]["data_base64"], validate=True)
        return value, response.content

    async def preview(self, file: bytes, actions: dict[str, str]) -> str:
        result = (await self.request("POST", TRANSFER + "/preview", file=file)).json()
        rt.require({row["slug"]: row["action"] for row in result["items"]} == actions
                   and len(result["items"]) == len(actions), "Unexpected preview items/actions")
        for row in result["items"]:
            rt.require(isinstance(row["warnings"], list) and all(isinstance(item, str) for item in row["warnings"]), "Invalid warnings contract")
            if row["action"] == "create":
                rt.require(row["warnings"], "New storefront needs empty warehouse/disabled warning")
        rt.require(isinstance(result["preview_token"], str) and result["preview_token"], "Missing preview token")
        return result["preview_token"]

    async def apply(self, file: bytes, token: str, *, created=(), updated=(), expected=(200,)):
        response = await self.request("POST", TRANSFER + "/import", file=file,
                                      data={"preview_token": token, "confirmed": "true"}, expected=expected)
        if response.status_code == 200:
            result = response.json()
            rt.require(sorted(result["created"]) == sorted(created) and sorted(result["updated"]) == sorted(updated), "Wrong applied slug lists")
        return response


async def snapshot(settings) -> dict:
    """Capture DB rows and real S3 objects under storefront-only prefixes."""
    import aioboto3
    from botocore.config import Config
    from sqlalchemy import func, select, table, text

    from infrastructure.database import AsyncSessionLocal

    result = {}
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        for name in ("catalog_storefronts", "catalog_storefront_warehouses", "catalog_storefront_fonts", "section_visibility"):
            relation = table(name).alias("t")
            values = (await session.execute(select(func.to_jsonb(relation.table_valued())))).scalars().all()
            result[name] = sorted(values, key=lambda row: json.dumps(row, sort_keys=True))
    result["objects"] = {}
    async with aioboto3.Session().client("s3", endpoint_url=settings.s3_endpoint, region_name=settings.s3_region,
                                       aws_access_key_id=settings.s3_access_key_id,
                                       aws_secret_access_key=settings.s3_secret_access_key,
                                       config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 0})) as s3:
        for prefix in ("storefronts/", "storefront-fonts/"):
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=prefix):
                for item in page.get("Contents", []):
                    obj = await s3.get_object(Bucket=settings.s3_bucket, Key=item["Key"])
                    data = await obj["Body"].read()
                    result["objects"][item["Key"]] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                    rt.require(len(result["objects"]) <= 200, "Unexpectedly large storefront fixture namespace")
    return result


def store_row(snap: dict, slug: str) -> dict:
    values = [row for row in snap["catalog_storefronts"] if (row["slug"] or "/") == slug]
    rt.require(len(values) == 1, "Expected unique storefront: " + slug)
    return values[0]


def preserved(before: dict, after: dict, omitted: list[str]) -> None:
    rt.require(before["catalog_storefront_warehouses"] == after["catalog_storefront_warehouses"], "Import changed warehouse bindings")
    rt.require(before["catalog_storefront_fonts"] == after["catalog_storefront_fonts"], "Import changed font catalog")
    for row in before["catalog_storefronts"]:
        current = store_row(after, row["slug"] or "/")
        rt.require(current["id"] == row["id"] and current["font_id"] == row["font_id"], "Import changed existing identity/font")
    for slug in omitted:
        previous = store_row(before, slug)
        rt.require(store_row(after, slug) == previous, "Omitted storefront changed: " + slug)
        rt.require([r for r in before["section_visibility"] if r["storefront_id"] == previous["id"]]
                   == [r for r in after["section_visibility"] if r["storefront_id"] == previous["id"]], "Omitted visibility changed")
    rt.require([r for r in before["section_visibility"] if r["storefront_id"] is None]
               == [r for r in after["section_visibility"] if r["storefront_id"] is None], "Global admin visibility changed")
    for key, value in before["objects"].items():
        if key.startswith("storefront-fonts/"):
            rt.require(after["objects"].get(key) == value, "Font file changed")


async def seed(api: API, settings) -> None:
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.section_visibility import SectionVisibility
    from infrastructure.models.storefronts import Storefront, StorefrontFont, StorefrontWarehouse
    from infrastructure.models.vehicles import Warehouse
    from infrastructure.services.object_storage import get_object_storage

    existing = (await api.request("GET", BASE)).json()["items"]
    rt.require(len(existing) == 1 and existing[0]["is_default"] is True,
               "Preparatory seed requires only the existing default storefront")
    state = {"marker": "task22242-storefront-settings", "ready": False,
             "ids": {key: str(ident(key)) for key in ("source", "untouched", "browser")}}
    save(state, exclusive=True)
    storage = get_object_storage()
    font_data = font()
    font_key = f"storefront-fonts/{ident('font')}/font.woff2"
    rt.require(not await storage.exists(font_key), "Fixture font already exists")
    await storage.put(font_key, font_data, "font/woff2")
    logo_keys = {}
    for name in state["ids"]:
        key = f"storefronts/{ident(name)}/task22242-original.png"
        rt.require(not await storage.exists(key), "Fixture logo already exists")
        await storage.put(key, png(), "image/png")
        logo_keys[name] = key
    async with AsyncSessionLocal() as session, session.begin():
        await rt.insert(session, StorefrontFont, id=ident("font"), name="22242 Settings Acceptance",
                        original_filename="task22242.woff2", storage_key=font_key, content_type="font/woff2",
                        size_bytes=len(font_data), checksum_sha256=hashlib.sha256(font_data).hexdigest(),
                        created_by=rt.identifier("user/" + rt.ADMIN))
        for name in state["ids"]:
            await rt.insert(session, Warehouse, id=ident("warehouse/" + name), brand="22242 settings",
                            address="22242 settings " + name, company_id=rt.identifier("company/dealer"),
                            dealer_id=rt.identifier("company/dealer"), status="active")
            await rt.insert(session, Storefront, id=ident(name), slug=SLUGS[name], is_default=False,
                            is_active=name != "untouched", font_id=ident("font"), version=1,
                            logo_storage_key=logo_keys[name], logo_content_type="image/png",
                            contact_email=f"{name}@task22242.test", contact_phone="+7 (900) 222-42-42",
                            appearance_primary_color="#245A91", appearance_border_radius="large")
            await rt.insert(session, StorefrontWarehouse, storefront_id=ident(name), warehouse_id=ident("warehouse/" + name))
            for scope, section in (("public", "about"), ("dealer", "reports"),
                                   ("distributor", "support"), ("leasing_company", "documents")):
                await rt.insert(session, SectionVisibility, id=ident(f"visibility/{name}/{scope}"),
                                storefront_id=ident(name), scope=scope, section_key=section, is_visible=False)
    # Prepare Chrome input using the existing admin API. The new transfer
    # endpoints need not exist yet, and inherited/effective fields are excluded.
    items = (await api.request("GET", BASE)).json()["items"]
    browser_row = next(row for row in items if row["slug"] == SLUGS["browser"])
    browser = {key: copy.deepcopy(browser_row[key]) for key in ("is_active", "contact_email", "contact_phone", "public_ui")}
    browser["appearance"] = {key: copy.deepcopy(browser_row["appearance"][key])
                             for key in ("colors", "border_radius", "color_overrides")}
    browser["section_visibility"] = {"public": {"about": False}, "dealer": {"reports": False},
                                      "distributor": {"support": False}, "leasing_company": {"documents": False}}
    browser["logo"] = {"content_type": "image/png", "data_base64": base64.b64encode(png()).decode()}
    browser["contact_email"] = "browser-imported@task22242.test"
    browser["appearance"]["colors"]["primary"] = "#7C3AED"
    write_artifact("storefront-settings-browser-update.json", encode({SLUGS["browser"]: browser}))
    write_artifact("storefront-settings-browser-copy.json", encode({SLUGS["browser-copy"]: browser}))
    browser["warehouse_ids"] = [str(ident("warehouse/browser"))]
    write_artifact("storefront-settings-browser-invalid.json", encode({SLUGS["browser"]: browser}))
    state.update(ready=True, original_logo_sha256=hashlib.sha256(png()).hexdigest())
    save(state)
    rt.check("seed: 3 storefronts/warehouses, real custom WOFF2, PNG originals, four visibility scopes")
    rt.check("Chrome chooser files: /runtime/storefront-settings-browser-{update,copy,invalid}.json")


def state_slug_values() -> set[str]:
    return {SLUGS[key] for key in ("source", "untouched", "browser")}


async def commit_rollback(api: API, settings, block: dict) -> None:
    """Real deferred PostgreSQL constraint failure after immutable logo staging."""
    from sqlalchemy import text

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.services.object_storage import get_object_storage

    rollback_block = copy.deepcopy(block)
    marker = "rollback-22242@task22242.test"
    rollback_block["contact_email"] = marker
    rollback_block["logo"] = {"content_type": "image/png", "data_base64": base64.b64encode(png((10, 150, 90, 255))).decode()}
    new_slug = "t22242-settings-rollback-new"
    content = encode({SLUGS["source"]: rollback_block, new_slug: rollback_block})
    token = await api.preview(content, {SLUGS["source"]: "update", new_slug: "create"})
    before = await snapshot(settings)
    old_key = store_row(before, SLUGS["source"])["logo_storage_key"]
    storage = get_object_storage()
    old = await storage.get(old_key)
    rt.require(old is not None, "Rollback fixture requires a real published logo")
    rt.require(ident("source") == UUID("b60a7955-aa29-582e-a715-17f2dbeea719")
               and SLUGS["source"] == "t22242-settings-source"
               and marker == "rollback-22242@task22242.test", "Static COMMIT probe identity mismatch")
    installed = False
    try:
        async with AsyncSessionLocal() as session, session.begin():
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            # Sequence increments survive transaction rollback and prove this
            # exact deferred probe fired (a coincidental earlier 500 cannot pass).
            await session.execute(text("CREATE SEQUENCE public.task22242_storefront_settings_fail_commit_hits"))
            await session.execute(text("""
                CREATE FUNCTION public.task22242_storefront_settings_fail_commit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.id = 'b60a7955-aa29-582e-a715-17f2dbeea719'::uuid
                       AND NEW.slug = 't22242-settings-source'
                       AND NEW.contact_email = 'rollback-22242@task22242.test' THEN
                        PERFORM nextval('public.task22242_storefront_settings_fail_commit_hits');
                        RAISE EXCEPTION 'task22242 settings injected commit failure' USING ERRCODE = 'P0001';
                    END IF;
                    RETURN NEW;
                END $$
            """))
            await session.execute(text("""
                CREATE CONSTRAINT TRIGGER task22242_storefront_settings_fail_commit
                AFTER INSERT OR UPDATE ON catalog_storefronts
                DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
                EXECUTE FUNCTION public.task22242_storefront_settings_fail_commit()
            """))
        installed = True
        await api.apply(content, token, expected=(500,))
        async with AsyncSessionLocal() as session:
            fired = (await session.execute(text(
                "SELECT is_called FROM public.task22242_storefront_settings_fail_commit_hits"
            ))).scalar_one()
        rt.require(fired is True, "HTTP 500 occurred before the deferred COMMIT probe; inspect backend logs")
        after = await snapshot(settings)
        for table in ("catalog_storefronts", "catalog_storefront_warehouses", "catalog_storefront_fonts", "section_visibility"):
            rt.require(after[table] == before[table], "COMMIT rollback left partial rows: " + table)
        for key, value in before["objects"].items():
            rt.require(after["objects"].get(key) == value, "COMMIT rollback replaced/deleted an existing object")
        current = await storage.get(old_key)
        rt.require(current is not None and current.data == old.data, "COMMIT rollback altered published logo bytes")
        # Failed staging can leave an unreferenced immutable object; §11 requires
        # old references/bytes to survive, not a global object-store transaction.
        print(f"PASS COMMIT rollback: all rows/old logo bytes intact; unreferenced staged objects={len(set(after['objects']) - set(before['objects']))}", flush=True)
    finally:
        if installed:
            async with AsyncSessionLocal() as session, session.begin():
                await session.execute(text("SET LOCAL lock_timeout = '5s'"))
                await session.execute(text("DROP TRIGGER task22242_storefront_settings_fail_commit ON catalog_storefronts"))
                await session.execute(text("DROP FUNCTION public.task22242_storefront_settings_fail_commit()"))
                await session.execute(text("DROP SEQUENCE public.task22242_storefront_settings_fail_commit_hits"))


async def verify(api: API, settings) -> None:
    state = load()
    rt.require(not state.get("verification_started"), "Verification already started; inspect receipts before replay")
    exported, raw = await api.export()
    rt.require(set(exported) == {"/", *state_slug_values()}, "Unexpected storefronts: do not mutate unrelated fixtures")
    exported_again, raw_again = await api.export()
    rt.require(raw == raw_again and exported == exported_again and b"\n" in raw, "Export must be stable and human readable")
    write_artifact("storefront-settings-export.json", raw, exclusive=False)
    rt.require(exported[SLUGS["untouched"]]["is_active"] is False, "Disabled storefront omitted/changed")
    for key in state_slug_values():
        rt.require(base64.b64decode(exported[key]["logo"]["data_base64"], validate=True) == png(), "Export changed original PNG bytes")
    before = await snapshot(settings)
    token = await api.preview(raw, dict.fromkeys(exported, "update"))
    rt.require(await snapshot(settings) == before, "Preview changed DB/S3")
    for role in (None, *rt.ROLES[1:]):
        expected = (401,) if role is None else (403,)
        await api.request("GET", TRANSFER + "/export", role=role, expected=expected)
        await api.request("POST", TRANSFER + "/preview", file=raw, role=role, expected=expected)
        await api.request("POST", TRANSFER + "/import", file=raw,
                          data={"preview_token": token, "confirmed": "true"}, role=role, expected=expected)
    rt.require(await snapshot(settings) == before, "Denied access changed DB/S3")
    for data in ({"preview_token": token}, {"preview_token": token, "confirmed": "false"}, {"confirmed": "true"}):
        await api.request("POST", TRANSFER + "/import", file=raw, data=data, expected=(400, 409, 422))
    rt.require(await snapshot(settings) == before, "Missing confirmation/token changed DB/S3")
    state["verification_started"] = True
    save(state)
    await api.apply(raw, token, updated=exported)
    rt.require((await api.export())[0] == exported, "Full round-trip changed transferable values")
    preserved(before, await snapshot(settings), [])
    rt.check("export/all-storefront round-trip incl '/' and disabled; originals exact; font/warehouse/global scope preserved; all roles checked")

    changed = copy.deepcopy(exported[SLUGS["source"]])
    changed["contact_email"] = "changed@task22242.test"
    changed["appearance"]["colors"]["primary"] = "#7C3AED"
    changed["logo"] = {"content_type": "image/png", "data_base64": base64.b64encode(png((160, 60, 90, 255))).decode()}
    changed["section_visibility"]["dealer"]["reports"] = True
    payload = encode({SLUGS["source"]: changed})
    before = await snapshot(settings)
    token = await api.preview(payload, {SLUGS["source"]: "update"})
    rt.require(await snapshot(settings) == before, "Subset preview changed DB/S3")
    await api.apply(payload, token, updated=(SLUGS["source"],))
    after = await snapshot(settings)
    rt.require((await api.export())[0][SLUGS["source"]] == changed, "Subset import did not fully replace portable settings")
    preserved(before, after, ["/", SLUGS["untouched"], SLUGS["browser"]])
    rt.require(store_row(before, SLUGS["source"])["logo_storage_key"] != store_row(after, SLUGS["source"])["logo_storage_key"], "Logo was overwritten instead of using an immutable key")
    rt.check("subset update: only requested slug replaced, original ID/font/warehouses kept, omitted storefronts byte-for-byte unchanged")

    payload = encode({SLUGS["copy"]: changed})
    before = await snapshot(settings)
    token = await api.preview(payload, {SLUGS["copy"]: "create"})
    rt.require(await snapshot(settings) == before, "Copy preview mutated DB/S3")
    await api.apply(payload, token, created=(SLUGS["copy"],))
    after = await snapshot(settings)
    copied = store_row(after, SLUGS["copy"])
    rt.require(copied["is_active"] is False and copied["font_id"] is None, "New storefront must be disabled/system font")
    rt.require(not any(row["storefront_id"] == copied["id"] for row in after["catalog_storefront_warehouses"]), "Copy inherited warehouses")
    preserved(before, after, list(exported))
    copy_expected = {**changed, "is_active": False}
    rt.require((await api.export())[0][SLUGS["copy"]] == copy_expected, "Copy did not preserve portable values")
    await api.request("PATCH", BASE + "/" + copied["id"], body={"is_active": True}, expected=(422,))
    await api.request("POST", BASE, body={"slug": "t22242-settings-no-warehouse", "warehouse_ids": []}, expected=INVALID)
    rt.require(await snapshot(settings) == after, "Ordinary activation/create bypassed warehouse requirement")
    await api.request("PATCH", BASE + "/" + copied["id"], body={"warehouse_ids": [str(ident("warehouse/source"))]})
    await api.request("PATCH", BASE + "/" + copied["id"], body={"is_active": True})
    activated = store_row(await snapshot(settings), SLUGS["copy"])
    rt.require(activated["is_active"] is True and activated["font_id"] is None, "Copy failed activation after binding warehouse")
    rt.check("copied slug: create warning, disabled/empty/system font; activation 422 until bound, then 200")

    payload = encode({SLUGS["source"]: changed})
    token = await api.preview(payload, {SLUGS["source"]: "update"})
    before = await snapshot(settings)
    tampered = copy.deepcopy(changed)
    tampered["contact_email"] = "tampered@task22242.test"
    await api.apply(encode({SLUGS["source"]: tampered}), token, expected=(409,))
    rt.require(await snapshot(settings) == before, "Changed-file stale import changed DB/S3")
    token = await api.preview(payload, {SLUGS["source"]: "update"})
    await api.request("PATCH", BASE + "/" + state["ids"]["source"], body={"contact_email": "concurrent@task22242.test"})
    before = await snapshot(settings)
    await api.apply(payload, token, expected=(409,))
    rt.require(await snapshot(settings) == before, "Stale settings import changed DB/S3/published logo")
    rt.check("stale previews: changed file and concurrent real PATCH -> 409, DB/S3 preserved")
    await commit_rollback(api, settings, changed)

    await validate_malformed(api, settings, state, exported, changed)


async def validate_malformed(api: API, settings, state: dict, exported: dict, changed: dict,
                             *, start_at: str | None = None) -> None:

    good = copy.deepcopy(changed)
    bad_cases = {
        "syntax": b'{"broken":', "empty": b"{}", "top-list": b"[]",
        "duplicate-slug": (b'{"' + SLUGS["source"].encode() + b'":' + encode(good) + b',"'
                           + SLUGS["source"].encode() + b'":' + encode(good) + b'}'),
        "NaN": b'{"bad":{"is_active":NaN}}', "Infinity": b'{"bad":{"is_active":Infinity}}',
    }
    for label, patch in (
        ("unknown-field", {"unknown": True}), ("warehouses", {"warehouse_ids": [str(ident("warehouse/source"))]}),
        ("uuid", {"id": state["ids"]["source"]}), ("font-top", {"font_id": str(ident("font"))}),
        ("type", {"is_active": "true"}), ("email", {"contact_email": "broken"}),
        ("phone", {"contact_phone": "hello"}),
        ("logo-url", {"logo": {"url": "http://127.0.0.1:9/task22242-no-fetch"}}),
        ("base64", {"logo": {"content_type": "image/png", "data_base64": "%%%"}}),
        ("mime", {"logo": {"content_type": "image/jpeg", "data_base64": base64.b64encode(png()).decode()}}),
    ):
        bad_cases[label] = encode({SLUGS["source"]: good, "t22242-settings-invalid": {**good, **patch}})
    for label, transform in (
        ("nested-font", lambda b: b["appearance"].update(font_id=str(ident("font")))),
        ("color", lambda b: b["appearance"]["colors"].update(primary="red")),
        ("unknown-visibility", lambda b: b["section_visibility"].update(public={"nonexistent": False})),
        ("global-admin", lambda b: b["section_visibility"].update(carcraft_employee={"special_equipment_import": True})),
        ("hidden-home", lambda b: (b["public_ui"].update(home_page_key="about"), b["section_visibility"].update(public={"about": False}))),
    ):
        bad = copy.deepcopy(good)
        transform(bad)
        bad_cases[label] = encode({SLUGS["source"]: good, "t22242-settings-invalid": bad})
    bad_cases["invalid-slug"] = encode({"Bad Slug": good})
    bad_cases["root-disabled"] = encode({"/": {**exported["/"], "is_active": False}})
    bad_cases["1001-items"] = encode({f"t22242-limit-{index}": good for index in range(1001)})
    bad_cases["logo-over-5MiB"] = encode({SLUGS["source"]: {**good, "logo": {
        "content_type": "image/png", "data_base64": base64.b64encode(png() + b" " * (5 * 1024 * 1024)).decode()}}})
    if start_at is not None:
        labels = list(bad_cases)
        rt.require(start_at in labels, "Unknown malformed validation checkpoint")
        bad_cases = {label: bad_cases[label] for label in labels[labels.index(start_at):]}
    fresh_token = await api.preview(encode({SLUGS["source"]: good}), {SLUGS["source"]: "update"})
    for label, content in bad_cases.items():
        before = await snapshot(settings)
        expected = (409,) if label in {"hidden-home", "root-disabled"} else (400, 413, 422)
        await api.request("POST", TRANSFER + "/preview", file=content, expected=expected)
        await api.request("POST", TRANSFER + "/import", file=content,
                          data={"preview_token": fresh_token, "confirmed": "true"}, expected=(400, 409, 413, 422))
        rt.require(await snapshot(settings) == before, "Malformed batch changed DB/S3: " + label)
        rt.check("atomic rejection: " + label)
    before = await snapshot(settings)
    valid_file = encode({SLUGS["source"]: good})
    oversized = valid_file + b" " * (20 * 1024 * 1024 + 1 - len(valid_file))
    await api.request("POST", TRANSFER + "/preview", file=oversized, expected=(400, 413, 422))
    rt.require(await snapshot(settings) == before, "Oversized file changed DB/S3")
    rt.check("atomic rejection: file-over-20MiB")
    state["verified"] = True
    if start_at is not None:
        state["validation_resumed_from"] = start_at
    save(state)
    rt.check("storefront JSON API/DB/S3 acceptance complete; Chrome fixture files remain available")


async def validate_remaining(api: API, settings) -> None:
    state = load()
    rt.require(state.get("verification_started") is True and not state.get("verified"),
               "validate requires the interrupted, uncompleted verification run")
    before = await snapshot(settings)
    expected_slugs = {"/", *state_slug_values(), SLUGS["copy"]}
    rt.require({row["slug"] or "/" for row in before["catalog_storefronts"]} == expected_slugs,
               "Resume fixture set changed; no mutation phases will be replayed")
    source = store_row(before, SLUGS["source"])
    copied = store_row(before, SLUGS["copy"])
    rt.require(source["id"] == state["ids"]["source"]
               and source["contact_email"] == "concurrent@task22242.test",
               "Resume requires the completed stale/rollback fixture state")
    rt.require(copied["is_active"] is True and copied["font_id"] is None
               and any(row["storefront_id"] == copied["id"]
                       and row["warehouse_id"] == str(ident("warehouse/source"))
                       for row in before["catalog_storefront_warehouses"]),
               "Resume requires the already-created/activated copy")
    exported, _ = await api.export()
    rt.require(await snapshot(settings) == before, "Resume export changed DB/S3")
    rt.check("resume preconditions: source unchanged after rollback; copy already active/bound; no extra storefronts")
    await validate_malformed(api, settings, state, exported, exported[SLUGS["source"]], start_at="hidden-home")


async def concurrency(api: API, settings) -> None:
    """Real handler/HTTP transactions; no sleeps used to infer lock ordering."""
    from sqlalchemy import delete, insert, select, text

    from application.commands.section_visibility import (
        SectionVisibilityUpdate,
        UpdateSectionVisibilityCommand,
        handle_update_section_visibility,
    )
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.section_visibility import SectionVisibility
    from infrastructure.models.storefronts import Storefront

    state = load()
    rt.require(state.get("verified") is True, "Concurrency requires completed baseline acceptance")
    source_id = ident("source")
    predicate = (SectionVisibility.storefront_id == source_id,
                 SectionVisibility.scope == "dealer", SectionVisibility.section_key == "reports")
    parent = select(Storefront.id).where(Storefront.id == source_id, Storefront.slug == SLUGS["source"]).with_for_update()
    async with AsyncSessionLocal() as session:
        original = dict((await session.execute(select(SectionVisibility.__table__).where(*predicate))).mappings().one())
    before = await snapshot(settings)
    rt.require(store_row(before, SLUGS["source"])["id"] == str(source_id), "Wrong concurrency fixture")
    exported, _ = await api.export()
    file = encode({SLUGS["source"]: exported[SLUGS["source"]]})
    token = await api.preview(file, {SLUGS["source"]: "update"})
    pending = None

    async def lock_wait(pid: int, operation: asyncio.Task, mode: str) -> int:
        # An observer connection proves the exact parent relation wait, not
        # merely that HTTP has not returned yet. Never print SQL or JWTs.
        async with asyncio.timeout(15):
            async with AsyncSessionLocal() as observer:
                while not operation.done():
                    rows = (await observer.execute(text("""
                        SELECT DISTINCT l.pid FROM pg_locks l
                        JOIN pg_stat_activity a ON a.pid = l.pid
                        WHERE a.datname = current_database()
                          AND :blocker = ANY(pg_blocking_pids(l.pid))
                          AND l.relation = 'catalog_storefronts'::regclass
                          AND NOT l.granted AND l.mode = :mode
                    """), {"blocker": pid, "mode": mode})).scalars().all()
                    await observer.rollback()
                    if rows:
                        rt.require(len(rows) == 1, "Ambiguous parent lock waiter; stop other storefront writes")
                        rt.check(f"concurrency observed pg_blocking_pids: {mode} waits for fixture gate")
                        return rows[0]
                    await asyncio.sleep(0.1)
                await asyncio.shield(operation)  # Preserve server completion for cleanup.
                raise rt.AcceptanceFailure("HTTP completed without the required parent lock wait")

    async def gate_settings(session) -> int:
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        await session.execute(text("SET LOCAL idle_in_transaction_session_timeout = '25s'"))
        return await session.scalar(text("SELECT pg_backend_pid()"))

    try:
        # Role writer wins: actual application command in a controlled session.
        async with AsyncSessionLocal() as writer:
            writer_pid = await gate_settings(writer)
            rt.require(await writer.scalar(parent) == source_id, "Missing source parent")
            await handle_update_section_visibility(UpdateSectionVisibilityCommand(
                scope="dealer", storefront_id=source_id,
                sections=(SectionVisibilityUpdate(key="reports", is_visible=not original["is_visible"]),),
                updated_by=UUID(api.auth["users"][rt.ADMIN]["id"]),
            ), writer)
            pending = asyncio.create_task(api.apply(file, token, expected=(409,)))
            await lock_wait(writer_pid, pending, "ExclusiveLock")
            await writer.commit()
        await asyncio.shield(pending)
        pending = None
        current, _ = await api.export()
        expected = copy.deepcopy(exported[SLUGS["source"]])
        expected["section_visibility"]["dealer"]["reports"] = not original["is_visible"]
        rt.require(current[SLUGS["source"]] == expected, "Stale import overwrote committed role visibility/settings")
        rt.check("concurrency role-first: committed override survives; waiting HTTP import returns 409")

        # Remove ONLY this override so the second role upsert must perform a
        # genuine INSERT/FK check, not an ON CONFLICT update of an existing row.
        async with AsyncSessionLocal() as session, session.begin():
            await gate_settings(session)
            rt.require(await session.scalar(parent) == source_id, "Missing source parent")
            await session.execute(delete(SectionVisibility).where(*predicate))
        async with AsyncSessionLocal() as gate:
            gate_pid = await gate_settings(gate)
            await gate.execute(text("LOCK TABLE catalog_storefronts IN EXCLUSIVE MODE"))
            pending = asyncio.create_task(api.request(
                "PATCH", f"{BASE}/{source_id}/section-visibility/dealer",
                body={"sections": [{"key": "reports", "is_visible": original["is_visible"]}]},
            ))
            waiter = await lock_wait(gate_pid, pending, "RowShareLock")
            async with AsyncSessionLocal() as observer:
                early_write = await observer.scalar(text("""
                    SELECT EXISTS (SELECT 1 FROM pg_locks
                        WHERE pid = :waiter AND relation = 'section_visibility'::regclass
                          AND granted AND mode = 'RowExclusiveLock')
                """), {"waiter": waiter})
            rt.require(not early_write, "Role INSERT locked visibility before parent: deadlock order remains")
            # Reproduce the rest of import's actual lock order while the role
            # request is waiting; the old ordering deadlocks at this point.
            await gate.execute(text("LOCK TABLE catalog_storefront_warehouses IN EXCLUSIVE MODE"))
            await gate.execute(text("LOCK TABLE section_visibility IN EXCLUSIVE MODE"))
            rt.require(not pending.done(), "Role request escaped held import locks")
            await gate.commit()
        await asyncio.shield(pending)
        pending = None
        async with AsyncSessionLocal() as session:
            inserted = (await session.execute(select(SectionVisibility.__table__).where(*predicate))).mappings().one()
            rt.require(inserted["id"] != original["id"] and inserted["is_visible"] == original["is_visible"],
                       "Role HTTP request did not commit a fresh visibility INSERT")
        rt.check("concurrency import-first: no early visibility write lock; fresh role INSERT commits via HTTP 200")
    finally:
        # Context managers release gate locks first. Let any in-flight HTTP
        # transaction finish before restoring; cancelling a client alone does
        # not cancel a server-side commit.
        if pending is not None:
            await asyncio.gather(pending, return_exceptions=True)
        async with AsyncSessionLocal() as session, session.begin():
            await gate_settings(session)
            rt.require(await session.scalar(parent) == source_id, "Cannot restore missing fixture parent")
            await session.execute(delete(SectionVisibility).where(*predicate))
            await session.execute(insert(SectionVisibility).values(**original))
        rt.check("concurrency cleanup: exact source/dealer/reports override restored")
    after = await snapshot(settings)
    rt.require({k: v for k, v in before.items() if k != "objects"}
               == {k: v for k, v in after.items() if k != "objects"}, "Concurrency changed persistent settings/other rows")
    rt.require(all(after["objects"].get(k) == v for k, v in before["objects"].items()),
               "Concurrency changed existing logo/font bytes")
    state["concurrency_verified"] = True
    save(state)
    rt.check("both real PostgreSQL lock orders passed; original DB rows and published S3 objects preserved")


async def legacy(api: API, settings) -> None:
    """Same real acceptance command must fail on the old image and pass on the fix."""
    from sqlalchemy import delete, insert, select, text

    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.section_visibility import SectionVisibility
    from infrastructure.models.storefronts import Storefront
    from infrastructure.repositories.section_visibility_repository import upsert_visibility_overrides

    state = load()
    names = ("source", "browser")
    scopes = ("dealer", "leasing_company", "distributor")
    ids = [ident(name) for name in names]
    predicate = (SectionVisibility.storefront_id.in_(ids), SectionVisibility.scope.in_(scopes))
    before = await snapshot(settings)
    for name in names:
        rt.require(store_row(before, SLUGS[name])["id"] == state["ids"][name], "Wrong legacy fixture")
    # Check cookie validity before any fixture mutation.
    await api.request("GET", BASE)
    original = None

    async def lock_fixtures(session) -> None:
        await session.execute(text("SET LOCAL lock_timeout = '5s'"))
        await session.execute(text("SET LOCAL statement_timeout = '10s'"))
        locked = (await session.execute(select(Storefront.id).where(
            Storefront.id.in_(ids), Storefront.slug.in_([SLUGS[name] for name in names]),
        ).order_by(Storefront.id).with_for_update())).scalars().all()
        rt.require(set(locked) == set(ids), "Missing legacy fixture parents")

    try:
        async with AsyncSessionLocal() as session, session.begin():
            await lock_fixtures(session)
            original = [dict(row) for row in (await session.execute(
                select(SectionVisibility.__table__).where(*predicate),
            )).mappings()]
            # Make each current-role map genuinely partial: only support=False.
            # The other entries are persisted legacy data, not valid import input.
            await session.execute(delete(SectionVisibility).where(*predicate))
            for name, value in (("source", False), ("browser", True)):
                for scope in scopes:
                    await upsert_visibility_overrides(
                        session, scope, {"support": False, "compensations": value,
                                         "task22242_obsolete": value},
                        UUID(api.auth["users"][rt.ADMIN]["id"]), storefront_id=ident(name),
                    )
        seeded = await snapshot(settings)
        rt.check("legacy fixtures: compensations False/True plus obsolete key across all three roles; support=False")
        response = await api.request("GET", TRANSFER + "/export", expected=(200, 409))
        rt.require(await snapshot(settings) == seeded, "Export modified legacy DB rows or S3")
        if response.status_code == 409:
            rt.require("compensations" in response.text, "Export 409 was not the expected legacy-key error")
            raise rt.AcceptanceFailure("RED reproduced: export HTTP 409 rejects persisted compensations; expected 200")
        exported = response.json()
        for name in names:
            for scope in scopes:
                rt.require(exported[SLUGS[name]]["section_visibility"][scope] == {"support": False},
                           "Export leaked obsolete keys, renamed one, lost False, or filled absent defaults")
        rt.check("export HTTP 200: legacy keys omitted; explicit support=False retained; no inferred/default entries")
        file = response.content
        await api.preview(file, {slug: "update" for slug in exported})
        for scope in scopes:
            for value in (False, True):
                invalid = copy.deepcopy(exported[SLUGS["source"]])
                invalid["section_visibility"][scope]["compensations"] = value
                await api.request("POST", TRANSFER + "/preview",
                                  file=encode({SLUGS["source"]: invalid}), expected=(422,))
        rt.require(await snapshot(settings) == seeded, "Export/preview mutated legacy DB rows or S3")
        rt.check("export preview HTTP 200; explicit compensations import preview stays strict HTTP 422 for all roles/values")
    finally:
        if original is not None:
            async with AsyncSessionLocal() as session, session.begin():
                await lock_fixtures(session)
                await session.execute(delete(SectionVisibility).where(*predicate))
                if original:
                    await session.execute(insert(SectionVisibility), original)
            rt.require(await snapshot(settings) == before, "Legacy cleanup did not restore exact DB/S3 snapshot")
            rt.check("legacy cleanup: exact original rows restored; other fixtures, root and S3 unchanged")


async def run(args) -> None:
    import httpx

    settings = rt.guard(args)
    auth = rt.load_state()
    async with httpx.AsyncClient(base_url=rt.API_URL, timeout=30, follow_redirects=False, trust_env=False) as client:
        api = API(client, auth, settings)
        async with asyncio.timeout(args.timeout):
            if args.mode == "seed":
                await seed(api, settings)
            elif args.mode == "validate":
                await validate_remaining(api, settings)
            elif args.mode == "concurrency":
                await concurrency(api, settings)
            elif args.mode == "legacy":
                await legacy(api, settings)
            else:
                await verify(api, settings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seed", "verify", "validate", "concurrency", "legacy"))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--backend-path", default="/app")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        rt.require(1 <= args.timeout <= 600, "Timeout must be 1..600 seconds")
        asyncio.run(run(args))
    except rt.AcceptanceFailure as exc:
        print(f"FAIL {exc}", flush=True)
        raise SystemExit(1) from None
    except Exception as exc:
        print(f"FAIL {type(exc).__name__}; secrets suppressed; inspect isolated service logs", flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
