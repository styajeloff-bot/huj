"""Unit and integration tests for special equipment import image URL parsing, normalization, transfer, and apply."""

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application import special_equipment_import_v2 as import_v2
from application.tasks import special_equipment_import as import_tasks
from domain.special_equipment_import import (
    CATEGORY_IMAGE_MULTIPLE,
    NULL_TOKEN,
    PRODUCT_IMAGE_CLEAR_MIXED,
    PRODUCT_IMAGE_URL_INVALID,
    PRODUCT_IMAGES_ALL_FAILED,
    PRODUCT_IMAGES_LIMIT_EXCEEDED,
    ImportContractError,
    ImportMode,
    IssueSeverity,
    extract_google_drive_file_id,
    image_source_ref,
    parse_image_source_urls,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
    SpecialEquipmentProductImage,
)
from infrastructure.models.special_equipment_registry import (
    SpecialEquipmentMediaCleanupJob,
)
from infrastructure.repositories import (
    special_equipment_import_repository as import_repository,
)
from infrastructure.services.special_equipment_import_images import TransferredImage
from infrastructure.services.special_equipment_xlsx import JsonlRows
from tests.special_equipment_factories import special_equipment_directory
from tests.test_special_equipment_import_v2_durability import create_row_stores

_ALLOWED_HOSTS = frozenset({"drive.google.com", "drive.usercontent.google.com"})


def test_extract_google_drive_file_id() -> None:
    assert (
        extract_google_drive_file_id("https://drive.google.com/file/d/1a2b3c4d5e/view?usp=sharing")
        == "1a2b3c4d5e"
    )
    assert (
        extract_google_drive_file_id("https://drive.google.com/file/d/XYZ-999_abc/view?usp=drive_link")
        == "XYZ-999_abc"
    )
    assert (
        extract_google_drive_file_id("https://drive.google.com/uc?export=download&id=id_12345")
        == "id_12345"
    )
    assert (
        extract_google_drive_file_id("https://drive.google.com/open?id=open_678")
        == "open_678"
    )
    assert extract_google_drive_file_id("https://example.com/image.png") is None


def test_image_source_ref_normalizes_drive_urls() -> None:
    ref1 = image_source_ref("https://drive.google.com/file/d/FILE123/view?usp=sharing")
    ref2 = image_source_ref("https://drive.google.com/file/d/FILE123/view?usp=drive_link")
    ref3 = image_source_ref("https://drive.google.com/uc?id=FILE123&export=download")
    assert ref1 == "gdrive:FILE123"
    assert ref1 == ref2 == ref3


def test_parse_delimiters_and_whitespace() -> None:
    raw = (
        " https://drive.google.com/file/d/img1/view , https://drive.google.com/file/d/img2/view ; \n"
        "https://drive.google.com/file/d/img3/view\r\n\r\n"
        "https://drive.google.com/file/d/img4/view "
    )
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS)
    assert not parsed.is_clear
    assert not parsed.is_empty
    assert len(parsed.refs) == 4
    assert [r.source_ref for r in parsed.refs] == [
        "gdrive:img1",
        "gdrive:img2",
        "gdrive:img3",
        "gdrive:img4",
    ]
    assert [r.position for r in parsed.refs] == [1, 2, 3, 4]
    assert len(parsed.issues) == 0


def test_parse_single_url_backwards_compatible() -> None:
    raw = "https://drive.google.com/file/d/single_file_id/view?usp=sharing"
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS)
    assert len(parsed.refs) == 1
    assert parsed.refs[0].source_ref == "gdrive:single_file_id"
    assert len(parsed.issues) == 0


def test_parse_deduplication_within_cell() -> None:
    raw = (
        "https://drive.google.com/file/d/DUP1/view?usp=sharing,\n"
        "https://drive.google.com/file/d/DUP1/view?usp=drive_link,\n"
        "https://drive.google.com/file/d/UNIQUE2/view"
    )
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS)
    assert len(parsed.refs) == 2
    assert [r.source_ref for r in parsed.refs] == ["gdrive:DUP1", "gdrive:UNIQUE2"]
    assert len(parsed.issues) == 0  # No warning for duplicates


def test_parse_limit_exceeded() -> None:
    links = [f"https://drive.google.com/file/d/photo_{i}/view" for i in range(55)]
    raw = "\n".join(links)
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS, limit=50)
    assert len(parsed.refs) == 50
    assert len(parsed.issues) == 1
    issue = parsed.issues[0]
    assert issue.code == PRODUCT_IMAGES_LIMIT_EXCEEDED
    assert "50" in issue.message
    assert "отброшено: 5" in issue.message


def test_parse_invalid_host_and_scheme_generates_warnings() -> None:
    raw = (
        "http://drive.google.com/file/d/insecure/view,\n"
        "https://evil.com/file/d/bad_host/view,\n"
        "https://drive.google.com/file/d/valid/view"
    )
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS)
    assert len(parsed.refs) == 1
    assert parsed.refs[0].source_ref == "gdrive:valid"
    assert len(parsed.issues) == 2
    assert all(issue.code == PRODUCT_IMAGE_URL_INVALID for issue in parsed.issues)


def test_parse_empty_and_clear_token() -> None:
    assert parse_image_source_urls("", allowed_hosts=_ALLOWED_HOSTS).is_empty
    assert parse_image_source_urls("   ", allowed_hosts=_ALLOWED_HOSTS).is_empty
    assert parse_image_source_urls(None, allowed_hosts=_ALLOWED_HOSTS).is_empty

    clear_parsed = parse_image_source_urls(NULL_TOKEN, allowed_hosts=_ALLOWED_HOSTS)
    assert clear_parsed.is_clear
    assert not clear_parsed.is_empty
    assert len(clear_parsed.refs) == 0
    assert len(clear_parsed.issues) == 0


def test_parse_clear_mixed_with_urls() -> None:
    raw = f"{NULL_TOKEN}, https://drive.google.com/file/d/mixed/view"
    parsed = parse_image_source_urls(raw, allowed_hosts=_ALLOWED_HOSTS)
    assert not parsed.is_clear
    assert len(parsed.refs) == 0
    assert len(parsed.issues) == 1
    assert parsed.issues[0].code == PRODUCT_IMAGE_CLEAR_MIXED


# ==============================================================================
# Category image normalization tests
# ==============================================================================

def test_attach_category_image_action_multiple_urls_returns_error() -> None:
    row = {
        "_code": "cat-1",
        "_sheet_code": "Категории",
        "_row_number": 2,
        "image_source_url": (
            "https://drive.google.com/file/d/cat_img1/view, "
            "https://drive.google.com/file/d/cat_img2/view"
        ),
    }
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_category_image_action(
        values=values,
        row=row,
        mode=ImportMode.APPEND,
        issues=issues,
    )
    assert not ok
    assert issues.error_count == 1
    issue = next(iter(issues))
    assert issue.code == CATEGORY_IMAGE_MULTIPLE
    assert issue.severity == IssueSeverity.ERROR
    assert "одна ссылка" in issue.message


def test_attach_category_image_action_single_url_succeeds() -> None:
    row = {
        "_code": "cat-1",
        "_sheet_code": "Категории",
        "_row_number": 2,
        "image_source_url": "https://drive.google.com/file/d/single_cat_img/view",
    }
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_category_image_action(
        values=values,
        row=row,
        mode=ImportMode.APPEND,
        issues=issues,
    )
    assert ok
    assert issues.error_count == 0
    assert values["_image_action"] == "replace"
    assert values["_image_source_url"] == "https://drive.google.com/file/d/single_cat_img/view"


def test_attach_category_image_action_clear_marker() -> None:
    row = {
        "_code": "cat-1",
        "_sheet_code": "Категории",
        "_row_number": 2,
        "image_source_url": NULL_TOKEN,
    }
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_category_image_action(
        values=values,
        row=row,
        mode=ImportMode.APPEND,
        issues=issues,
    )
    assert ok
    assert values["_image_action"] == "clear"


# ==============================================================================
# Product image normalization and NOOP detection tests
# ==============================================================================

def test_attach_product_images_action_patch_blank_keeps_gallery() -> None:
    row = {"operation": "SET", "image_source_url": None}
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_product_images_action(
        values=values,
        row=row,
        mode=ImportMode.PATCH,
        code="prod-1",
        context={"product_images": {}},
        issues=issues,
    )
    assert ok
    assert values["_images_action"] == "keep"
    assert values["_image_sources"] == []


def test_attach_product_images_action_append_blank_clears_gallery() -> None:
    row = {"operation": "ADD", "image_source_url": None}
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_product_images_action(
        values=values,
        row=row,
        mode=ImportMode.APPEND,
        code="prod-1",
        context={"product_images": {}},
        issues=issues,
    )
    assert ok
    assert values["_images_action"] == "clear"


def test_attach_product_images_action_matching_gallery_sets_keep() -> None:
    current_images = [
        {
            "id": uuid4(),
            "storage_key": "special-equipment/p1/img1.webp",
            "source_ref": "gdrive:match1",
            "sort_order": 0,
            "is_primary": True,
        },
        {
            "id": uuid4(),
            "storage_key": "special-equipment/p1/img2.webp",
            "source_ref": "gdrive:match2",
            "sort_order": 1,
            "is_primary": False,
        },
    ]
    row = {
        "operation": "SET",
        "image_source_url": (
            "https://drive.google.com/file/d/match1/view?usp=sharing, "
            "https://drive.google.com/file/d/match2/view?usp=drive_link"
        ),
    }
    values: dict[str, object] = {}
    issues = import_v2.V2IssueCollector()

    ok = import_v2._attach_product_images_action(
        values=values,
        row=row,
        mode=ImportMode.PATCH,
        code="prod-1",
        context={"product_images": {"prod-1": current_images}},
        issues=issues,
    )
    assert ok
    assert values["_images_action"] == "keep"
    assert isinstance(values["_image_sources"], list)
    assert len(values["_image_sources"]) == 2


def test_product_attributes_changed_detection() -> None:
    current = {
        "seller_company_id": "11111111-1111-1111-1111-111111111111",
        "price": Decimal("1000000"),
        "description": "Original description",
        "publication_status": "published",
    }
    values_identical = {
        "seller_company_id": "11111111-1111-1111-1111-111111111111",
        "price": Decimal("1000000.00"),
        "description": "Original description",
        "publication_status": "published",
    }
    assert not import_v2._product_attributes_changed(values=values_identical, current=current)

    values_changed = {**values_identical, "description": "Updated description"}
    assert import_v2._product_attributes_changed(values=values_changed, current=current)


# ==============================================================================
# Import task _transfer_plan_images tests
# ==============================================================================

@pytest.mark.asyncio
async def test_transfer_plan_images_deduplicates_downloads_across_products(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "dedup-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    download_count = 0

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        nonlocal download_count
        download_count += 1
        url = kwargs["source_url"]
        file_id = extract_google_drive_file_id(url)
        return TransferredImage(
            storage_key=f"special-equipment/staged/{file_id}.webp",
            content_sha256="b" * 64,
            size_bytes=1024,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    # 10 products sharing the same 3 images
    shared_sources = [
        {"source_ref": "gdrive:share1", "raw_url": "https://drive.google.com/file/d/share1/view", "position": 1},
        {"source_ref": "gdrive:share2", "raw_url": "https://drive.google.com/file/d/share2/view", "position": 2},
        {"source_ref": "gdrive:share3", "raw_url": "https://drive.google.com/file/d/share3/view", "position": 3},
    ]

    for i in range(10):
        plan["products"].append(
            {
                "id": uuid4(),
                "code": f"truck-{i}",
                "operation": "SET",
                "values": {
                    "_images_action": "replace",
                    "_image_sources": list(shared_sources),
                    "_current_images": [],
                },
                "_sheet_code": "Объявления",
                "_row_number": i + 2,
                "_aggregate_kind": "product",
                "_aggregate_code": f"truck-{i}",
            }
        )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert download_count == 3
    assert summary["requested"] == 3
    assert summary["transferred"] == 3
    assert summary["reused"] == 0
    assert summary["optionalFailures"] == 0
    assert summary["blockingFailures"] == 0

    for row in plan["products"]:
        images = row["values"]["_images"]
        assert len(images) == 3
        assert [img["storage_key"] for img in images] == [
            "special-equipment/staged/share1.webp",
            "special-equipment/staged/share2.webp",
            "special-equipment/staged/share3.webp",
        ]


@pytest.mark.asyncio
async def test_transfer_plan_images_partial_failure_first_fails_second_becomes_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "partial-fail-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        url = kwargs["source_url"]
        if "bad_photo" in url:
            raise ImportContractError("IMAGE_HTTP_STATUS_403")
        return TransferredImage(
            storage_key="special-equipment/staged/good_photo.webp",
            content_sha256="c" * 64,
            size_bytes=2048,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    sources = [
        {"source_ref": "gdrive:bad_photo", "raw_url": "https://drive.google.com/file/d/bad_photo/view", "position": 1},
        {"source_ref": "gdrive:good_photo", "raw_url": "https://drive.google.com/file/d/good_photo/view", "position": 2},
    ]

    plan["products"].append(
        {
            "id": uuid4(),
            "code": "truck-partial",
            "operation": "SET",
            "values": {
                "_images_action": "replace",
                "_image_sources": sources,
                "_current_images": [],
            },
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_aggregate_kind": "product",
            "_aggregate_code": "truck-partial",
        }
    )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert summary["transferred"] == 1
    assert summary["optionalFailures"] == 1
    assert summary["blockingFailures"] == 0

    assert issues.warning_count == 1
    assert issues.error_count == 0
    warning_issue = next(iter(issues))
    assert warning_issue.code == "IMAGE_HTTP_STATUS_403"
    assert warning_issue.severity == IssueSeverity.WARNING

    row = next(iter(plan["products"]))
    images = row["values"]["_images"]
    assert len(images) == 1
    assert images[0]["storage_key"] == "special-equipment/staged/good_photo.webp"
    assert images[0]["source_ref"] == "gdrive:good_photo"


@pytest.mark.asyncio
async def test_transfer_plan_images_all_photos_fail_marks_blocking_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "all-fail-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        raise ImportContractError("IMAGE_HTTP_STATUS_404")

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    sources = [
        {"source_ref": "gdrive:f1", "raw_url": "https://drive.google.com/file/d/f1/view", "position": 1},
        {"source_ref": "gdrive:f2", "raw_url": "https://drive.google.com/file/d/f2/view", "position": 2},
    ]

    plan["products"].append(
        {
            "id": uuid4(),
            "code": "truck-fail",
            "operation": "SET",
            "values": {
                "_images_action": "replace",
                "_image_sources": sources,
                "_current_images": [],
            },
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_aggregate_kind": "product",
            "_aggregate_code": "truck-fail",
        }
    )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert summary["blockingFailures"] == 1
    assert summary["optionalFailures"] == 2
    assert summary["transferred"] == 0

    assert issues.error_count == 1
    error_issues = [i for i in issues if i.severity == IssueSeverity.ERROR]
    assert error_issues[0].code == PRODUCT_IMAGES_ALL_FAILED
    # Product aggregate was dropped from plan in PATCH mode
    assert len(list(plan["products"])) == 0


@pytest.mark.asyncio
async def test_transfer_plan_images_reuses_existing_image_without_downloading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "reuse-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    transfer_called = False

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        nonlocal transfer_called
        transfer_called = True
        return TransferredImage(
            storage_key="should-not-be-called",
            content_sha256="",
            size_bytes=0,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    existing_id = str(uuid4())
    current_images = [
        {
            "id": existing_id,
            "storage_key": "special-equipment/existing_stored.webp",
            "source_ref": "gdrive:already_have",
            "sort_order": 0,
            "is_primary": True,
        }
    ]

    sources = [
        {"source_ref": "gdrive:already_have", "raw_url": "https://drive.google.com/file/d/already_have/view", "position": 1}
    ]

    plan["products"].append(
        {
            "id": uuid4(),
            "code": "truck-reuse",
            "operation": "SET",
            "values": {
                "_images_action": "replace",
                "_image_sources": sources,
                "_current_images": current_images,
            },
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_aggregate_kind": "product",
            "_aggregate_code": "truck-reuse",
        }
    )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert not transfer_called
    assert summary["reused"] == 1
    assert summary["transferred"] == 0
    row = next(iter(plan["products"]))
    target = row["values"]["_images"][0]
    assert target["storage_key"] == "special-equipment/existing_stored.webp"
    assert target["source_ref"] == "gdrive:already_have"
    assert target["reuse_image_id"] == existing_id


# ==============================================================================
# Repository apply _v2_apply_product_images tests
# ==============================================================================

@pytest.mark.asyncio
async def test_apply_product_images_inserts_ordered_gallery(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Gallery Mark",
        model_name="SE Gallery Model",
        modification_name="SE Gallery Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"gallery-test-{uuid4()}",
        modification_id=modification.id,
        slug=f"gallery-slug-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add(product)
    await db_session.flush()

    # Apply 6 images
    images_payload = [
        {"storage_key": f"key_{i}.webp", "source_ref": f"gdrive:ref_{i}", "reuse_image_id": None}
        for i in range(6)
    ]
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": images_payload},
    )
    await db_session.flush()

    rows = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
                .order_by(SpecialEquipmentProductImage.sort_order)
            )
        ).scalars()
    )

    assert len(rows) == 6
    for idx, img in enumerate(rows):
        assert img.sort_order == idx
        assert img.storage_key == f"key_{idx}.webp"
        assert img.source_ref == f"gdrive:ref_{idx}"
        assert img.is_primary == (idx == 0)


@pytest.mark.asyncio
async def test_apply_product_images_reorder_is_idempotent(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Reorder Mark",
        model_name="SE Reorder Model",
        modification_name="SE Reorder Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"reorder-test-{uuid4()}",
        modification_id=modification.id,
        slug=f"reorder-slug-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add(product)
    await db_session.flush()

    # Initial order: 0, 1, 2
    initial_payload = [
        {"storage_key": f"key_{i}.webp", "source_ref": f"gdrive:ref_{i}", "reuse_image_id": None}
        for i in range(3)
    ]
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": initial_payload},
    )
    await db_session.flush()

    # Reverse order: 2, 1, 0
    reversed_payload = list(reversed(initial_payload))
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": reversed_payload},
    )
    await db_session.flush()

    rows = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
                .order_by(SpecialEquipmentProductImage.sort_order)
            )
        ).scalars()
    )
    assert len(rows) == 3
    assert rows[0].storage_key == "key_2.webp"
    assert rows[0].is_primary is True
    assert rows[1].storage_key == "key_1.webp"
    assert rows[1].is_primary is False
    assert rows[2].storage_key == "key_0.webp"
    assert rows[2].is_primary is False

    # Applying the exact same reversed order again is completely idempotent
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": reversed_payload},
    )
    await db_session.flush()

    rows_after = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
                .order_by(SpecialEquipmentProductImage.sort_order)
            )
        ).scalars()
    )
    assert len(rows_after) == 3
    assert [r.id for r in rows_after] == [r.id for r in rows]


@pytest.mark.asyncio
async def test_apply_product_images_deletion_enqueues_cleanup(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Cleanup Mark",
        model_name="SE Cleanup Model",
        modification_name="SE Cleanup Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"cleanup-test-{uuid4()}",
        modification_id=modification.id,
        slug=f"cleanup-slug-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add(product)
    await db_session.flush()

    initial_payload = [
        {"storage_key": f"clean_key_{i}.webp", "source_ref": f"gdrive:ref_{i}", "reuse_image_id": None}
        for i in range(3)
    ]
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": initial_payload},
    )
    await db_session.flush()

    # Now replace with only key_0, removing clean_key_1 and clean_key_2
    reduced_payload = [initial_payload[0]]
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "replace", "_images": reduced_payload},
    )
    await db_session.flush()

    cleanup_jobs = list(
        (
            await db_session.execute(
                select(SpecialEquipmentMediaCleanupJob).where(
                    SpecialEquipmentMediaCleanupJob.storage_key.in_(
                        ["clean_key_1.webp", "clean_key_2.webp"]
                    )
                )
            )
        ).scalars()
    )
    assert len(cleanup_jobs) == 2


@pytest.mark.asyncio
async def test_apply_product_images_shared_image_not_enqueued_if_referenced_elsewhere(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Shared Mark",
        model_name="SE Shared Model",
        modification_name="SE Shared Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    prod1 = SpecialEquipmentProduct(
        code=f"shared-1-{uuid4()}",
        modification_id=modification.id,
        slug=f"shared-slug-1-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    prod2 = SpecialEquipmentProduct(
        code=f"shared-2-{uuid4()}",
        modification_id=modification.id,
        slug=f"shared-slug-2-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add_all([prod1, prod2])
    await db_session.flush()

    shared_key = f"shared_common_{uuid4()}.webp"
    # Both products reference shared_key
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=prod1.id,
        values={
            "_images_action": "replace",
            "_images": [{"storage_key": shared_key, "source_ref": "gdrive:common", "reuse_image_id": None}],
        },
    )
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=prod2.id,
        values={
            "_images_action": "replace",
            "_images": [{"storage_key": shared_key, "source_ref": "gdrive:common", "reuse_image_id": None}],
        },
    )
    await db_session.flush()

    # Now clear product 1 images
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=prod1.id,
        values={"_images_action": "clear", "_images": []},
    )
    await db_session.flush()

    # shared_key is still used by prod2 -> MUST NOT be in cleanup table
    cleanup_jobs = list(
        (
            await db_session.execute(
                select(SpecialEquipmentMediaCleanupJob).where(
                    SpecialEquipmentMediaCleanupJob.storage_key == shared_key
                )
            )
        ).scalars()
    )
    assert len(cleanup_jobs) == 0


@pytest.mark.asyncio
async def test_transfer_plan_images_respects_concurrency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "concurrency-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    active_downloads = 0
    max_active = 0

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        nonlocal active_downloads, max_active
        active_downloads += 1
        max_active = max(max_active, active_downloads)
        await asyncio.sleep(0.02)
        active_downloads -= 1
        return TransferredImage(
            storage_key=f"special-equipment/staged/{uuid4()}.webp",
            content_sha256="c" * 64,
            size_bytes=100,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    for i in range(12):
        plan["products"].append(
            {
                "id": uuid4(),
                "code": f"truck-conc-{i}",
                "operation": "SET",
                "values": {
                    "_images_action": "replace",
                    "_image_sources": [
                        {"source_ref": f"gdrive:conc_{i}", "raw_url": f"https://drive.google.com/file/d/conc_{i}/view", "position": 1}
                    ],
                    "_current_images": [],
                },
                "_sheet_code": "Объявления",
                "_row_number": i + 2,
                "_aggregate_kind": "product",
                "_aggregate_code": f"truck-conc-{i}",
            }
        )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert summary["transferred"] == 12
    # Verify concurrency never exceeded the semaphore limit (4)
    assert max_active <= 4


@pytest.mark.asyncio
async def test_transfer_plan_images_budget_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "budget-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    async def mock_transfer_timeout(**kwargs: Any) -> TransferredImage:
        # Simulate long download
        await asyncio.sleep(0.5)
        return TransferredImage(
            storage_key="should-timeout.webp",
            content_sha256="",
            size_bytes=0,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer_timeout)
    # Set budget to 0 seconds so it immediately exceeds
    from infrastructure.settings import settings
    monkeypatch.setattr(settings, "special_equipment_import_image_budget_seconds", 0)

    plan["products"].append(
        {
            "id": uuid4(),
            "code": "truck-timeout",
            "operation": "SET",
            "values": {
                "_images_action": "replace",
                "_image_sources": [
                    {"source_ref": "gdrive:timeout1", "raw_url": "https://drive.google.com/file/d/timeout1/view", "position": 1}
                ],
                "_current_images": [],
            },
            "_sheet_code": "Объявления",
            "_row_number": 2,
            "_aggregate_kind": "product",
            "_aggregate_code": "truck-timeout",
        }
    )

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    assert summary["transferred"] == 0
    assert summary["optionalFailures"] == 1
    assert any(i.code == "IMAGE_FETCH_BUDGET_EXCEEDED" for i in issues)


@pytest.mark.asyncio
async def test_apply_product_legacy_primary_image_action_compatibility(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Legacy Mark",
        model_name="SE Legacy Model",
        modification_name="SE Legacy Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"legacy-test-{uuid4()}",
        modification_id=modification.id,
        slug=f"legacy-slug-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add(product)
    await db_session.flush()

    legacy_key = f"legacy_staged_{uuid4()}.webp"
    row = {
        "id": product.id,
        "code": product.code,
        "operation": "SET",
        "values": {
            "modification_id": modification.id,
            "slug": product.slug,
            "condition": "new",
            "no_vin": True,
            "price": 500_000,
            "publication_status": "draft",
            "sale_status": "available",
            "_primary_image_action": "replace",
            "_primary_image_storage_key": legacy_key,
        },
    }
    await import_repository._v2_apply_entity(
        db_session,
        family="products",
        row=row,
        counts={"created": 0, "updated": 0, "archived": 0, "removed": 0},
    )
    await db_session.flush()

    rows = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
            )
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].storage_key == legacy_key
    assert rows[0].is_primary is True


@pytest.mark.asyncio
async def test_apply_product_manual_image_retention_on_keep_and_removal_on_replace(
    db_session: AsyncSession,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="SE Manual Mark",
        model_name="SE Manual Model",
        modification_name="SE Manual Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    product = SpecialEquipmentProduct(
        code=f"manual-test-{uuid4()}",
        modification_id=modification.id,
        slug=f"manual-slug-{uuid4()}",
        condition="new",
        no_vin=True,
        price=500_000,
        currency_code="RUB",
        publication_status="draft",
        sale_status="available",
    )
    db_session.add(product)
    await db_session.flush()

    # Manual image has source_ref = None
    manual_img = SpecialEquipmentProductImage(
        product_id=product.id,
        storage_key="manual_img.webp",
        sort_order=0,
        is_primary=True,
        source_ref=None,
    )
    db_session.add(manual_img)
    await db_session.flush()

    # Case A: _images_action == "keep" preserves manual image
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={"_images_action": "keep"},
    )
    await db_session.flush()

    images = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
            )
        ).scalars()
    )
    assert len(images) == 1
    assert images[0].storage_key == "manual_img.webp"

    # Case B: _images_action == "replace" replaces manual image with new file images
    await import_repository._v2_apply_product_images(
        db_session,
        product_id=product.id,
        values={
            "_images_action": "replace",
            "_images": [
                {"storage_key": "imported_new.webp", "source_ref": "gdrive:new_ref", "reuse_image_id": None}
            ],
        },
    )
    await db_session.flush()

    images_after = list(
        (
            await db_session.execute(
                select(SpecialEquipmentProductImage)
                .where(SpecialEquipmentProductImage.product_id == product.id)
            )
        ).scalars()
    )
    assert len(images_after) == 1
    assert images_after[0].storage_key == "imported_new.webp"
    assert images_after[0].source_ref == "gdrive:new_ref"

    # Verify manual_img was queued for cleanup
    cleanup = list(
        (
            await db_session.execute(
                select(SpecialEquipmentMediaCleanupJob).where(
                    SpecialEquipmentMediaCleanupJob.storage_key == "manual_img.webp"
                )
            )
        ).scalars()
    )
    assert len(cleanup) == 1


@pytest.mark.asyncio
async def test_regression_50_announcements_6_photos_dedup(
    tmp_path: Path,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mark, model, modification = special_equipment_directory(
        mark_name="FAW Regression Mark",
        model_name="FAW Regression Model",
        modification_name="FAW Regression Mod",
    )
    db_session.add_all([mark, model, modification])
    await db_session.flush()

    plan: dict[str, JsonlRows] = create_row_stores(
        tmp_path / "faw-plan",
        import_tasks.DATA_SHEET_HEADERS,
    )

    download_count = 0

    async def mock_transfer(**kwargs: Any) -> TransferredImage:
        nonlocal download_count
        download_count += 1
        url = kwargs["source_url"]
        file_id = extract_google_drive_file_id(url)
        return TransferredImage(
            storage_key=f"special-equipment/staged/{file_id}.webp",
            content_sha256="f" * 64,
            size_bytes=1024,
        )

    monkeypatch.setattr(import_tasks, "transfer_temporary_image", mock_transfer)

    # 5 common photos + 1 unique photo per announcement
    common_sources = [
        {"source_ref": f"gdrive:common_{k}", "raw_url": f"https://drive.google.com/file/d/common_{k}/view", "position": k}
        for k in range(1, 6)
    ]

    products: list[SpecialEquipmentProduct] = []
    for i in range(50):
        prod_id = uuid4()
        prod = SpecialEquipmentProduct(
            id=prod_id,
            code=f"faw-truck-{i}-{uuid4()}",
            modification_id=modification.id,
            slug=f"faw-slug-{i}-{uuid4()}",
            condition="new",
            no_vin=True,
            price=1_000_000,
            currency_code="RUB",
            publication_status="draft",
            sale_status="available",
        )
        products.append(prod)
        db_session.add(prod)

        unique_source = {
            "source_ref": f"gdrive:unique_{i}",
            "raw_url": f"https://drive.google.com/file/d/unique_{i}/view",
            "position": 6,
        }
        item_sources = [*common_sources, unique_source]

        plan["products"].append(
            {
                "id": prod_id,
                "code": prod.code,
                "operation": "SET",
                "values": {
                    "_images_action": "replace",
                    "_image_sources": item_sources,
                    "_current_images": [],
                },
                "_sheet_code": "Объявления",
                "_row_number": i + 2,
                "_aggregate_kind": "product",
                "_aggregate_code": prod.code,
            }
        )

    await db_session.flush()

    issues = import_v2.V2IssueCollector()
    summary = await import_tasks._transfer_plan_images(
        job_id=uuid4(),
        mode=ImportMode.PATCH,
        plan=plan,
        issues=issues,
        storage=object(),  # type: ignore[arg-type]
    )

    # Exactly 5 common + 50 unique = 55 downloads
    assert download_count == 55
    assert summary["requested"] == 55
    assert summary["transferred"] == 55
    assert summary["reused"] == 0
    assert summary["optionalFailures"] == 0
    assert summary["blockingFailures"] == 0

    # Apply all 50 products to DB
    for row in plan["products"]:
        await import_repository._v2_apply_product_images(
            db_session,
            product_id=row["id"],
            values=row["values"],
        )
    await db_session.flush()

    # Verify each product in DB has 6 images, sort_order 0..5, only first is primary
    for prod in products:
        images = list(
            (
                await db_session.execute(
                    select(SpecialEquipmentProductImage)
                    .where(SpecialEquipmentProductImage.product_id == prod.id)
                    .order_by(SpecialEquipmentProductImage.sort_order)
                )
            ).scalars()
        )
        assert len(images) == 6
        for idx, img in enumerate(images):
            assert img.sort_order == idx
            assert img.is_primary == (idx == 0)

