"""Real HTTP/PostgreSQL/S3 checks for questionnaire-scoped SOPD files."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from acceptance import API, ROOT, guard, new_application as create_application, pdf, progress, require

FIELD = "personal_data_processing_consent"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a9S8AAAAASUVORK5CYII=")


async def new_application(state):
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.applications import LeasingCompanyApplication
    app_id = await create_application(state)
    async with AsyncSessionLocal() as session:
        for alias in ("lc_a", "lc_b"):
            session.add(LeasingCompanyApplication(application_id=UUID(app_id),
                leasing_company_id=UUID(state["companies"][alias]["leasing_company_id"])))
        await session.commit()
    return app_id


def content_url(app_id, request_id, *, field=FIELD, disposition="attachment"):
    return f"/api/v1/questionnaire/{app_id}/consents/{request_id}/content?field={field}&disposition={disposition}"


async def signature_fixture(state, app_id, *, content=PNG, content_type="image/png", scope=("lc_a", "lc_b"), signer="director", status="signed_physical", signed_at=None, key=True, store=True):
    from application.services.questionnaire_consents import refresh_consent_projection
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.signature_requests import SignatureRequest
    from infrastructure.models.sopd_operator_snapshots import SopdOperatorSnapshot
    from infrastructure.services.object_storage import get_object_storage
    request_id = uuid4()
    s3_key = f"questionnaire-22286/consent/{request_id}" if key else None
    user_id = UUID(state["users"]["outsider"]["id"])
    if store and key:
        await get_object_storage().put(s3_key, content, content_type)
    async with AsyncSessionLocal() as session:
        session.add(SignatureRequest(id=request_id, user_id=user_id, application_id=UUID(app_id), document_type="sopd",
            status=status, signed_at=signed_at or datetime.now(UTC), signature_method="physical",
            signed_pdf_s3_key=s3_key, subject_snapshot={"full_name": "Тестовый подписант СОПД", "signer_key": signer}))
        await session.flush()
        session.add(SopdOperatorSnapshot(signature_request_id=request_id, user_id=user_id, application_id=UUID(app_id),
            leasing_companies=[{"id": state["companies"][alias]["leasing_company_id"], "name": alias} for alias in scope], contractors=[]))
        await session.flush()
        await refresh_consent_projection(session, UUID(app_id))
        await session.commit()
    return request_id, s3_key


async def verify():
    guard()
    from infrastructure.database import AsyncSessionLocal
    from infrastructure.models.signature_requests import SignatureRequest
    from infrastructure.models.sopd_revocations import SopdRevokedOperator, SopdRevokeRequest
    from infrastructure.services.object_storage import get_object_storage
    state = json.loads((ROOT / "state.secret.json").read_text())
    api = API(state)
    app_id = await new_application(state)
    request_id, key = await signature_fixture(state, app_id)
    url = content_url(app_id, request_id)
    before = await get_object_storage().get(key)
    for actor in ("client", "admin", "lc_a", "lc_b"):
        for disposition in ("inline", "attachment"):
            response = await api.request(actor, "GET", content_url(app_id, request_id, disposition=disposition), raw=True)
            require(response.content == PNG and response.headers["content-type"] == "image/png", "Existing PNG was changed or mislabeled")
            require(response.headers["content-disposition"] == f'{disposition}; filename="sopd-{request_id}.png"', "Disposition or physical-file suffix is wrong")
            require(response.headers["cache-control"] == "private, no-store", "Consent response can outlive revocation in browser cache")
    # Applicant and admin are not the signing user; old global download remains private.
    await api.request("client", "GET", f"/api/v1/signatures/{request_id}/download", expected=403)
    await api.request(None, "GET", url, expected=401)
    await api.request("outsider", "GET", url, expected=(403, 404))
    await api.request("client", "GET", content_url(app_id, request_id, field="company_seal"), expected=404)
    await api.request("client", "GET", content_url(app_id, request_id, disposition="invalid"), expected=422)
    await api.request("admin", "GET", content_url(app_id, uuid4()), expected=404)
    foreign_app = await new_application(state)
    await api.request("admin", "GET", content_url(foreign_app, request_id), expected=404)

    settings_url = f"/api/v1/leasing/companies/{state['companies']['lc_a']['leasing_company_id']}/questionnaire-settings"
    original = (await api.request("admin", "GET", settings_url))["fields"]
    original = [{key: item[key] for key in ("field", "enabled", "required")} for item in original]
    try:
        hidden = [{**item, "enabled": False, "required": False} if item["field"] == FIELD else item for item in original]
        await api.request("admin", "PUT", settings_url, json={"fields": hidden})
        await api.request("lc_a", "GET", url, expected=404)
        await api.request("lc_b", "GET", url, raw=True)
        await api.request("client", "GET", url, raw=True)
    finally:
        await api.request("admin", "PUT", settings_url, json={"fields": original})

    pdf_app = await new_application(state)
    pdf_data = pdf()
    pdf_id, _ = await signature_fixture(state, pdf_app, content=pdf_data, content_type="application/pdf", scope=("lc_a",))
    response = await api.request("lc_a", "GET", content_url(pdf_app, pdf_id), raw=True)
    require(response.content == pdf_data and response.headers["content-type"] == "application/pdf" and '.pdf"' in response.headers["content-disposition"], "PDF bytes or metadata changed")
    await api.request("lc_b", "GET", content_url(pdf_app, pdf_id), expected=404)
    for options, expected in (({"key": False}, 404), ({"store": False}, 410), ({"status": "pending"}, 404)):
        missing_app = await new_application(state)
        missing_id, _ = await signature_fixture(state, missing_app, **options)
        await api.request("client", "GET", content_url(missing_app, missing_id), expected=expected)

    # Revocation is deliberately written without refreshing the questionnaire:
    # even stale persisted references must not authorize the file.
    revoked_app = await new_application(state)
    revoked_id, _ = await signature_fixture(state, revoked_app)
    revoked_url = content_url(revoked_app, revoked_id)
    async with AsyncSessionLocal() as session:
        user_id = UUID(state["users"]["outsider"]["id"])
        lc_id = UUID(state["companies"]["lc_a"]["leasing_company_id"])
        revoke = SopdRevokeRequest(signature_request_id=revoked_id, user_id=user_id, application_id=UUID(revoked_app),
            status="confirmed", selected_leasing_company_ids=[lc_id], revoked_leasing_company_ids=[lc_id],
            revoked_contractor_ids=[], excluded_contractor_ids=[], operators_snapshot={})
        session.add(revoke)
        await session.flush()
        session.add(SopdRevokedOperator(revoke_request_id=revoke.id, signature_request_id=revoked_id, user_id=user_id,
            operator_type="leasing_company", leasing_company_id=lc_id, operator_name="lc_a", operator_inn="0000222863"))
        await session.commit()
    await api.request("lc_a", "GET", revoked_url, expected=404)
    await api.request("lc_b", "GET", revoked_url, raw=True)
    async with AsyncSessionLocal() as session:
        request = await session.get(SignatureRequest, revoked_id)
        request.status = "revoked"
        request.revoked_at = datetime.now(UTC)
        await session.commit()
    for actor in ("admin", "client", "lc_b"):
        await api.request(actor, "GET", revoked_url, expected=404)

    older_id, _ = await signature_fixture(state, app_id, signed_at=datetime.now(UTC) - timedelta(days=1))
    await api.request("client", "GET", content_url(app_id, older_id), expected=404)
    after = await get_object_storage().get(key)
    require(before.data == after.data and before.etag == after.etag, "Reading the questionnaire rewrote its signed file")
    (ROOT / "consent-document-manifest.json").write_text(json.dumps({
        "application_id": app_id, "signature_request_id": str(request_id),
        "field": FIELD, "sha256": sha256(PNG).hexdigest(), "filename": f"sopd-{request_id}.png",
        "lc_a": state["companies"]["lc_a"]["leasing_company_id"],
    }))
    progress("questionnaire_consent_document_http_db_s3_passed", application_id=app_id,
        checked="PDF/PNG, applicant/admin/LC, outsider, foreign app, hidden field, LC scope, partial/full revoke, stale reference, replaced SOPD, missing file, original file preserved")


if __name__ == "__main__":
    asyncio.run(verify())
