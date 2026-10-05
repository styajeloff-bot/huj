"""Adapt legacy person records to persistent UUIDs before questionnaire merging.

Aliases are correlation evidence at the import boundary, never merge keys. Keeping
that evidence after deletion lets a UUID tombstone stop the same provider person
from reappearing. Ambiguous aliases intentionally do not identify a person.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4, uuid5

PEOPLE_FIELDS = ("founders", "beneficiaries", "other_representatives")
IdentityMap = dict[str, dict[str, list[str]]]


def _uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value))) if value is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _aliases(person: dict[str, Any]) -> set[str]:
    aliases = set()
    for field, prefix in (("id", "id"), ("inn", "inn"), ("signer_key", "signer")):
        value = _text(person.get(field))
        if value:
            aliases.add(f"{prefix}/{value}")
    if not person.get("inn") and not person.get("signer_key"):
        for field in ("name", "full_name"):
            value = " ".join(_text(person.get(field)).casefold().split())
            if value:
                aliases.add(f"name/{value}")
    return aliases


def _remember(aliases: dict[str, list[str]], alias: str, identifier: str) -> None:
    values = aliases.setdefault(alias, [])
    if identifier not in values:
        values.append(identifier)


def _remember_person(aliases: dict[str, list[str]], person: dict[str, Any]) -> None:
    for alias in _aliases(person):
        _remember(aliases, alias, person["id"])


def _legacy_key(person: dict[str, Any], index: int) -> str:
    """Interpret only the historical storage format for a one-time path migration."""
    for field in ("id", "signer_key", "inn"):
        if person.get(field):
            return str(person[field])
    return str(index)


def _legacy_uuid(application_id: UUID, field: str, token: str) -> str:
    return str(uuid5(application_id, f"questionnaire-person/{field}/legacy/{token}"))


def _remember_legacy(aliases: dict[str, list[str]], token: str, identifier: str) -> None:
    _remember(aliases, f"legacy/{token}", identifier)
    if token.isdigit() and len(token) in (10, 12):
        _remember(aliases, f"inn/{token}", identifier)
    elif ":" in token:
        _remember(aliases, f"signer/{token}", identifier)
    elif _uuid(token):
        _remember(aliases, f"id/{token}", identifier)


def _identity_map(value: Any) -> IdentityMap:
    result: IdentityMap = {field: {} for field in PEOPLE_FIELDS}
    if not isinstance(value, dict):
        return result
    for field in PEOPLE_FIELDS:
        raw = value.get(field)
        if isinstance(raw, dict):
            for alias, identifiers in raw.items():
                if isinstance(identifiers, list):
                    for identifier in identifiers:
                        valid = _uuid(identifier)
                        if valid:
                            _remember(result[field], str(alias), valid)
    return result


def _stored_paths(
    result: dict[str, Any], registry: IdentityMap, application_id: UUID,
) -> dict[str, dict[str, list[str]]]:
    paths: dict[str, dict[str, list[str]]] = {field: {} for field in PEOPLE_FIELDS}
    for field in PEOPLE_FIELDS:
        records = result.get(field)
        if not isinstance(records, list):
            continue
        used: set[str] = set()
        for index, person in enumerate(records):
            if not isinstance(person, dict):
                continue
            token = _legacy_key(person, index)
            identifier = _uuid(person.get("id"))
            if identifier is None:
                identifier = _legacy_uuid(application_id, field, token)
            if identifier in used:
                identifier = _legacy_uuid(application_id, field, f"{token}/duplicate/{index}")
            used.add(identifier)
            person["id"] = identifier
            _remember_legacy(registry[field], token, identifier)
            _remember_person(registry[field], person)
    for field, aliases in registry.items():
        for alias, identifiers in aliases.items():
            kind, _, token = alias.partition("/")
            if kind in {"id", "legacy", "inn", "signer"}:
                for identifier in identifiers:
                    _remember(paths[field], token, identifier)
    return paths


def normalize_stored_people(current: dict[str, Any], application_id: UUID) -> dict[str, Any]:
    """Assign missing UUIDs and migrate every historical source path, including deletes."""
    result = deepcopy(current)
    registry = _identity_map(current.get("people_identity_map"))
    paths = _stored_paths(result, registry, application_id)
    sources: dict[str, str] = {}
    for path, source in (current.get("field_sources") or {}).items():
        field, dot, tail = path.partition(".")
        if field not in PEOPLE_FIELDS or not dot:
            sources[path] = source
            continue
        tokens = [token for token in paths[field] if tail == token or tail.startswith(token + ".")]
        if tokens:
            token = max(tokens, key=len)
            identifiers = paths[field][token]
        else:
            token = tail.split(".", 1)[0]
            identifier = _uuid(token)
            if identifier is None:
                identifier = _legacy_uuid(application_id, field, token)
            identifiers = [identifier]
            _remember_legacy(registry[field], token, identifier)
        suffix = tail[len(token):]
        for identifier in identifiers:
            target = f"{field}.{identifier}{suffix}"
            if sources.get(target) not in {"manual", "document_request"}:
                sources[target] = source
    result["field_sources"] = sources
    result["people_identity_map"] = registry
    return result


def _resolve_import(person: dict[str, Any], aliases: dict[str, list[str]]) -> str | None:
    """Correlate a provider/legacy record only when its evidence is unambiguous."""
    identifier = _uuid(person.get("id"))
    if identifier and len(aliases.get(f"id/{identifier}", [])) == 1:
        return aliases[f"id/{identifier}"][0]
    matches = {identifier for alias in _aliases(person) for identifier in aliases.get(alias, [])}
    return next(iter(matches)) if len(matches) == 1 else None


def normalize_incoming_people(
    current: dict[str, Any], payload: dict[str, Any], *, explicit: bool,
) -> tuple[dict[str, Any], IdentityMap]:
    """Normalize the import once; the merge itself only consumes canonical UUIDs."""
    result = deepcopy(payload)
    registry = _identity_map(current.get("people_identity_map"))
    for field in PEOPLE_FIELDS:
        records = result.get(field)
        if not isinstance(records, list):
            continue
        normalized = []
        seen: set[str] = set()
        for person in records:
            if not isinstance(person, dict):
                continue
            original = deepcopy(person)
            identifier = _uuid(person.get("id"))
            if not explicit or identifier is None:
                resolved = _resolve_import(person, registry[field])
                if resolved is not None:
                    identifier = resolved
            if identifier is None:
                identifier = str(uuid4())
            person["id"] = identifier
            for alias in _aliases(original):
                _remember(registry[field], alias, identifier)
            _remember_person(registry[field], person)
            if identifier not in seen:
                normalized.append(person)
                seen.add(identifier)
        result[field] = normalized
    return result, registry
