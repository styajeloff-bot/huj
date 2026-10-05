"""Real API/DB/S3 path with an explicitly synthetic provider HTTP response."""
import asyncio
import json
from pathlib import Path
from uuid import UUID

from acceptance import API, ROOT, db_questionnaire, guard, new_application, progress, require


async def verify():
    guard()
    from infrastructure.settings import settings
    require(settings.parser_api_url == "http://provider-fixture:8080" and settings.parser_api_key == "fixture-only", "Refusing non-fixture provider")
    from sqlalchemy import select
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.documents import Document, DocumentApplication
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    mode = ROOT / "provider-mode.json"
    mode.write_text(json.dumps("success"))
    app_id = await new_application(state)
    url = f"/api/v1/questionnaire/{app_id}"
    first = await api.request("client", "POST", url + "/refresh")
    require(first["sources"]["fns"] == "updated" and first["sources"]["egrul"] == "updated", "FNS/PDF flow failed")
    require(first["questionnaire"]["employee_count"] == 42, "Latest headcount year not selected")
    async with AsyncSessionLocal() as session:
        docs = (await session.execute(select(Document.id, Document.file_name, Document.s3_key).join(DocumentApplication, DocumentApplication.document_id == Document.id).where(DocumentApplication.application_id == UUID(app_id), Document.document_type == "egrul"))).all()
        require(len(docs) == 1, "EGRUL not linked once")
        document_id = str(docs[0].id)
        from infrastructure.services.document_storage import get_document
        require((await get_document(docs[0].s3_key)).startswith(b"%PDF-"), "Stored content not PDF")
    for disposition in ("inline", "attachment"):
        file_response = await api.request("client", "GET", f"/api/v1/documents/{document_id}/content?disposition={disposition}", raw=True)
        require(file_response.content.startswith(b"%PDF-"), "EGRUL content endpoint lost PDF")
        require(file_response.headers.get("content-disposition", "").startswith(disposition), "EGRUL open/download disposition mismatch")
    await api.request("outsider", "GET", f"/api/v1/documents/{document_id}/content", expected=(403, 404), raw=True)
    await api.request("client", "PUT", url, json={"employee_count": 9, "full_company_name": "Ручное название"})
    again = await api.request("client", "POST", url + "/refresh")
    require(again["sources"]["egrul"] == "already_attached", "Repeat downloaded duplicate extract")
    require(again["questionnaire"]["employee_count"] == 9 and again["questionnaire"]["full_company_name"] == "Ручное название", "Automatic source overwrote manual data")
    async with AsyncSessionLocal() as session:
        ids = (await session.scalars(select(DocumentApplication.document_id).where(DocumentApplication.application_id == UUID(app_id)))).all()
        require([str(item) for item in ids] == [document_id], "Duplicate document link")
    mode.write_text(json.dumps("unavailable"))
    failed = await api.request("client", "POST", url + "/refresh")
    require(failed["sources"]["fns"] == "unavailable" and failed["questionnaire"]["employee_count"] == 9, "Outage lost manual data")
    for value, expected in (("invalid_pdf", "unavailable"), ("not_found", "not_found")):
        mode.write_text(json.dumps(value))
        other_id = await new_application(state)
        result = await api.request("client", "POST", f"/api/v1/questionnaire/{other_id}/refresh")
        require(result["sources"]["egrul"] == expected, f"Bad PDF handling {value}")
    mode.write_text(json.dumps("success"))
    require((await db_questionnaire(app_id))["id"] == UUID(first["questionnaire"]["id"]), "Refresh changed questionnaire identity")
    progress("synthetic_provider_http_db_s3_passed", live_provider_verified=False)


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    finally:
        (Path("/runtime") / "provider-mode.json").write_text(json.dumps("success"))
