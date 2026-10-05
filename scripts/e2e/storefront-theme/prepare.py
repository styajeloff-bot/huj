"""Create fixtures in the isolated storefront-theme E2E database."""
import asyncio
import json
import time
from pathlib import Path
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import select
from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.database import AsyncSessionLocal
from infrastructure.models.users import User, UserSession
from infrastructure.models.storefronts import Storefront
from infrastructure.models.storefront_pages import StorefrontPage
from infrastructure.settings import settings

SID = UUID("00000000-0000-0000-0000-000000000001")
PID = UUID("e2e00000-0000-0000-0000-000000000001")
def layout(settings=None):
    return {"settings": settings or {}, "sections": [{"id": str(uuid4()), "name": "E2E Palette", "layout_type": "container", "columns": [{"id": str(uuid4()), "width": 12, "widgets": [
        {"id": str(uuid4()), "type": "leasing_calculator", "props": {"title": "E2E Palette Calculator", "subtitle": "Theme preview", "show_apply_button": True}},
        {"id": str(uuid4()), "type": "rich_text", "props": {"html_content": "<p>E2E explicit override</p>"}, "styles": {"text_color": "#5A2288", "background_color": "#EDDDAA"}}
    ]}]}]}
async def main():
    if "storefront_theme_e2e" not in settings.database_dsn:
        raise RuntimeError("Only isolated storefront-theme E2E DB is permitted")
    output = Path("/runtime/artifacts")
    output.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as session:
        sf = await session.get(Storefront, SID)
        if sf is None:
            sf = Storefront(id=SID, is_default=True, slug=None)
            session.add(sf)
        sf.appearance_primary_color = "#247A49"
        sf.appearance_background_color = "#F2F4EF"
        sf.appearance_surface_color = "#E3EADC"
        sf.appearance_text_color = "#263B31"
        await session.flush()
        existing = (await session.execute(select(StorefrontPage).where(StorefrontPage.storefront_id == SID, StorefrontPage.page_key == "about"))).scalar_one_or_none()
        if existing is None:
            existing = StorefrontPage(id=PID, storefront_id=SID, page_key="about", title="About E2E", is_system=True)
            session.add(existing)
        existing.status = "published"
        existing.version = 1
        existing.draft_layout = layout()
        existing.published_layout = existing.draft_layout
        existing.published_at = datetime.now(UTC)
        for alias, role in (("admin", "carcraft_employee"), ("client", "client")):
            phone = "+700018417" + ("01" if alias == "admin" else "02")
            user = (await session.execute(select(User).where(User.phone == phone))).scalar_one_or_none()
            if user is None:
                user = await session.merge(User(id=uuid5(NAMESPACE_URL, "storefront-theme/" + alias), name="Storefront theme " + alias, phone=phone, role=role, is_active=True, phone_verified=True))
            await session.flush()
            session_id = uuid4()
            access, refresh = generate_tokens(user.id, role, None, refresh_session_id=session_id)
            session.add(UserSession(id=session_id, user_id=user.id, refresh_token_hash=hash_refresh_token(refresh), expires_at=datetime.now(UTC) + timedelta(days=1)))
            state = {"cookies": [{"name": key, "value": val, "domain": "localhost", "path": "/", "expires": time.time() + 86400, "httpOnly": True, "secure": False, "sameSite": "Lax"} for key, val in (("accessToken", access), ("refreshToken", refresh))], "origins": []}
            (output / (alias + ".storage.json")).write_text(json.dumps(state))
        await session.commit()
        (output / "manifest.json").write_text(json.dumps({"storefront": str(SID), "page": str(existing.id)}))
    print("storefront-theme fixture ready")
asyncio.run(main())
