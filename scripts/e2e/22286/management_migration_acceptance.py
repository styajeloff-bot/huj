"""Real upgrade 157->158->159->head on a disposable DB with historical LC responses."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from acceptance import guard, progress, require
from migration_acceptance import (
    database_operation,
    database_revisions,
    isolated_alembic,
    questionnaire_snapshots,
    target_url,
    verify_connection,
)

BASE = datetime(2026, 9, 1, 12, tzinfo=UTC)
SOURCE_TABLES = ("application_document_requests", "documents", "application_documents")
DOCUMENT_PATHS = ("status", "file_name", "documents")


async def source_snapshots(url, expected):
    target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            return {table: [dict(row) for row in (await connection.execute(sa.text(
                f"SELECT * FROM {table} ORDER BY id"
            ))).mappings()] for table in SOURCE_TABLES}
    finally:
        await engine.dispose()


async def seed_history(url, expected):
    target_url(url, expected)
    engine = create_async_engine(url)
    meta = sa.MetaData()
    cases = {}
    try:
        async with engine.begin() as connection:
            await verify_connection(connection, expected)
            require(tuple((await connection.scalars(sa.text("SELECT version_num FROM alembic_version"))).all()) == ("157",), "Historical seed requires actual 157")
            await connection.run_sync(meta.reflect, only=[
                "companies", "leasing_companies", "leasing_applications",
                "application_questionnaires", *SOURCE_TABLES,
            ])
            company_id, lc_a, lc_b = uuid4(), uuid4(), uuid4()
            await connection.execute(meta.tables["companies"].insert().values(
                id=company_id, name="Management migration synthetic company", company_type="other"))
            await connection.execute(meta.tables["leasing_companies"].insert(), [
                {"id": lc_a, "company_id": company_id}, {"id": lc_b, "company_id": company_id},
            ])
            for name in ("two_files", "latest_no_file", "autoapproved_legacy", "no_actual_response"):
                app_id, qid = uuid4(), uuid4()
                requisites = [{"name": "Ручная управляющая компания", "inn": "7701234567", "ogrn": None}]
                await connection.execute(meta.tables["leasing_applications"].insert().values(
                    id=app_id, company_id=company_id, name="Management history " + name))
                await connection.execute(meta.tables["application_questionnaires"].insert().values(
                    id=qid, application_id=app_id, management_company_details=requisites,
                    company_email="preserved@example.test",
                    field_sources={"management_company_details": "manual",
                        "management_company_details.0.ogrn": "manual", "company_email": "manual"},
                    questionnaire_completed_at=BASE, created_at=BASE, updated_at=BASE,
                ))
                cases[name] = {"application_id": app_id, "questionnaire_id": qid, "expected_documents": []}

            async def request(case, *, status, provided_day=None, requested_day=0,
                              kind="management_company", files=(), lc=lc_a, file_day=None, reviewed_day=None):
                app_id = cases[case]["application_id"]
                request_id = uuid4()
                await connection.execute(meta.tables["application_document_requests"].insert().values(
                    id=request_id, application_id=app_id, leasing_company_id=lc, request_batch_id=uuid4(),
                    document_type=kind, display_name="Сведения об управляющей компании",
                    status=status, provided_at=BASE + timedelta(days=provided_day) if provided_day is not None else None,
                    requested_at=BASE + timedelta(days=requested_day),
                    reviewed_at=BASE + timedelta(days=reviewed_day) if reviewed_day is not None else None,
                ))
                references = []
                for index, (filename, title) in enumerate(files):
                    document_id = uuid4()
                    actual_file_day = file_day if file_day is not None else provided_day if provided_day is not None else requested_day
                    uploaded = BASE + timedelta(days=actual_file_day, minutes=index)
                    await connection.execute(meta.tables["documents"].insert().values(
                        id=document_id, company_id=company_id, document_type=kind,
                        related_application_id=app_id, file_name=filename,
                        created_at=uploaded, uploaded_at=uploaded,
                    ))
                    await connection.execute(meta.tables["application_documents"].insert().values(
                        id=uuid4(), application_id=app_id, leasing_company_id=lc, document_request_id=request_id,
                        document_id=document_id, user_title=title, submitted_at=uploaded,
                    ))
                    references.append({"document_id": str(document_id), "user_title": title.strip() if title and title.strip() else filename or "Документ об управляющей компании"})
                return request_id, references

            # provided_at, not requested_at, establishes the actual answer order.
            await request("two_files", status="provided", provided_day=2, requested_day=8,
                          files=(("older.pdf", "Старый файл"),))
            selected_id, documents = await request("two_files", status="approved", provided_day=4, requested_day=1,
                files=(("contract.pdf", "Договор управления"), ("legacy-contract.pdf", "  ")))
            cases["two_files"]["expected_documents"] = documents
            await request("two_files", status="requested", requested_day=9,
                          files=(("pending.pdf", "Не предоставлен"),))
            await request("two_files", status="provided", provided_day=10, requested_day=10,
                          kind="custom_management_company", files=(("custom.pdf", "Похожее пользовательское название"),))
            await request("two_files", status="provided", provided_day=11, requested_day=11,
                          kind="appointment_docs", files=(("wrong-type.pdf", "Другой тип"),))
            # A link for another application or LC must not enlarge request access.
            for wrong_app, wrong_lc in (
                (cases["latest_no_file"]["application_id"], lc_a),
                (cases["two_files"]["application_id"], lc_b),
            ):
                document_id = uuid4()
                await connection.execute(meta.tables["documents"].insert().values(
                    id=document_id, company_id=company_id, document_type="management_company",
                    related_application_id=wrong_app, file_name="unrelated.pdf", created_at=BASE))
                await connection.execute(meta.tables["application_documents"].insert().values(
                    id=uuid4(), application_id=wrong_app, leasing_company_id=wrong_lc,
                    document_request_id=selected_id, document_id=document_id, user_title="Чужая связь"))

            await request("latest_no_file", status="provided", provided_day=2, files=(("old.pdf", "Старый ответ"),))
            # A late approval must not make an older actual file answer the latest.
            await request("latest_no_file", status="approved", requested_day=1, file_day=3, reviewed_day=30,
                          files=(("late-approved.pdf", "Одобрен позже нового ответа"),))
            await request("latest_no_file", status="provided", provided_day=5, requested_day=1)
            await request("latest_no_file", status="requested", requested_day=12)
            await request("no_actual_response", status="requested", requested_day=12,
                          files=(("pending.pdf", "Ожидающий"),))
            await request("no_actual_response", status="approved", requested_day=13, reviewed_day=14)
            _, legacy_documents = await request("autoapproved_legacy", status="approved",
                requested_day=1, file_day=4, reviewed_day=10, files=((None, None),))
            cases["autoapproved_legacy"]["expected_documents"] = legacy_documents
            await request("no_actual_response", status="provided", provided_day=14, requested_day=14,
                          kind="custom_management_company", files=(("custom.pdf", "Похожее название"),))
    finally:
        await engine.dispose()
    return cases


def expected_backfill(before, cases):
    expected = deepcopy(before)
    for case in ("two_files", "latest_no_file", "autoapproved_legacy"):
        row = expected[cases[case]["questionnaire_id"]]
        documents = cases[case]["expected_documents"]
        row["management_company_details"].update({
            "status": "file_attached" if documents else "not_provided",
            "file_name": "; ".join(item["user_title"] for item in documents) or None,
            "documents": documents,
        })
        row["field_sources"].update({
            "management_company_details." + field: "document_request" for field in DOCUMENT_PATHS
        })
    return expected


def run():
    settings = guard()
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    original_name, original_url = settings.db_name, settings.database_url
    original_dsn = settings.database_dsn
    shared_revisions = asyncio.run(database_revisions(original_dsn, original_name))
    admin_url = sa.engine.make_url(original_dsn).set(database="postgres")
    name = "questionnaire22286_m150_" + uuid4().hex[:16]
    isolated_dsn = sa.engine.make_url(original_dsn).set(database=name).render_as_string(hide_password=False)
    config = Config("/source/alembic.ini")
    config.set_main_option("script_location", "/source/alembic")
    config.set_main_option("prepend_sys_path", "/source")
    graph = ScriptDirectory.from_config(config)
    require(len(graph.get_heads()) == 1, "Expected exactly one current head")
    head = graph.get_current_head()
    asyncio.run(database_operation(admin_url, name, create=True))
    try:
        settings.db_name = name
        settings.database_url = isolated_dsn
        settings.__dict__.pop("database_dsn", None)
        target_url(settings.database_dsn, name)
        isolated_alembic(command.upgrade, config, settings, name, "157")
        cases = asyncio.run(seed_history(settings.database_dsn, name))
        source_rows = asyncio.run(source_snapshots(settings.database_dsn, name))
        isolated_alembic(command.upgrade, config, settings, name, "158")
        before = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))
        require(before[cases["two_files"]["questionnaire_id"]]["management_company_details"]["status"] == "not_provided",
                "Historical gap was not exercised at revision 158")
        progress("management_history_158_gap_reproduced", database=name)
        expected = expected_backfill(before, cases)
        isolated_alembic(command.upgrade, config, settings, name, "159")
        require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("159",), "Upgrade did not reach actual revision 159")
        after = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))
        require(after == expected, "Historical backfill differs from expected evidence or changed requisites/manual sources/identity/dates")
        require(asyncio.run(source_snapshots(settings.database_dsn, name)) == source_rows, "Backfill rewrote requests, files or LC access links")
        isolated_alembic(command.upgrade, config, settings, name, "head")
        require(asyncio.run(database_revisions(settings.database_dsn, name)) == (head,), "Upgrade did not reach current head")
        require(asyncio.run(questionnaire_snapshots(settings.database_dsn, name)) == after, "Later migrations changed backfilled evidence")
        require(asyncio.run(source_snapshots(settings.database_dsn, name)) == source_rows, "Later migrations rewrote document sources")
        isolated_alembic(command.check, config, settings, name)

        isolated_alembic(command.downgrade, config, settings, name, "158")
        require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("158",), "Downgrade did not reach actual revision 158")
        require(asyncio.run(questionnaire_snapshots(settings.database_dsn, name)) == after, "Downgrade discarded transferred evidence")
        isolated_alembic(command.upgrade, config, settings, name, "head")
        require(asyncio.run(questionnaire_snapshots(settings.database_dsn, name)) == after, "Repeated upgrade changed canonical evidence")
        require(asyncio.run(source_snapshots(settings.database_dsn, name)) == source_rows, "Replay changed document access or source rows")
        isolated_alembic(command.check, config, settings, name)
        progress("management_history_migration_passed", database=name, revision=head,
                 checked="two files; legacy autoapproval without provided_at; actual upload chronology; safe nullable title; pending/custom excluded; latest no-file; scope; manual data; identity/date; replay/check")
    finally:
        settings.db_name = original_name
        settings.database_url = original_url
        settings.__dict__.pop("database_dsn", None)
        asyncio.run(database_operation(admin_url, name, create=False))
        require(asyncio.run(database_revisions(settings.database_dsn, original_name)) == shared_revisions,
                "Shared database revision changed during isolated acceptance")


if __name__ == "__main__":
    run()
