from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.section_visibility import (
    InitializeStorefrontSectionVisibilityCommand,
    SectionVisibilityUpdate,
    UpdateSectionVisibilityCommand,
    handle_initialize_storefront_section_visibility,
    handle_update_section_visibility,
)
from application.commands.storefronts import (
    CreateStorefrontCommand,
    handle_create_storefront,
)
from application.errors import ServiceError
from application.queries.section_visibility import (
    GetSectionVisibilityQuery,
    ListSectionVisibilityQuery,
    handle_get_section_visibility,
    handle_list_section_visibility,
)
from domain.section_visibility import (
    GLOBAL_SECTION_VISIBILITY_SCOPES,
    SECTION_DEFAULTS_BY_SCOPE,
    STOREFRONT_SECTION_VISIBILITY_SCOPES,
    TARGET_SECTION_VISIBILITY_SCOPES,
    InvalidSectionVisibilityKeyError,
    InvalidSectionVisibilityScopeError,
    InvalidSectionVisibilityTargetError,
    get_section_visibility_defaults,
    validate_section_visibility_key,
    validate_section_visibility_scope,
    validate_section_visibility_target,
)
from domain.storefronts import DEFAULT_STOREFRONT_ID
from infrastructure.auth import generate_tokens
from infrastructure.models.section_visibility import SectionVisibility
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories.section_visibility_repository import (
    list_visibility_overrides,
    upsert_visibility_overrides,
)

pytestmark = pytest.mark.asyncio


EXPECTED_DEFAULTS: dict[str, dict[str, bool]] = {
    "public": {
        "about": True,
        "catalog": True,
        "models": False,
        "model_brand_selection": True,
        "cars_brand_filter": True,
        "special_equipment_catalog": False,
    },
    "carcraft_employee": {
        "monetization": True,
        "special_equipment_import": False,
        "special_equipment_catalog": False,
    },
    "leasing_company": {
        "monetization": True,
        "leasing_applications": True,
        "documents": True,
        "document_requirements": True,
        "support": True,
        "exchange": True,
        "leasing_analytics": True,
        "security": True,
        "employees": True,
    },
    "dealer": {
        "monetization": True,
        "applications": True,
        "clients": True,
        "inventory": True,
        "reports": True,
        "distributor_analytics": True,
        "exchange": True,
        "support": True,
        "employees": True,
    },
    "distributor": {
        "monetization": True,
        "exchange": True,
        "applications": True,
        "warehouses": True,
        "distributor_analytics": True,
        "dealers": True,
        "companies": True,
        "support": True,
        "catalog": True,
        "employees": True,
    },
}


def _auth(token: str, *, csrf: bool = False) -> dict[str, str]:
    cookie = f"accessToken={token}"
    headers: dict[str, str] = {}
    if csrf:
        cookie += "; csrfToken=test-csrf-token"
        headers["X-CSRF-Token"] = "test-csrf-token"
    headers["Cookie"] = cookie
    return headers


async def _create_role_user(
    session: AsyncSession,
    *,
    role: str,
    suffix: str,
) -> tuple[User, str]:
    user = User(
        phone=f"+7666999{suffix}",
        email=f"section-visibility-{suffix}@test.local",
        name=f"Section visibility {role}",
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    token, _ = generate_tokens(user.id, role, None)
    return user, token


def _section_map(payload: Mapping[str, object]) -> dict[str, bool]:
    sections = payload["sections"]
    assert isinstance(sections, list)
    return {
        str(item["key"]): bool(item["is_visible"])
        for item in sections
        if isinstance(item, dict)
    }


def _rows_by_key(
    rows: Iterable[dict[str, object]],
) -> dict[str, dict[str, object]]:
    return {str(row["section_key"]): row for row in rows}


async def test_section_visibility_catalog_preserves_current_defaults() -> None:
    assert tuple(EXPECTED_DEFAULTS) == TARGET_SECTION_VISIBILITY_SCOPES
    assert SECTION_DEFAULTS_BY_SCOPE == EXPECTED_DEFAULTS

    for scope, expected in EXPECTED_DEFAULTS.items():
        actual = get_section_visibility_defaults(scope)
        assert actual == expected
        assert "profile" not in actual
        assert len(actual) == len(set(actual))


async def test_section_visibility_catalog_rejects_unknown_scope_and_key() -> None:
    with pytest.raises(InvalidSectionVisibilityScopeError):
        validate_section_visibility_scope("client")
    with pytest.raises(InvalidSectionVisibilityKeyError):
        validate_section_visibility_key("public", "profile")
    with pytest.raises(InvalidSectionVisibilityKeyError):
        validate_section_visibility_key("dealer", "documents")


@pytest.mark.parametrize(
    "scope",
    ["public", "leasing_company", "dealer", "distributor"],
)
async def test_section_visibility_target_requires_storefront_for_scoped_areas(
    scope: str,
) -> None:
    assert validate_section_visibility_target(scope, DEFAULT_STOREFRONT_ID) == (
        scope,
        DEFAULT_STOREFRONT_ID,
    )

    with pytest.raises(InvalidSectionVisibilityTargetError):
        validate_section_visibility_target(scope, None)


async def test_section_visibility_target_keeps_only_employee_global() -> None:
    assert GLOBAL_SECTION_VISIBILITY_SCOPES == ("carcraft_employee",)
    assert validate_section_visibility_target("carcraft_employee", None) == (
        "carcraft_employee",
        None,
    )

    with pytest.raises(InvalidSectionVisibilityTargetError):
        validate_section_visibility_target(
            "carcraft_employee",
            DEFAULT_STOREFRONT_ID,
        )


async def test_custom_storefront_can_enable_special_equipment_catalog() -> None:
    custom_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    assert validate_section_visibility_target("public", custom_id) == (
        "public",
        custom_id,
    )
    assert validate_section_visibility_key(
        "public",
        "special_equipment_catalog",
    ) == "special_equipment_catalog"


async def test_repository_upserts_only_requested_overrides_and_keeps_uuid_actor(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    await upsert_visibility_overrides(
        db_session,
        "public",
        {"models": True, "special_equipment_catalog": True},
        employee_user.id,
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    await upsert_visibility_overrides(
        db_session,
        "public",
        {"models": False},
        employee_user.id,
        storefront_id=DEFAULT_STOREFRONT_ID,
    )

    rows = await list_visibility_overrides(
        db_session,
        ["public"],
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    by_key = _rows_by_key(rows)
    assert set(by_key) == {"models", "special_equipment_catalog"}
    assert by_key["models"]["is_visible"] is False
    assert by_key["special_equipment_catalog"]["is_visible"] is True

    persisted = (
        (
            await db_session.execute(
                select(SectionVisibility).where(SectionVisibility.scope == "public")
            )
        )
        .scalars()
        .all()
    )
    assert {row.section_key for row in persisted} == {
        "models",
        "special_equipment_catalog",
    }
    assert all(row.updated_by == employee_user.id for row in persisted)


async def test_repository_keeps_public_storefronts_independent(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom = Storefront(slug="visibility-child", is_default=False, is_active=True)
    db_session.add(custom)
    await db_session.flush()

    await upsert_visibility_overrides(
        db_session,
        "public",
        {"models": True},
        employee_user.id,
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    await upsert_visibility_overrides(
        db_session,
        "public",
        {"models": False},
        employee_user.id,
        storefront_id=custom.id,
    )

    root_rows = await list_visibility_overrides(
        db_session,
        ["public"],
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    custom_rows = await list_visibility_overrides(
        db_session,
        ["public"],
        storefront_id=custom.id,
    )

    assert _rows_by_key(root_rows)["models"]["is_visible"] is True
    assert _rows_by_key(custom_rows)["models"]["is_visible"] is False
    assert root_rows[0]["storefront_id"] == DEFAULT_STOREFRONT_ID
    assert custom_rows[0]["storefront_id"] == custom.id


async def test_repository_keeps_business_role_storefronts_independent(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom = Storefront(
        slug="visibility-role-child",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    await upsert_visibility_overrides(
        db_session,
        "dealer",
        {"applications": False},
        employee_user.id,
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    await upsert_visibility_overrides(
        db_session,
        "dealer",
        {"applications": True},
        employee_user.id,
        storefront_id=custom.id,
    )

    root_rows = await list_visibility_overrides(
        db_session,
        ["dealer"],
        storefront_id=DEFAULT_STOREFRONT_ID,
    )
    custom_rows = await list_visibility_overrides(
        db_session,
        ["dealer"],
        storefront_id=custom.id,
    )

    assert _rows_by_key(root_rows)["applications"]["is_visible"] is False
    assert _rows_by_key(custom_rows)["applications"]["is_visible"] is True


async def test_persistence_enforces_partial_uniqueness_and_target_shape(
    db_session: AsyncSession,
) -> None:
    custom = Storefront(
        slug="visibility-constraints",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    async def assert_rejected(values: list[dict[str, object]]) -> None:
        nested = await db_session.begin_nested()
        try:
            with pytest.raises(IntegrityError):
                await db_session.execute(
                    sa.insert(SectionVisibility),
                    values,
                )
        finally:
            await nested.rollback()

    await assert_rejected(
        [
            {
                "scope": "public",
                "storefront_id": custom.id,
                "section_key": "about",
                "is_visible": True,
            },
            {
                "scope": "public",
                "storefront_id": custom.id,
                "section_key": "about",
                "is_visible": False,
            },
        ]
    )
    await assert_rejected(
        [
            {
                "scope": "dealer",
                "storefront_id": custom.id,
                "section_key": "applications",
                "is_visible": True,
            },
            {
                "scope": "dealer",
                "storefront_id": custom.id,
                "section_key": "applications",
                "is_visible": False,
            },
        ]
    )
    await assert_rejected(
        [
            {
                "scope": "public",
                "storefront_id": None,
                "section_key": "catalog",
                "is_visible": True,
            }
        ]
    )
    await assert_rejected(
        [
            {
                "scope": "dealer",
                "storefront_id": None,
                "section_key": "applications",
                "is_visible": True,
            }
        ]
    )


async def test_handlers_merge_scope_defaults_and_partial_updates(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    initial = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope="public",
            storefront_id=DEFAULT_STOREFRONT_ID,
        ),
        db_session,
    )
    assert initial["scope"] == "public"
    assert initial["storefront_id"] == DEFAULT_STOREFRONT_ID
    assert _section_map(initial) == EXPECTED_DEFAULTS["public"]

    updated = await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="public",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(SectionVisibilityUpdate(key="models", is_visible=True),),
            updated_by=employee_user.id,
        ),
        db_session,
    )
    assert _section_map(updated) == {
        **EXPECTED_DEFAULTS["public"],
        "models": True,
    }

    global_list = await handle_list_section_visibility(
        ListSectionVisibilityQuery(),
        db_session,
    )
    assert [item["scope"] for item in global_list["items"]] == [
        "carcraft_employee"
    ]
    assert (
        _section_map(global_list["items"][0])
        == EXPECTED_DEFAULTS["carcraft_employee"]
    )
    assert global_list["items"][0]["storefront_id"] is None

    storefront_list = await handle_list_section_visibility(
        ListSectionVisibilityQuery(storefront_id=DEFAULT_STOREFRONT_ID),
        db_session,
    )
    by_scope = {item["scope"]: item for item in storefront_list["items"]}
    assert tuple(by_scope) == STOREFRONT_SECTION_VISIBILITY_SCOPES
    assert _section_map(by_scope["public"])["models"] is True
    assert _section_map(by_scope["dealer"]) == EXPECTED_DEFAULTS["dealer"]
    assert all(
        item["storefront_id"] == DEFAULT_STOREFRONT_ID
        for item in storefront_list["items"]
    )


async def test_handlers_keep_business_role_storefronts_independent(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom = Storefront(
        slug="visibility-handler-child",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    root = await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="leasing_company",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(
                SectionVisibilityUpdate(key="documents", is_visible=False),
            ),
            updated_by=employee_user.id,
        ),
        db_session,
    )
    custom_matrix = await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="leasing_company",
            storefront_id=custom.id,
            sections=(
                SectionVisibilityUpdate(key="documents", is_visible=True),
            ),
            updated_by=employee_user.id,
        ),
        db_session,
    )

    assert _section_map(root)["documents"] is False
    assert _section_map(custom_matrix)["documents"] is True
    assert root["storefront_id"] == DEFAULT_STOREFRONT_ID
    assert custom_matrix["storefront_id"] == custom.id


async def test_new_storefront_copies_default_public_snapshot_then_stays_independent(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    warehouse = Warehouse(
        address="Visibility warehouse",
        brand="Visibility",
        status="active",
    )
    db_session.add(warehouse)
    await db_session.flush()
    await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="public",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(
                SectionVisibilityUpdate(key="models", is_visible=True),
                SectionVisibilityUpdate(
                    key="model_brand_selection",
                    is_visible=False,
                ),
                SectionVisibilityUpdate(
                    key="special_equipment_catalog",
                    is_visible=True,
                ),
            ),
            updated_by=employee_user.id,
        ),
        db_session,
    )
    for scope, section_key in (
        ("leasing_company", "documents"),
        ("distributor", "support"),
    ):
        await handle_update_section_visibility(
            UpdateSectionVisibilityCommand(
                scope=scope,
                storefront_id=DEFAULT_STOREFRONT_ID,
                sections=(
                    SectionVisibilityUpdate(
                        key=section_key,
                        is_visible=False,
                    ),
                ),
                updated_by=employee_user.id,
            ),
            db_session,
        )
    await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="dealer",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(
                SectionVisibilityUpdate(key="applications", is_visible=False),
            ),
            updated_by=employee_user.id,
        ),
        db_session,
    )

    storefront = await handle_create_storefront(
        CreateStorefrontCommand(
            slug="visibility-copy",
            warehouse_ids=(warehouse.id,),
            created_by=employee_user.id,
        ),
        db_session,
    )
    copied = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope="public",
            storefront_id=storefront["id"],
        ),
        db_session,
    )
    assert _section_map(copied) == {
        "about": True,
        "catalog": True,
        "models": True,
        "model_brand_selection": False,
        "cars_brand_filter": True,
        "special_equipment_catalog": True,
    }
    copied_dealer = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope="dealer",
            storefront_id=storefront["id"],
        ),
        db_session,
    )
    assert _section_map(copied_dealer) == {
        **EXPECTED_DEFAULTS["dealer"],
        "applications": False,
    }
    copied_matrices = await handle_list_section_visibility(
        ListSectionVisibilityQuery(storefront_id=storefront["id"]),
        db_session,
    )
    copied_by_scope = {
        matrix["scope"]: _section_map(matrix)
        for matrix in copied_matrices["items"]
    }
    assert copied_by_scope["leasing_company"]["documents"] is False
    assert copied_by_scope["distributor"]["support"] is False

    await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="public",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(SectionVisibilityUpdate(key="about", is_visible=False),),
            updated_by=employee_user.id,
        ),
        db_session,
    )
    await handle_update_section_visibility(
        UpdateSectionVisibilityCommand(
            scope="dealer",
            storefront_id=DEFAULT_STOREFRONT_ID,
            sections=(
                SectionVisibilityUpdate(key="applications", is_visible=True),
            ),
            updated_by=employee_user.id,
        ),
        db_session,
    )
    unchanged = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope="public",
            storefront_id=storefront["id"],
        ),
        db_session,
    )
    assert _section_map(unchanged)["about"] is True
    unchanged_dealer = await handle_get_section_visibility(
        GetSectionVisibilityQuery(
            scope="dealer",
            storefront_id=storefront["id"],
        ),
        db_session,
    )
    assert _section_map(unchanged_dealer)["applications"] is False


async def test_initialize_storefront_visibility_is_a_write_only_command(
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom = Storefront(
        slug="visibility-write-only",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    await handle_initialize_storefront_section_visibility(
        InitializeStorefrontSectionVisibilityCommand(
            storefront_id=custom.id,
            updated_by=employee_user.id,
        ),
        db_session,
    )
    matrices = await handle_list_section_visibility(
        ListSectionVisibilityQuery(storefront_id=custom.id),
        db_session,
    )

    assert [item["scope"] for item in matrices["items"]] == list(
        STOREFRONT_SECTION_VISIBILITY_SCOPES
    )
    assert all(
        _section_map(matrix) == EXPECTED_DEFAULTS[matrix["scope"]]
        for matrix in matrices["items"]
    )


@pytest.mark.parametrize(
    "command",
    [
        UpdateSectionVisibilityCommand(
            scope="client",
            sections=(SectionVisibilityUpdate(key="about", is_visible=False),),
            updated_by=UUID("00000000-0000-0000-0000-000000000001"),
        ),
        UpdateSectionVisibilityCommand(
            scope="public",
            sections=(
                SectionVisibilityUpdate(key="unknown_key", is_visible=False),
            ),
            updated_by=UUID("00000000-0000-0000-0000-000000000001"),
        ),
        UpdateSectionVisibilityCommand(
            scope="public",
            sections=(),
            updated_by=UUID("00000000-0000-0000-0000-000000000001"),
        ),
        UpdateSectionVisibilityCommand(
            scope="public",
            sections=(
                SectionVisibilityUpdate(key="about", is_visible=False),
                SectionVisibilityUpdate(key="about", is_visible=True),
            ),
            updated_by=UUID("00000000-0000-0000-0000-000000000001"),
        ),
    ],
)
async def test_update_handler_rejects_invalid_or_ambiguous_commands(
    db_session: AsyncSession,
    command: UpdateSectionVisibilityCommand,
) -> None:
    with pytest.raises(ServiceError) as exc_info:
        await handle_update_section_visibility(command, db_session)

    assert exc_info.value.status_code == 422


async def test_public_endpoint_needs_no_auth_and_returns_safe_defaults(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/section-visibility/public")

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == "public"
    assert response.json()["storefront_id"] == str(DEFAULT_STOREFRONT_ID)
    assert _section_map(response.json()) == EXPECTED_DEFAULTS["public"]


async def test_custom_public_endpoint_is_independent_from_root(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    custom = Storefront(
        slug="visibility-http",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()
    await upsert_visibility_overrides(
        db_session,
        "public",
        {"about": False, "models": True},
        employee_user.id,
        storefront_id=custom.id,
    )

    custom_response = await client.get(
        "/api/v1/storefronts/visibility-http/section-visibility/public"
    )
    root_response = await client.get("/api/v1/section-visibility/public")

    assert custom_response.status_code == 200, custom_response.text
    assert custom_response.json()["scope"] == "public"
    assert custom_response.json()["storefront_id"] == str(custom.id)
    assert _section_map(custom_response.json()) == {
        **EXPECTED_DEFAULTS["public"],
        "about": False,
        "models": True,
    }
    assert root_response.status_code == 200, root_response.text
    assert root_response.json()["storefront_id"] == str(DEFAULT_STOREFRONT_ID)
    assert _section_map(root_response.json()) == EXPECTED_DEFAULTS["public"]


@pytest.mark.parametrize("slug", ["missing-visibility", "inactive-visibility"])
async def test_custom_public_endpoint_hides_missing_and_inactive_storefronts(
    client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
) -> None:
    if slug == "inactive-visibility":
        db_session.add(
            Storefront(slug=slug, is_default=False, is_active=False)
        )
        await db_session.flush()

    response = await client.get(
        f"/api/v1/storefronts/{slug}/section-visibility/public"
    )

    assert response.status_code == 404, response.text


@pytest.mark.parametrize(
    ("role", "suffix"),
    [
        ("carcraft_employee", "0100"),
        ("leasing_company", "0101"),
        ("dealer", "0102"),
        ("distributor", "0103"),
    ],
)
async def test_workspace_endpoint_returns_current_scope_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
    role: str,
    suffix: str,
) -> None:
    _, token = await _create_role_user(db_session, role=role, suffix=suffix)

    response = await client.get(
        "/api/v1/workspace/section-visibility",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == role
    expected_storefront_id = (
        None
        if role == "carcraft_employee"
        else str(DEFAULT_STOREFRONT_ID)
    )
    assert response.json()["storefront_id"] == expected_storefront_id
    assert _section_map(response.json()) == EXPECTED_DEFAULTS[role]


@pytest.mark.parametrize(
    ("role", "suffix"),
    [
        ("leasing_company", "0104"),
        ("dealer", "0105"),
        ("distributor", "0106"),
    ],
)
async def test_custom_workspace_endpoint_uses_active_storefront_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
    role: str,
    suffix: str,
) -> None:
    custom = Storefront(
        slug=f"visibility-workspace-{role.replace('_', '-')}",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()
    section_key = next(iter(EXPECTED_DEFAULTS[role]))
    await upsert_visibility_overrides(
        db_session,
        role,
        {section_key: False},
        employee_user.id,
        storefront_id=custom.id,
    )
    _, token = await _create_role_user(db_session, role=role, suffix=suffix)

    response = await client.get(
        f"/api/v1/storefronts/{custom.slug}/workspace/section-visibility",
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == role
    assert response.json()["storefront_id"] == str(custom.id)
    assert _section_map(response.json())[section_key] is False


@pytest.mark.parametrize("slug", ["missing-workspace", "inactive-workspace"])
async def test_custom_workspace_endpoint_hides_missing_and_inactive_storefronts(
    client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
) -> None:
    if slug == "inactive-workspace":
        db_session.add(Storefront(slug=slug, is_default=False, is_active=False))
        await db_session.flush()
    _, token = await _create_role_user(
        db_session,
        role="dealer",
        suffix="0110" if slug.startswith("missing") else "0112",
    )

    response = await client.get(
        f"/api/v1/storefronts/{slug}/workspace/section-visibility",
        headers=_auth(token),
    )

    assert response.status_code == 404, response.text


async def test_employee_workspace_visibility_stays_global_under_custom_slug(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    custom = Storefront(
        slug="visibility-employee-context",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/storefronts/{custom.slug}/workspace/section-visibility",
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["scope"] == "carcraft_employee"
    assert response.json()["storefront_id"] is None


async def test_workspace_endpoint_rejects_a_non_workspace_role(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.get(
        "/api/v1/workspace/section-visibility",
        headers=_auth(client_token),
    )

    assert response.status_code == 403


async def test_admin_patch_updates_public_and_employee_navigation(
    client: AsyncClient,
    employee_token: str,
) -> None:
    public_response = await client.patch(
        f"/api/v1/admin/storefronts/{DEFAULT_STOREFRONT_ID}"
        "/section-visibility/public",
        headers=_auth(employee_token, csrf=True),
        json={
            "sections": [
                {"key": "models", "is_visible": True},
                {"key": "model_brand_selection", "is_visible": False},
            ]
        },
    )
    employee_response = await client.patch(
        "/api/v1/admin/section-visibility/carcraft_employee",
        headers=_auth(employee_token, csrf=True),
        json={
            "sections": [
                {"key": "special_equipment_import", "is_visible": True}
            ]
        },
    )

    assert public_response.status_code == 200, public_response.text
    assert _section_map(public_response.json())["models"] is True
    assert (
        _section_map(public_response.json())["model_brand_selection"] is False
    )
    assert employee_response.status_code == 200, employee_response.text
    assert (
        _section_map(employee_response.json())["special_equipment_import"] is True
    )

    public_matrix = await client.get("/api/v1/section-visibility/public")
    employee_matrix = await client.get(
        "/api/v1/workspace/section-visibility",
        headers=_auth(employee_token),
    )
    assert _section_map(public_matrix.json())["models"] is True
    assert _section_map(public_matrix.json())["model_brand_selection"] is False
    assert (
        _section_map(employee_matrix.json())["special_equipment_import"] is True
    )


async def test_admin_patch_preserves_untouched_business_sections(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    employee_user: User,
) -> None:
    _, leasing_token = await _create_role_user(
        db_session,
        role="leasing_company",
        suffix="0111",
    )
    for key in ("documents", "exchange"):
        response = await client.patch(
            f"/api/v1/admin/storefronts/{DEFAULT_STOREFRONT_ID}"
            "/section-visibility/leasing_company",
            headers=_auth(employee_token, csrf=True),
            json={"sections": [{"key": key, "is_visible": False}]},
        )
        assert response.status_code == 200, response.text

    own = await client.get(
        "/api/v1/workspace/section-visibility",
        headers=_auth(leasing_token),
    )
    visibility = _section_map(own.json())
    assert visibility["documents"] is False
    assert visibility["exchange"] is False
    assert visibility["leasing_applications"] is True

    rows = (
        (
            await db_session.execute(
                select(SectionVisibility).where(
                    SectionVisibility.scope == "leasing_company"
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.section_key for row in rows} == {"documents", "exchange"}
    assert all(row.updated_by == employee_user.id for row in rows)


async def test_admin_business_patch_keeps_root_and_custom_storefront_independent(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    custom = Storefront(
        slug="visibility-business-admin",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    updated = await client.patch(
        f"/api/v1/admin/storefronts/{custom.id}"
        "/section-visibility/distributor",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "support", "is_visible": False}]},
    )
    _, distributor_token = await _create_role_user(
        db_session,
        role="distributor",
        suffix="0113",
    )
    root = await client.get(
        "/api/v1/workspace/section-visibility",
        headers=_auth(distributor_token),
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["storefront_id"] == str(custom.id)
    assert _section_map(updated.json())["support"] is False
    assert root.status_code == 200, root.text
    assert root.json()["storefront_id"] == str(DEFAULT_STOREFRONT_ID)
    assert _section_map(root.json())["support"] is True


async def test_admin_global_list_returns_only_employee_defaults(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.get(
        "/api/v1/admin/section-visibility",
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [item["scope"] for item in items] == ["carcraft_employee"]
    assert items[0]["storefront_id"] is None
    assert _section_map(items[0]) == EXPECTED_DEFAULTS["carcraft_employee"]


async def test_admin_storefront_resource_lists_four_scopes_and_allows_inactive_patch(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    custom = Storefront(
        slug="visibility-inactive-admin",
        is_default=False,
        is_active=False,
    )
    db_session.add(custom)
    await db_session.flush()

    initial = await client.get(
        f"/api/v1/admin/storefronts/{custom.id}/section-visibility",
        headers=_auth(employee_token),
    )
    updated = await client.patch(
        f"/api/v1/admin/storefronts/{custom.id}/section-visibility/public",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "catalog", "is_visible": False}]},
    )
    root = await client.get("/api/v1/section-visibility/public")

    assert initial.status_code == 200, initial.text
    items = initial.json()["items"]
    assert [item["scope"] for item in items] == list(
        STOREFRONT_SECTION_VISIBILITY_SCOPES
    )
    assert all(item["storefront_id"] == str(custom.id) for item in items)
    assert updated.status_code == 200, updated.text
    assert updated.json()["storefront_id"] == str(custom.id)
    assert _section_map(updated.json())["catalog"] is False
    assert _section_map(root.json())["catalog"] is True


async def test_admin_public_resource_allows_enabling_custom_special_equipment(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    custom = Storefront(
        slug="visibility-special-equipment",
        is_default=False,
        is_active=True,
    )
    db_session.add(custom)
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/admin/storefronts/{custom.id}/section-visibility/public",
        headers=_auth(employee_token, csrf=True),
        json={
            "sections": [
                {
                    "key": "special_equipment_catalog",
                    "is_visible": True,
                }
            ]
        },
    )

    assert response.status_code == 200, response.text
    assert _section_map(response.json())["special_equipment_catalog"] is True


async def test_admin_public_resource_rejects_unknown_storefront(
    client: AsyncClient,
    employee_token: str,
) -> None:
    missing_id = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")

    response = await client.get(
        f"/api/v1/admin/storefronts/{missing_id}/section-visibility",
        headers=_auth(employee_token),
    )

    assert response.status_code == 404, response.text


async def test_admin_visibility_endpoints_are_employee_only(
    client: AsyncClient,
    client_token: str,
) -> None:
    listed = await client.get(
        "/api/v1/admin/section-visibility",
        headers=_auth(client_token),
    )
    patched = await client.patch(
        f"/api/v1/admin/storefronts/{DEFAULT_STOREFRONT_ID}"
        "/section-visibility/public",
        headers=_auth(client_token, csrf=True),
        json={"sections": [{"key": "about", "is_visible": False}]},
    )

    assert listed.status_code == 403
    assert patched.status_code == 403


@pytest.mark.parametrize(
    ("scope", "sections"),
    [
        ("unknown_scope", [{"key": "about", "is_visible": False}]),
        ("public", [{"key": "unknown_key", "is_visible": False}]),
        ("dealer", [{"key": "documents", "is_visible": False}]),
    ],
)
async def test_admin_patch_rejects_unknown_scope_or_section_key(
    client: AsyncClient,
    employee_token: str,
    scope: str,
    sections: list[dict[str, object]],
) -> None:
    response = await client.patch(
        f"/api/v1/admin/section-visibility/{scope}",
        headers=_auth(employee_token, csrf=True),
        json={"sections": sections},
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize("scope", ["carcraft_employee", "unknown_scope"])
async def test_admin_storefront_patch_rejects_global_or_unknown_scope(
    client: AsyncClient,
    employee_token: str,
    scope: str,
) -> None:
    response = await client.patch(
        f"/api/v1/admin/storefronts/{DEFAULT_STOREFRONT_ID}"
        f"/section-visibility/{scope}",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "catalog", "is_visible": False}]},
    )

    assert response.status_code == 422, response.text


async def test_old_admin_visibility_urls_are_not_kept_as_wrappers(
    client: AsyncClient,
    employee_token: str,
) -> None:
    listed = await client.get(
        "/api/v1/admin/workspace-section-visibility",
        headers=_auth(employee_token),
    )
    patched = await client.patch(
        "/api/v1/admin/workspace-section-visibility/leasing_company",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "documents", "is_visible": False}]},
    )

    assert listed.status_code == 404
    assert patched.status_code == 404


async def test_public_only_admin_patch_without_scope_is_removed(
    client: AsyncClient,
    employee_token: str,
) -> None:
    response = await client.patch(
        f"/api/v1/admin/storefronts/{DEFAULT_STOREFRONT_ID}/section-visibility",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "catalog", "is_visible": False}]},
    )

    assert response.status_code == 405, response.text


async def test_cars_brand_filter_persists_independently_and_roundtrips_transfer(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    employee_user: User,
) -> None:
    from application.queries.storefront_transfer import (
        handle_export_storefront_settings,
    )
    from domain.storefront_transfer import parse_storefront_settings
    from infrastructure.repositories.storefront_transfer_repository import (
        replace_transfer_visibility,
    )
    from tests.fakes.object_storage import FakeObjectStorage

    custom = Storefront(slug="brand-filter-transfer", is_active=True)
    db_session.add(custom)
    await db_session.flush()
    public_url = f"/api/v1/storefronts/{custom.slug}/section-visibility/public"
    initial = await client.get(public_url)
    assert initial.status_code == 200, initial.text
    assert _section_map(initial.json())["cars_brand_filter"] is True
    changed = await client.patch(
        f"/api/v1/admin/storefronts/{custom.id}/section-visibility/public",
        headers=_auth(employee_token, csrf=True),
        json={"sections": [{"key": "cars_brand_filter", "is_visible": False}]},
    )
    assert changed.status_code == 200, changed.text
    reloaded = await client.get(public_url)
    assert _section_map(reloaded.json())["cars_brand_filter"] is False
    assert _section_map(reloaded.json())["model_brand_selection"] is True
    root = await client.get("/api/v1/section-visibility/public")
    assert _section_map(root.json())["cars_brand_filter"] is True
    exported = await handle_export_storefront_settings(db_session, FakeObjectStorage())
    items = parse_storefront_settings(exported)
    assert custom.slug is not None
    visibility = items[custom.slug].section_visibility
    assert visibility["public"]["cars_brand_filter"] is False
    assert "cars_brand_filter" not in items["/"].section_visibility["public"]
    await replace_transfer_visibility(db_session, custom.id, visibility, employee_user.id)
    imported = await client.get(public_url)
    assert _section_map(imported.json())["cars_brand_filter"] is False
    await replace_transfer_visibility(
        db_session, custom.id, items["/"].section_visibility, employee_user.id,
    )
    legacy_import = await client.get(public_url)
    assert _section_map(legacy_import.json())["cars_brand_filter"] is True
