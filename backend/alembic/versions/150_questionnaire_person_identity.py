"""Normalize questionnaire person UUIDs and preserve legacy source/tombstone paths.

Revision ID: 150
Revises: 149
"""
from copy import deepcopy
from typing import Any
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID

revision = "150"
down_revision = "149"
branch_labels = None
depends_on = None


# Frozen data-migration adapter: intentionally independent from runtime changes.
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


def normalize_stored_people(current: dict[str, Any], application_id: UUID) -> dict[str, Any]:
    """Assign missing UUIDs and migrate every historical source path, including deletes."""
    result = deepcopy(current)
    registry = _identity_map(current.get("people_identity_map"))
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


def upgrade() -> None:
    op.add_column("application_questionnaires", sa.Column(
        "people_identity_map", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"),
    ))
    table = sa.table(
        "application_questionnaires", sa.column("id", PGUUID(as_uuid=True)),
        sa.column("application_id", PGUUID(as_uuid=True)),
        *(sa.column(field, JSONB()) for field in PEOPLE_FIELDS),
        sa.column("field_sources", JSONB()), sa.column("people_identity_map", JSONB()),
    )
    connection = op.get_bind()
    for row in connection.execute(sa.select(table)).mappings():
        before = dict(row)
        normalized = normalize_stored_people(before, row["application_id"])
        values = {field: normalized[field] for field in (*PEOPLE_FIELDS, "field_sources", "people_identity_map")
                  if normalized.get(field) != before.get(field)}
        if values:
            connection.execute(table.update().where(table.c.id == row["id"]).values(**values))


def downgrade() -> None:
    # Person UUIDs and migrated field_sources remain valid on the older schema.
    op.drop_column("application_questionnaires", "people_identity_map")
