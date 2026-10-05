"""Seed technical OCR evidence for a real browser test; this is not live DBrain."""
import asyncio
import json
from uuid import UUID
from acceptance import API, ROOT, guard, private_json, require, progress

async def run():
    guard()
    import sqlalchemy as sa
    from infrastructure.models.sopd_passport_snapshots import SopdPassportSnapshot
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.repositories import sopd_passport_snapshot_repository as snapshots
    from application.services.sopd_passport import map_dbrain
    state = json.loads((ROOT / "state.secret.json").read_text())
    manifest = json.loads((ROOT / "manifest.json").read_text())
    app_id = manifest["ui_application_id"]
    await API(state).request("client", "PUT", f"/api/v1/applications/{app_id}/questionnaire", json={"beneficiaries": [], "has_beneficiary": True})
    candidates = (await API(state).request("client", "GET", f"/api/v1/applications/{app_id}/sopd-signer-candidates"))["candidates"]
    directors = [row for row in candidates if row["role"] == "director_applicant"]
    require(len(directors) == 1, "Expected one UI application director")
    key = directors[0]["key"]
    fields = {"surname": "Тестов", "first_name": "Иван", "other_names": "Иванович", "nationality": "Российская Федерация", "sex": "male", "date_of_birth": "1980-01-01", "place_of_birth": "Москва", "series_and_number": "1234 123456", "date_of_issue": "2020-01-01", "subdivision_code": "123-456", "issuing_authority": "УМВД России"}
    raw = {"items": [{"fields": fields, "confidence": {field: 0.98 for field in fields}}]}
    raw["items"][0]["confidence"]["place_of_birth"] = 0
    mapped, confidence = map_dbrain(raw)
    async with AsyncSessionLocal() as session:
        # Reset only this disposable application's technical snapshot for repeatable UI evidence.
        await session.execute(sa.delete(SopdPassportSnapshot).where(SopdPassportSnapshot.application_id == UUID(app_id), SopdPassportSnapshot.signer_key == key))
        await snapshots.upsert_recognition(session, application_id=UUID(app_id), signer_key=key, owner_user_id=UUID(state["users"]["client"]["id"]), fields=mapped, confidence=confidence)
        await session.commit()
    manifest["ui_signer_key"] = key
    private_json(ROOT / "manifest.json", manifest)
    progress("ui_confidence_fixture_ready", application_id=app_id, evidence="technical snapshot; not live DBrain")

if __name__ == "__main__":
    asyncio.run(run())
