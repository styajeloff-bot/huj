"""Questionnaire field catalogue, conditional rules and source precedence."""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

QUESTIONNAIRE_FIELDS: dict[str, str] = {
    "full_company_name": "Полное наименование компании",
    "short_company_name": "Сокращённое наименование",
    "inn": "ИНН компании",
    "kpp": "КПП",
    "ogrn": "ОГРН",
    "okpo": "ОКПО",
    "okato": "ОКАТО",
    "legal_form": "Организационно-правовая форма",
    "tax_system": "Система налогообложения",
    "okved_main": "Основной ОКВЭД",
    "okved_additional": "Дополнительные ОКВЭД",
    "registration_date": "Дата регистрации",
    "registration_authority_name": "Регистрирующий орган",
    "legal_address": "Юридический адрес",
    "actual_address": "Фактический адрес",
    "actual_address_same_as_legal": "Фактический адрес совпадает с юридическим",
    "actual_address_details": "Детализация фактического адреса",
    "postal_address": "Почтовый адрес",
    "legal_address_matches_registration": "Совпадение юридического адреса с адресом регистрации",
    "postal_address_matches_legal": "Совпадение юридического адреса с  почтовым адресом",
    "phone": "Телефон контактного лица",
    "email": "Email  контактного лица",
    "website": "Сайт, существующее поле",
    "company_phone": "Телефон организации",
    "company_email": "Email  организации",
    "company_website": "Сайт организации",
    "contact_person": "ФИО, должность, телефон и  email  контактного лица",
    "fax": "Факс",
    "bank_name": "Наименование банка",
    "bik": "БИК",
    "settlement_account": "Расчётный счёт",
    "correspondent_account": "Корреспондентский счёт",
    "director_full_name": "ФИО руководителя",
    "director_surname": "Фамилия руководителя",
    "director_first_name": "Имя руководителя",
    "director_patronymic": "Отчество руководителя",
    "director_position": "Должность руководителя",
    "director_inn": "ИНН руководителя",
    "director_snils": "СНИЛС руководителя",
    "director_sex": "Пол руководителя",
    "director_citizenship": "Гражданство руководителя",
    "director_birth_date": "Дата рождения руководителя",
    "director_birth_place": "Место рождения руководителя",
    "director_passport_series": "Серия паспорта",
    "director_passport_number": "Номер паспорта",
    "director_passport_issued_by": "Кем выдан паспорт",
    "director_passport_issue_date": "Дата выдачи паспорта",
    "director_passport_department_code": "Код подразделения",
    "director_registration_address": "Адрес регистрации руководителя",
    "director_phone": "Телефон руководителя",
    "director_email": "Email  руководителя",
    "director_appointment_document": "Документ о назначении руководителя",
    "director_is_pdl": "Руководитель является ПДЛ или родственником ПДЛ",
    "director_pdl_related_person": "ФИО ПДЛ или родственника ПДЛ",
    "director_name_changed": "Отметка о смене ФИО",
    "founders": "Учредители",
    "beneficiaries": "Бенефициарные владельцы",
    "has_beneficiary": "Наличие бенефициарного владельца",
    "beneficiary_info": "Дополнительные сведения о бенефициаре",
    "other_representatives": "Подписанты и другие представители",
    "management_bodies": "Органы управления",
    "employee_count": "Среднесписочная численность сотрудников",
    "licenses_or_sro_membership": "Лицензии и членство в СРО",
    "main_counterparties": "Основные контрагенты",
    "open_bank_accounts": "Открытые расчётные счета",
    "loans_credits_leasing": "Кредиты, займы и лизинг",
    "third_party_guarantees": "Поручительства за третьих лиц",
    "additional_collateral_available": "Возможность дополнительного обеспечения",
    "vehicle_purchase_purpose": "Цели приобретения ТС",
    "management_company_details": "Сведения об управляющей компании",
    "transaction_beneficiary": "Выгодоприобретатель по сделке",
    "electronic_document_management_systems": "Используемые системы ЭДО",
    "website_in_blocked_domains_registry": "Сайт в реестре запрещённых доменов",
    "state_defense_order": "Наличие гособоронзаказа",
    "personal_data_processing_consent": "Согласие на обработку персональных данных",
    "legal_entity_credit_report_consent": "Согласие на кредитный отчёт юрлица",
    "individual_credit_report_consent": "Согласие на кредитный отчёт физлица",
    "credit_bureau_data_transfer_consent": "Согласие на передачу данных в БКИ",
    "marketing_communications_consent": "Согласие на рекламные рассылки",
    "information_accuracy_declaration": "Заверение о достоверности сведений",
    "information_verification_consent": "Согласие на проверку информации",
    "permitted_data_recipients": "Банки и партнёры для передачи данных",
    "telecom_data_transfer_consent": "Согласие на передачу данных операторам связи",
    "federal_register_inclusion_consent": "Согласие на включение в федеральный реестр",
    "affiliates_data_transfer_consent": "Согласие на передачу аффилированным лицам",
    "electronic_documents_equivalence_consent": "Электронные документы равнозначны бумажным",
    "automated_marketing_consent": "Согласие на автоматические рассылки",
    "biometric_data_processing_consent": "Согласие на обработку биометрии",
    "consent_validity_period": "Срок действия согласий",
    "consent_revocation_procedure": "Порядок отзыва согласий",
    "questionnaire_completed_at": "Дата и время заполнения анкеты",
    "authorized_person_signature": "Подпись руководителя или представителя",
    "company_seal": "Оттиск печати",
    "foreign_company_name": "Наименование на иностранном языке",
    "no_beneficial_owner_reason": "Причина отсутствия бенефициарного владельца",
    "no_beneficial_owner_reason_details": "Пояснение причины отсутствия бенефициара",
    "director_actual_apartment": "director actual apartment",
    "director_actual_same_as_registration": "director actual same as registration",
    "director_actual_country": "director actual country",
    "director_registration_postal_code": "director registration postal code",
    "director_actual_address": "director actual address",
    "director_registration_date": "director registration date",
    "director_birth_country": "director birth country",
    "director_registration_country": "director registration country",
    "director_registration_apartment": "director registration apartment",
    "director_registration_house": "director registration house",
    "director_actual_house": "director actual house",
    "director_actual_postal_code": "director actual postal code",
}
QUESTIONNAIRE_REQUIRED_UNAVAILABLE_REASONS = {
    **dict.fromkeys(
        ("authorized_person_signature", "company_seal"),
        "Поле не заполняется в текущей анкете, поэтому его нельзя сделать обязательным.",
    ),
    # TODO(TZ40): visibility is independent of required; the future collection
    # process is not defined. Do not restore pre-assignment requirements for
    # request-only fields without a way to supply them before LC assignment.
    # See specs/task_2026-09-30_16-03-41_MSK.md, deferred TZ40 requirements.
    **dict.fromkeys(
        (
            "director_appointment_document",
            "state_defense_order",
            "licenses_or_sro_membership",
            "loans_credits_leasing",
            "third_party_guarantees",
            "additional_collateral_available",
            "director_snils",
            "open_bank_accounts",
            "transaction_beneficiary",
        ),
        "Сведения заполняются по дозапросу после назначения ЛК, "
        "поэтому их нельзя сделать обязательными до назначения.",
    ),
}

FIELD_SCALAR_TYPES = {
    "full_company_name": ("text", 500),
    "short_company_name": ("text", 255),
    "inn": ("text", 20),
    "ogrn": ("text", 20),
    "kpp": ("text", 20),
    "okpo": ("text", 20),
    "okato": ("text", 20),
    "okved_main": ("text", 500),
    "okved_additional": ("text", None),
    "tax_system": ("text", 50),
    "legal_form": ("text", 100),
    "legal_address": ("text", None),
    "legal_address_matches_registration": ("bool", None),
    "actual_address": ("text", None),
    "actual_address_same_as_legal": ("bool", None),
    "actual_address_details": ("text", None),
    "postal_address": ("text", None),
    "phone": ("text", 50),
    "fax": ("text", 50),
    "email": ("text", 255),
    "website": ("text", 255),
    "bank_name": ("text", 255),
    "bik": ("text", 20),
    "settlement_account": ("text", 50),
    "director_full_name": ("text", 255),
    "director_position": ("text", 100),
    "director_passport_series": ("text", 30),
    "director_passport_number": ("text", 30),
    "director_passport_issued_by": ("text", None),
    "director_passport_issue_date": ("date", None),
    "director_passport_department_code": ("text", 30),
    "director_birth_date": ("date", None),
    "director_birth_place": ("text", None),
    "director_citizenship": ("text", 100),
    "director_registration_address": ("text", None),
    "director_actual_address": ("text", None),
    "director_phone": ("text", 50),
    "director_email": ("text", 255),
    "director_surname": ("text", 100),
    "director_first_name": ("text", 100),
    "director_patronymic": ("text", 100),
    "director_sex": ("text", 20),
    "director_birth_country": ("text", 100),
    "director_registration_country": ("text", 100),
    "director_registration_postal_code": ("text", 10),
    "director_registration_house": ("text", 50),
    "director_registration_apartment": ("text", 50),
    "director_registration_date": ("date", None),
    "director_actual_country": ("text", 100),
    "director_actual_postal_code": ("text", 10),
    "director_actual_house": ("text", 50),
    "director_actual_apartment": ("text", 50),
    "director_actual_same_as_registration": ("bool", None),
    "has_beneficiary": ("bool", None),
    "beneficiary_info": ("text", None),
    "registration_date": ("date", None),
    "registration_authority_name": ("text", None),
    "postal_address_matches_legal": ("bool", None),
    "company_phone": ("text", None),
    "company_email": ("text", None),
    "company_website": ("text", None),
    "correspondent_account": ("text", None),
    "director_inn": ("text", None),
    "director_snils": ("text", None),
    "director_is_pdl": ("bool", None),
    "director_pdl_related_person": ("text", None),
    "director_name_changed": ("bool", None),
    "website_in_blocked_domains_registry": ("bool", None),
    "consent_validity_period": ("text", None),
    "consent_revocation_procedure": ("text", None),
    "foreign_company_name": ("text", None),
    "no_beneficial_owner_reason_details": ("text", None),
}
CONSENT_FIELDS = frozenset(
    {
        "personal_data_processing_consent",
        "legal_entity_credit_report_consent",
        "individual_credit_report_consent",
        "credit_bureau_data_transfer_consent",
        "marketing_communications_consent",
        "information_accuracy_declaration",
        "information_verification_consent",
        "permitted_data_recipients",
        "telecom_data_transfer_consent",
        "federal_register_inclusion_consent",
        "affiliates_data_transfer_consent",
        "electronic_documents_equivalence_consent",
        "automated_marketing_consent",
        "biometric_data_processing_consent",
        "consent_validity_period",
        "consent_revocation_procedure",
    }
)
MANUAL_READONLY_FIELDS = CONSENT_FIELDS | {
    "id",
    "application_id",
    "created_at",
    "updated_at",
    "field_sources",
    "people_identity_map",
    "vehicle_purchase_purpose",
    "questionnaire_completed_at",
    "authorized_person_signature",
    "company_seal",
}
MANUAL_SOURCES = {"manual", "document_request"}
PEOPLE_FIELDS = {"founders", "beneficiaries", "other_representatives"}
FILE_DEFAULTS = {
    "loans_credits_leasing": "Данные о кредитах, займах и лизинге отсутствуют",
    "third_party_guarantees": "Данные о поручительствах за третьих лиц отсутствуют",
    "additional_collateral_available": "Данные о возможности предоставления дополнительного обеспечения отсутствуют",
    "state_defense_order": "Документ о гособоронзаказе не предоставлен",
    "director_appointment_document": "Документ о назначении руководителя не предоставлен",
}

MANUAL_READONLY_FIELDS = MANUAL_READONLY_FIELDS | set(FILE_DEFAULTS) | {"licenses_or_sro_membership"}


def initial_values() -> dict[str, Any]:
    return {
        **{
            key: {"status": "missing", "text": value, "documents": []}
            for key, value in FILE_DEFAULTS.items()
        },
        "management_company_details": {
            "requisites": [], "status": "not_provided", "file_name": None, "documents": [],
        },
        "postal_address_matches_legal": False,
        "actual_address_same_as_legal": False,
        "website_in_blocked_domains_registry": False,
        "director_is_pdl": False,
        "director_name_changed": False,
    }


def without_confidence(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: without_confidence(item)
            for key, item in value.items()
            if "confidence" not in key.lower()
        }
    if isinstance(value, list):
        return [without_confidence(item) for item in value]
    return value


def merge_with_sources(
    current: dict[str, Any], payload: dict[str, Any], source: str
) -> tuple[dict[str, Any], dict[str, str]]:
    sources = dict(current.get("field_sources") or {})
    explicit = source in MANUAL_SOURCES

    def protected(path: str) -> bool:
        parts = path.split(".")
        return any(
            sources.get(".".join(parts[:i])) in MANUAL_SOURCES
            for i in range(1, len(parts) + 1)
        )

    def mark_existing(value: Any, path: str, existing_source: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                mark_existing(item, f"{path}.{key}", existing_source)
        else:
            sources[path] = existing_source

    def merge_people(old: Any, new: list[Any], path: str) -> list[Any]:
        previous = old if isinstance(old, list) else []
        indexed = {
            str(UUID(person["id"])): person
            for person in previous
            if isinstance(person, dict)
        }
        if sources.get(path) in MANUAL_SOURCES:
            existing_source = sources.pop(path)
            for key, person in indexed.items():
                mark_existing(person, f"{path}.{key}", existing_source)
        people_result: list[Any] = []
        seen: set[str] = set()
        for incoming in new:
            if not isinstance(incoming, dict):
                continue
            person = deepcopy(incoming)
            key = str(UUID(person["id"]))
            seen.add(key)
            if explicit and sources.get(f"{path}.{key}") in MANUAL_SOURCES:
                sources.pop(f"{path}.{key}")
            if not explicit and key not in indexed and protected(f"{path}.{key}"):
                continue
            people_result.append(merge(indexed.get(key), person, f"{path}.{key}"))
        for key, person in indexed.items():
            if key not in seen:
                if explicit:
                    sources[f"{path}.{key}"] = source
                else:
                    people_result.append(person)
        return people_result

    def merge(old: Any, new: Any, path: str) -> Any:
        if path in PEOPLE_FIELDS and isinstance(new, list):
            return merge_people(old, new, path)
        if not explicit and protected(path):
            return old
        if isinstance(new, dict):
            result = deepcopy(old) if isinstance(old, dict) else {}
            for key, value in new.items():
                result[key] = merge(result.get(key), value, f"{path}.{key}")
            return result
        if old != new or (explicit and new is None):
            sources[path] = source
        return deepcopy(new)

    updates = {
        key: merge(current.get(key), value, key)
        for key, value in without_confidence(payload).items()
    }
    if updates.get(
        "actual_address_same_as_legal", current.get("actual_address_same_as_legal")
    ) is True:
        # Derive only after source precedence has chosen the effective legal address.
        updates["actual_address"] = updates.get("legal_address", current.get("legal_address"))
        sources["actual_address"] = "derived"
    return updates, sources


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _phone(value: Any) -> None:
    if (
        value is not None
        and value != ""
        and (
            not isinstance(value, str)
            or not re.fullmatch(r"\+?[\d\s()\-]{7,25}", value)
            or not 7 <= len(re.sub(r"\D", "", value)) <= 15
        )
    ):
        raise ValueError("Укажите корректный номер телефона")


def _email(value: Any) -> None:
    if value and (
        not isinstance(value, str)
        or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)
    ):
        raise ValueError("Укажите корректный email")


def _normalize_scalars(result: dict[str, Any]) -> None:
    for key, raw_value in result.items():
        value = raw_value.strip() or None if isinstance(raw_value, str) else raw_value
        result[key] = value
        kind, limit = FIELD_SCALAR_TYPES.get(key, (None, None))
        if value is None:
            if key == "actual_address_same_as_legal":
                raise ValueError(
                    f"Поле {QUESTIONNAIRE_FIELDS[key]} должно быть логическим значением"
                )
            continue
        if kind == "text" and (
            not isinstance(value, str) or (limit and len(value) > limit)
        ):
            raise ValueError(f"Некорректное значение поля {QUESTIONNAIRE_FIELDS[key]}")
        if kind == "bool" and not isinstance(value, bool):
            raise ValueError(
                f"Поле {QUESTIONNAIRE_FIELDS[key]} должно быть логическим значением"
            )
        if kind == "date":
            if not isinstance(value, str):
                raise TypeError("Укажите дату строкой")
            try:
                date.fromisoformat(value)
            except ValueError:
                day, month, year = (int(part) for part in value.split("."))
                result[key] = date(year, month, day).isoformat()


def _normalize_contacts(result: dict[str, Any]) -> None:
    for key in ("company_phone", "phone", "director_phone"):
        if key in result:
            _phone(result[key])
    for key in ("company_email", "email", "director_email"):
        if key in result:
            _email(result[key])
    if result.get("company_website"):
        value = result["company_website"]
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or "." not in parsed.hostname
            or re.search(r"\s", value)
        ):
            raise ValueError("Укажите корректный сайт организации")
    if "contact_person" in result and result["contact_person"] is not None:
        person = result["contact_person"]
        if not isinstance(person, dict) or any(
            k not in {"name", "position", "phone", "email"} for k in person
        ):
            raise ValueError("Укажите одно контактное лицо")
        if any(
            value is not None and not isinstance(value, str)
            for value in person.values()
        ):
            raise ValueError("Поля контактного лица должны быть текстом")
        _phone(person.get("phone"))
        _email(person.get("email"))
        for key in ("phone", "email"):
            if key in person:
                result[key] = person[key] or None


_PERSON_TEXT_FIELDS = frozenset({
    "name", "full_name", "surname", "first_name", "patronymic", "inn", "ogrn",
    "snils", "birth_place", "birth_country", "citizenship", "sex", "position",
    "passport_series", "passport_number", "passport_issued_by",
    "passport_department_code", "registration_address", "registration_country",
    "registration_postal_code", "registration_house", "registration_apartment",
    "actual_address", "actual_country", "actual_postal_code", "actual_house",
    "actual_apartment", "phone", "email", "pdl_related_person_name",
    "beneficial_owner_basis_details", "type", "document_type", "share_encumbrance",
    "signer_key",
})
_PERSON_BOOL_FIELDS = frozenset({
    "is_pdl", "name_changed", "no_patronymic", "actual_same_as_registration",
})
_PERSON_DATE_FIELDS = frozenset({
    "birth_date", "passport_issue_date", "registration_date",
})
_PERSON_UUID_FIELDS = frozenset({"id", "beneficial_owner_basis"})


def _person_date(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Поле физического лица {key} должно содержать дату строкой")
    value = value.strip()
    if not value:
        return ""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}", value):
        raise ValueError(f"Некорректная дата в поле физического лица {key}")
    try:
        if "." in value:
            day, month, year = (int(part) for part in value.split("."))
            parsed = date(year, month, day)
        else:
            parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Некорректная дата в поле физического лица {key}") from exc
    return parsed.isoformat()


def _person_uuid(value: Any, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Поле физического лица {key} должно содержать UUID")
    value = value.strip()
    if not value:
        return ""
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise ValueError(f"Некорректный UUID в поле физического лица {key}") from exc


def _normalize_person_fields(person: dict[str, Any]) -> None:
    for key in _PERSON_TEXT_FIELDS & person.keys():
        value = person[key]
        if value is not None and not isinstance(value, str):
            raise TypeError(f"Поле физического лица {key} должно быть текстом")
    for key in _PERSON_BOOL_FIELDS & person.keys():
        value = person[key]
        if value is not None and not isinstance(value, bool):
            raise TypeError(f"Поле физического лица {key} должно быть логическим значением")
    for key in _PERSON_DATE_FIELDS & person.keys():
        person[key] = _person_date(person[key], key)
    for key in _PERSON_UUID_FIELDS & person.keys():
        person[key] = _person_uuid(person[key], key)


def _normalize_person_shares(person: dict[str, Any]) -> None:
    for key in {"share", "share_percentage"} & person.keys():
        value = person[key]
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                person[key] = None
                continue
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            raise TypeError("Доля владения должна быть числом от 0 до 100")
        try:
            number = Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError("Доля владения должна быть числом от 0 до 100") from exc
        if not number.is_finite() or not Decimal("0") <= number <= Decimal("100"):
            raise ValueError("Доля владения должна быть от 0 до 100")
        # JSONB and the existing UI use JSON numbers. Convert only after exact
        # Decimal validation; binary floats never participate in the range check.
        person[key] = int(number) if number == number.to_integral_value() else float(number)


def _normalize_person(person: Any) -> None:
    if not isinstance(person, dict):
        raise TypeError("Некорректная карточка физического лица")
    _normalize_person_fields(person)
    _normalize_person_shares(person)
    if person.get("is_pdl"):
        if not _text(person.get("pdl_related_person_name")):
            raise ValueError("Укажите ФИО ПДЛ или родственника ПДЛ")
    elif "is_pdl" in person:
        person["pdl_related_person_name"] = None


def _normalize_people(result: dict[str, Any]) -> None:
    for key in PEOPLE_FIELDS & result.keys():
        if result[key] is None:
            result[key] = []
        if not isinstance(result[key], list):
            raise TypeError("Сведения о лицах должны быть списком")
        seen: set[str] = set()
        for person in result[key]:
            _normalize_person(person)
            if person.get("id"):
                identifier = str(UUID(str(person["id"])))
                if identifier in seen:
                    raise ValueError("Идентификаторы карточек не должны повторяться")
                person["id"] = identifier
                seen.add(identifier)


def _normalize_edo(result: dict[str, Any]) -> None:
    edo = result.get("electronic_document_management_systems")
    if edo is None:
        return
    if not isinstance(edo, dict):
        raise TypeError("Некорректные сведения об ЭДО")
    if any(
        not isinstance(edo[key], bool)
        for key in {"sbis", "diadoc", "kontur", "other", "not_used"} & edo.keys()
    ):
        raise ValueError("Выбор системы ЭДО должен быть логическим значением")
    if edo.get("not_used"):
        edo.update(sbis=False, diadoc=False, kontur=False, other=False, other_name=None)
    elif edo.get("other") and not _text(edo.get("other_name")):
        raise ValueError("Укажите название другой системы ЭДО")
    elif not edo.get("other"):
        edo["other_name"] = None


def _normalize_conditions(current: dict[str, Any], result: dict[str, Any]) -> None:
    merged = {**current, **result}
    if merged.get("postal_address_matches_legal") is True:
        result["postal_address"] = merged.get("legal_address")
    if {"director_is_pdl", "director_pdl_related_person"} & result.keys():
        if merged.get("director_is_pdl"):
            if not _text(merged.get("director_pdl_related_person")):
                raise ValueError("Укажите ФИО ПДЛ или родственника ПДЛ")
        else:
            result["director_pdl_related_person"] = None
    if {"has_beneficiary", "no_beneficial_owner_reason"} & result.keys():
        if merged.get("has_beneficiary") is True:
            result["no_beneficial_owner_reason"] = None
            result["no_beneficial_owner_reason_details"] = None
        elif merged.get("has_beneficiary") is False:
            result["beneficiaries"] = []
    if "employee_count" in result and result["employee_count"] is not None:
        value = result["employee_count"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                "Численность сотрудников должна быть целым неотрицательным числом"
            )


def normalize_questionnaire_payload(
    current: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    result: dict[str, Any] = without_confidence(
        {
            k: v
            for k, v in payload.items()
            if k in QUESTIONNAIRE_FIELDS and k not in MANUAL_READONLY_FIELDS
        }
    )
    if "management_company_details" in result:
        incoming = result["management_company_details"]
        previous = current.get("management_company_details")
        if isinstance(incoming, dict):
            if "requisites" not in incoming or set(incoming) - {
                "requisites", "status", "file_name", "documents",
            }:
                raise ValueError("Передайте реквизиты управляющей компании в requisites")
            for key in ("status", "file_name", "documents"):
                if key in incoming and (
                    not isinstance(previous, dict) or incoming[key] != previous.get(key)
                ):
                    raise ValueError("Сведения о документе изменяются только ответом на дозапрос")
            requisites = incoming["requisites"]
        else:
            # Preserve the legacy manual API: a list (or explicit null) edits
            # requisites only and cannot erase document-request evidence.
            requisites = incoming
        if requisites is not None and (
            not isinstance(requisites, list)
            or any(not isinstance(row, dict) for row in requisites)
        ):
            raise ValueError("Реквизиты управляющей компании должны быть массивом объектов")
        result["management_company_details"] = {"requisites": requisites}
    _normalize_scalars(result)
    _normalize_contacts(result)
    _normalize_people(result)
    _normalize_edo(result)
    _normalize_conditions(current, result)
    return result


def questionnaire_progress(data: dict[str, Any]) -> tuple[int, bool]:
    fields = (
        "full_company_name",
        "short_company_name",
        "inn",
        "kpp",
        "ogrn",
        "legal_address",
        "actual_address",
        "phone",
        "email",
        "director_full_name",
        "director_position",
    )
    return (
        round(sum(bool(data.get(key)) for key in fields) / len(fields) * 100),
        all(
            data.get(key)
            for key in (
                "full_company_name",
                "inn",
                "legal_address",
                "director_full_name",
            )
        ),
    )
