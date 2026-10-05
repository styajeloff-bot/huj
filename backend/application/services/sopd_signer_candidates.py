"""Build SOPD signer candidates for a company profile."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from domain.errors import CompanyLookupUnavailableError, SopdSignerResolutionError
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.repositories.dadata_normalization import normalize_dadata_payload

SignerRole = Literal["director_applicant", "director_management_company", "founder"]
SigningMethod = Literal["sms", "file"]

MAX_MANAGEMENT_COMPANY_DEPTH = 5
logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class SopdSignerCandidate:
    key: str
    role: SignerRole
    role_label: str
    full_name: str
    inn: str | None
    signing_method: SigningMethod
    source: str
    sort_order: int
    share: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "role": self.role,
            "role_label": self.role_label,
            "full_name": self.full_name,
            "inn": self.inn,
            "share": self.share,
            "signing_method": self.signing_method,
            "source": self.source,
            "sort_order": self.sort_order,
        }


@dataclass(frozen=True)
class _CandidateDraft:
    role: SignerRole
    role_label: str
    full_name: str
    inn: str | None
    share: str | None
    signing_method: SigningMethod
    source: str
    key: str


_ROLE_PRIORITY: dict[SignerRole, int] = {
    "director_applicant": 0,
    "director_management_company": 1,
    "founder": 2,
}
_FOUNDER_COLLECTION_KEYS = ("founders", "items", "data", "values", "result")
_FOUNDER_MARKER_KEYS = (
    "name",
    "full_name",
    "fio",
    "surname",
    "first_name",
    "inn",
    "share",
    "share_percentage",
    "percent",
)


async def build_sopd_signer_candidates(
    company: dict[str, Any],
    provider: CompanyLookupProvider | None = None,
    *,
    max_depth: int = MAX_MANAGEMENT_COMPANY_DEPTH,
) -> list[dict[str, Any]]:
    """Return flat SOPD signer candidates without mutating the profile payload."""
    cache: dict[str, dict[str, Any] | None] = {}
    drafts: list[_CandidateDraft] = []

    source_company = dict(company)
    director_name = _clean_string(source_company.get("director_full_name"))
    director_inn = _normalize_inn(source_company.get("director_inn"))

    director_inn_is_valid = _is_physical_inn(director_inn) or _is_legal_inn(
        director_inn
    )
    should_enrich_applicant = not director_inn_is_valid or (
        _is_physical_inn(director_inn) and not director_name
    )
    if provider is not None and should_enrich_applicant:
        enriched = await _enrich(company.get("inn"), provider, cache)
        if enriched is None:
            raise SopdSignerResolutionError(
                "Не удалось определить директора компании-заявителя"
            )
        enriched_director_name = _clean_string(enriched.get("director_full_name"))
        if not director_inn_is_valid:
            director_name = enriched_director_name or director_name
            director_inn = _normalize_inn(enriched.get("director_inn"))
        elif not director_name:
            director_name = enriched_director_name
        if source_company.get("founders") in (None, [], {}):
            source_company["founders"] = enriched.get("founders")

    if _is_physical_inn(director_inn):
        if not director_name:
            raise SopdSignerResolutionError(
                "Не удалось определить ФИО директора компании-заявителя"
            )
        drafts.append(
            _candidate(
                role="director_applicant",
                full_name=director_name,
                inn=director_inn,
                signing_method="sms",
                source="applicant",
            )
        )
    elif _is_legal_inn(director_inn):
        drafts.extend(
            await _resolve_management_company_director(
                director_inn,
                provider,
                cache,
                max_depth=max_depth,
            )
        )
    elif director_name:
        drafts.append(
            _candidate(
                role="director_applicant",
                full_name=director_name,
                inn=None,
                signing_method="sms",
                source="applicant",
                key=f"director_applicant:{_normalize_name_key(director_name)}",
            )
        )

    for founder in _extract_founders(source_company.get("founders")):
        inn = _normalize_inn(founder.get("inn"))
        share_value = _parse_share_number(_share_raw_value(founder))
        if not _is_physical_inn(inn) or share_value is None or share_value < Decimal("25"):
            continue
        name = _founder_name(founder)
        if not name:
            continue
        drafts.append(
            _candidate(
                role="founder",
                full_name=name,
                inn=inn,
                share=_format_share(share_value),
                signing_method="sms",
                source="applicant",
            )
        )

    deduped = _deduplicate(drafts)
    return [
        SopdSignerCandidate(sort_order=index + 1, **draft.__dict__).to_dict()
        for index, draft in enumerate(deduped)
    ]


async def _resolve_management_company_director(
    inn: str,
    provider: CompanyLookupProvider | None,
    cache: dict[str, dict[str, Any] | None],
    *,
    max_depth: int,
) -> list[_CandidateDraft]:
    if provider is None:
        raise CompanyLookupUnavailableError("Сервис поиска компаний не настроен")

    visited: set[str] = set()
    current_inn = inn
    drafts: list[_CandidateDraft] = []

    for level in range(1, max_depth + 1):
        if current_inn in visited:
            raise SopdSignerResolutionError()
        visited.add(current_inn)

        enriched = await _enrich(current_inn, provider, cache)
        if enriched is None:
            raise SopdSignerResolutionError()
        director_name = _clean_string(enriched.get("director_full_name"))
        director_inn = _normalize_inn(enriched.get("director_inn"))
        if _is_physical_inn(director_inn):
            if not director_name:
                raise SopdSignerResolutionError()
            drafts.append(
                _candidate(
                    role="director_management_company",
                    full_name=director_name,
                    inn=director_inn,
                    signing_method="file",
                    source=f"management_company_level_{level}",
                )
            )
            break
        if _is_legal_inn(director_inn):
            current_inn = director_inn
            continue
        if not director_name:
            raise SopdSignerResolutionError()
        drafts.append(
            _candidate(
                role="director_management_company",
                full_name=director_name,
                inn=None,
                signing_method="file",
                source=f"management_company_level_{level}",
                key=f"director_management_company:{_normalize_name_key(director_name)}",
            )
        )
        break
    else:
        raise SopdSignerResolutionError()

    return drafts


async def _enrich(
    inn: Any,
    provider: CompanyLookupProvider,
    cache: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    normalized_inn = _normalize_inn(inn)
    if not normalized_inn:
        return None
    if normalized_inn in cache:
        return cache[normalized_inn]
    try:
        raw = await provider.enrich_by_inn(normalized_inn)
    except CompanyLookupUnavailableError:
        logger.warning(
            "SOPD signer DaData enrichment failed for INN %s",
            normalized_inn,
            exc_info=True,
        )
        raise
    except Exception as exc:
        logger.warning(
            "SOPD signer DaData enrichment failed for INN %s",
            normalized_inn,
            exc_info=True,
        )
        raise CompanyLookupUnavailableError() from exc

    if raw is None:
        cache[normalized_inn] = None
        return None
    if not isinstance(raw, dict):
        logger.warning(
            "SOPD signer DaData enrichment returned an invalid payload for INN %s",
            normalized_inn,
        )
        raise CompanyLookupUnavailableError(
            "Сервис поиска компаний вернул некорректный ответ"
        )
    cache[normalized_inn] = normalize_dadata_payload(raw)
    return cache[normalized_inn]


def _candidate(
    *,
    role: SignerRole,
    full_name: str,
    inn: str | None,
    signing_method: SigningMethod,
    source: str,
    share: str | None = None,
    key: str | None = None,
) -> _CandidateDraft:
    return _CandidateDraft(
        key=key or inn or f"{role}:{_normalize_name_key(full_name)}",
        role=role,
        role_label=_role_label(role),
        full_name=full_name,
        inn=inn,
        share=share,
        signing_method=signing_method,
        source=source,
    )


def _role_label(role: SignerRole) -> str:
    if role == "director_applicant":
        return "Директор компании-заявителя"
    if role == "director_management_company":
        return "Директор управляющей компании"
    return "Учредитель"


def _deduplicate(drafts: list[_CandidateDraft]) -> list[_CandidateDraft]:
    by_key: dict[str, _CandidateDraft] = {}
    for draft in drafts:
        existing = by_key.get(draft.key)
        if existing is None or _ROLE_PRIORITY[draft.role] < _ROLE_PRIORITY[existing.role]:
            by_key[draft.key] = draft
    return sorted(by_key.values(), key=lambda item: (_ROLE_PRIORITY[item.role], drafts.index(item)))


def _normalize_inn(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_physical_inn(inn: str) -> bool:
    return len(inn) == 12 and inn.isdigit()


def _is_legal_inn(inn: str) -> bool:
    return len(inn) == 10 and inn.isdigit()


def _clean_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _normalize_name_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _decode_json_value(value: Any) -> Any:
    current = value
    for _ in range(2):
        if not isinstance(current, str):
            return current
        trimmed = current.strip()
        if not trimmed:
            return None
        if trimmed[0] not in "[{\"":
            return current
        try:
            current = json.loads(trimmed)
        except (TypeError, ValueError):
            return current
    return current


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _extract_founders(value: Any) -> list[dict[str, Any]]:
    decoded = _decode_json_value(value)
    if isinstance(decoded, list):
        return [item for item in decoded if _is_record(item)]
    if not _is_record(decoded):
        return []
    for key in _FOUNDER_COLLECTION_KEYS:
        nested = _extract_founders(decoded.get(key))
        if nested:
            return nested
    if any(decoded.get(key) is not None for key in _FOUNDER_MARKER_KEYS):
        return [decoded]
    values = [item for item in decoded.values() if _is_record(item)]
    if any(any(item.get(key) is not None for key in _FOUNDER_MARKER_KEYS) for item in values):
        return values
    return []


def _first_string(record: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _founder_name(record: dict[str, Any]) -> str:
    direct = _first_string(record, ["name", "full_name", "fio"])
    if direct:
        return direct
    return " ".join(
        part
        for part in [
            _first_string(record, ["surname", "last_name"]),
            _first_string(record, ["first_name", "name_first"]),
            _first_string(record, ["patronymic", "middle_name"]),
        ]
        if part
    )


def _share_raw_value(record: dict[str, Any]) -> Any:
    for key in ("share", "share_percentage", "percent", "share_percent", "ownership_percent"):
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_share_number(value: Any) -> Decimal | None:  # noqa: PLR0911
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        normalized = value.replace("%", "").replace(",", ".").strip()
        if not normalized:
            return None
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None
    if isinstance(value, dict):
        direct = _parse_share_number(value.get("value") or value.get("percent") or value.get("percentage"))
        if direct is not None:
            return direct
        numerator = _parse_share_number(value.get("numerator"))
        denominator = _parse_share_number(value.get("denominator"))
        if numerator is not None and denominator is not None and denominator != Decimal("0"):
            return (numerator / denominator) * Decimal("100")
    return None


def normalize_sopd_share(value: Any) -> str | None:
    """Keep the candidate percentage contract textual for numeric questionnaire input."""
    parsed = _parse_share_number(value)
    if parsed is None or not parsed.is_finite() or not Decimal("0") <= parsed <= Decimal("100"):
        return None
    return _format_share(parsed)


def _format_share(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.0001")).normalize()
    return format(normalized, "f")
