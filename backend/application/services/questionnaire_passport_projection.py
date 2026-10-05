"""Copy confirmed passport values to the application questionnaire."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.application_sopd_candidates import (
    PERSON_COLLECTIONS,
    questionnaire_person_id,
)
from domain.questionnaire_people import normalize_stored_people
from infrastructure.repositories import application_repository as app_repo

PASSPORT_MAPPING = {
    "surname": "surname", "name": "first_name", "patronymic": "patronymic",
    "nationality": "citizenship", "gender": "sex", "birthDate": "birth_date",
    "birthPlace": "birth_place", "passportSeries": "passport_series",
    "passportNumber": "passport_number", "givenDate": "passport_issue_date",
    "code": "passport_department_code", "givenWhom": "passport_issued_by",
}


async def project_confirmed_passport(session: AsyncSession, snapshot: dict[str, Any]) -> None:
    from application.services.questionnaire import write_questionnaire

    fields = snapshot["confirmed_fields"]
    signer_key = snapshot["signer_key"]
    values = {target: fields.get(source) for source, target in PASSPORT_MAPPING.items()}
    values["full_name"] = " ".join(str(fields.get(key) or "").strip() for key in ("surname", "name", "patronymic")).strip()
    application_id = snapshot["application_id"]
    edited = set(snapshot.get("edited_fields") or [])
    questionnaire = normalize_stored_people(
        await app_repo.get_questionnaire(session, application_id, for_update=True) or {},
        application_id,
    )
    role = snapshot.get("signer_role")
    if role == "director_applicant":
        automatic = {f"director_{key}": value for key, value in values.items()}
        await write_questionnaire(session, application_id=application_id, payload=automatic, source="sopd")
        manual = {f"director_{PASSPORT_MAPPING[key]}": fields.get(key) for key in edited if key in PASSPORT_MAPPING}
        if edited.intersection({"surname", "name", "patronymic"}):
            manual["director_full_name"] = values["full_name"]
        if manual:
            await write_questionnaire(session, application_id=application_id, payload=manual, source="manual")
        return
    if role not in PERSON_COLLECTIONS:
        raise ServiceError("Роль подписанта не определена", 409)
    identifier = questionnaire_person_id(questionnaire, role=role, signer_key=signer_key)
    if identifier is None:
        return
    collection = PERSON_COLLECTIONS[role]
    people = [dict(person) for person in questionnaire.get(collection) or [] if isinstance(person, dict)]
    person = next(person for person in people if UUID(person["id"]) == identifier)
    if collection == "beneficiaries":
        address = snapshot["recognition_fields"].get("_registration_address")
        if address:
            values["registration_address"] = address
    person.update(values)
    if collection == "founders" and "name" in person:
        person["name"] = values["full_name"]
    person["signer_key"] = signer_key
    await write_questionnaire(session, application_id=application_id, payload={collection: people}, source="sopd")
    manual_values = {PASSPORT_MAPPING[key]: fields.get(key) for key in edited if key in PASSPORT_MAPPING}
    if edited.intersection({"surname", "name", "patronymic"}):
        manual_values["full_name"] = values["full_name"]
        if collection == "founders" and "name" in person:
            manual_values["name"] = values["full_name"]
    if manual_values:
        saved = await app_repo.get_questionnaire(session, application_id) or {}
        saved_people = [dict(item) for item in saved.get(collection) or [] if isinstance(item, dict)]
        target = next((item for item in saved_people if UUID(item["id"]) == identifier), None)
        if target is not None:
            target.update(manual_values)
            await write_questionnaire(session, application_id=application_id, payload={collection: saved_people}, source="manual")
