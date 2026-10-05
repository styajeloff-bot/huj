"""Real PostgreSQL upgrade acceptance on a disposable database, never the shared stack.

Run: python /e2e/migration_acceptance.py
Uses three independent databases for the legacy chain, published revision 154,
and local revision 155. Checks real upgrades, preserved data and autogenerate,
then drops only the uniquely named databases it created.
"""
import asyncio
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from acceptance import guard, progress, require

PURPOSE = "Перевозка; сотрудников, клиентов"


def target_url(url, expected):
    parsed = sa.engine.make_url(url)
    require(parsed.host == "postgres" and parsed.database == expected, "Refusing unexpected database URL")
    return {"driver": parsed.drivername, "host": parsed.host, "port": parsed.port, "database": parsed.database}


async def verify_connection(connection, expected):
    actual = await connection.scalar(sa.text("SELECT current_database()"))
    require(actual == expected, "Connected to the wrong database")


async def database_revisions(url, expected):
    endpoint = target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            revisions = tuple((await connection.scalars(sa.text("SELECT version_num FROM alembic_version ORDER BY version_num"))).all())
        progress("database_target_verified", **endpoint, revisions=revisions)
        return revisions
    finally:
        await engine.dispose()


def isolated_alembic(operation, config, settings, expected, *args):
    endpoint = target_url(settings.database_dsn, expected)

    def guard_connect(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("SELECT current_database()")
            require(cursor.fetchone()[0] == expected, "Alembic attempted a non-isolated connection")
        finally:
            cursor.close()
        progress("alembic_target_verified", **endpoint)

    sa.event.listen(sa.engine.Engine, "connect", guard_connect)
    try:
        operation(config, *args)
    finally:
        sa.event.remove(sa.engine.Engine, "connect", guard_connect)


async def database_operation(url, name, *, create):
    require(re.fullmatch(r"questionnaire22286_m150_[0-9a-f]{16}", name), "Refusing non-fixture database")
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, "postgres")
            await connection.execute(sa.text(f'CREATE DATABASE "{name}"' if create else f'DROP DATABASE "{name}" WITH (FORCE)'))
    finally:
        await engine.dispose()


async def seed_legacy(url, expected):
    endpoint = target_url(url, expected)
    engine = create_async_engine(url)
    meta = sa.MetaData()
    ids = {key: uuid4() for key in ("company", "application", "questionnaire", "vehicle", "preserved_beneficiary", "mark", "model", "modification", "product", "category")}
    try:
        async with engine.begin() as connection:
            await verify_connection(connection, expected)
            require(tuple((await connection.scalars(sa.text("SELECT version_num FROM alembic_version"))).all()) == ("149",), "Legacy seeding requires only actual revision 149")
            progress("legacy_seed_target_verified", **endpoint)
            await connection.run_sync(meta.reflect, only=["companies", "leasing_applications", "application_questionnaires", "application_vehicles", "special_equipment_marks", "special_equipment_models", "special_equipment_modifications", "special_equipment_products", "special_equipment_application_items", "special_equipment_categories", "special_equipment_modification_categories"])
            await connection.execute(meta.tables["companies"].insert().values(id=ids["company"], name="Migration 150 synthetic fixture", company_type="other"))
            await connection.execute(meta.tables["leasing_applications"].insert().values(id=ids["application"], company_id=ids["company"], name="Migration fixture"))
            await connection.execute(meta.tables["application_questionnaires"].insert().values(
                id=ids["questionnaire"], application_id=ids["application"],
                founders=[{"inn": "000000009901", "name": "Ручное имя", "share": None}],
                beneficiaries=[{"id": str(ids["preserved_beneficiary"]), "inn": "000000009903", "full_name": "Прежний UUID", "birth_place": None}],
                other_representatives=[{"full_name": "Нет ID", "birth_place": None}],
                field_sources={"founders.000000009901.name": "manual", "founders.000000009901.share": "manual",
                    "founders.000000009902": "manual", "beneficiaries.000000009903.birth_place": "manual",
                    "other_representatives.0.full_name": "manual", "other_representatives.0.birth_place": "manual"},
            ))
            for table, key, parent in (("special_equipment_marks", "mark", None), ("special_equipment_models", "model", "mark"), ("special_equipment_modifications", "modification", "model")):
                values = {"id": ids[key], "code": ids[key].hex, "name": "Migration fixture", "slug": ids[key].hex}
                if parent:
                    values[parent+"_id"] = ids[parent]
                await connection.execute(meta.tables[table].insert().values(**values))
            await connection.execute(meta.tables["special_equipment_categories"].insert().values(
                id=ids["category"], code=ids["category"].hex, slug=ids["category"].hex,
                name="Migration category fixture", usage_metric="mileage_km",
            ))
            await connection.execute(meta.tables["special_equipment_modification_categories"].insert().values(
                modification_id=ids["modification"], category_id=ids["category"],
                is_primary=True, sort_order=0,
            ))
            await connection.execute(meta.tables["special_equipment_products"].insert().values(
                id=ids["product"], code=ids["product"].hex, slug=ids["product"].hex, modification_id=ids["modification"],
                seller_company_id=ids["company"], price=1000000, condition="new", no_vin=True, manufacture_year=2026,
            ))
            await connection.execute(meta.tables["special_equipment_application_items"].insert().values(
                id=ids["vehicle"], application_id=ids["application"], product_id=ids["product"], seller_company_id=ids["company"],
                currency_code="RUB", item_snapshot={}, leasing_purpose=PURPOSE, unit_price=1000000, total_price=1000000,
            ))
            await connection.execute(meta.tables["application_vehicles"].insert().values(
                id=ids["vehicle"], application_id=ids["application"], product_id=ids["product"], leasing_purpose=PURPOSE, is_model_order=False,
            ))
    finally:
        await engine.dispose()
    return ids


async def verify_migrated(url, expected, ids, head):
    target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            require(tuple((await connection.scalars(sa.text("SELECT version_num FROM alembic_version"))).all()) == (head,), "Verification requires exactly one actual current head")
            row = (await connection.execute(sa.text("SELECT * FROM application_questionnaires WHERE id=:id"), {"id": ids["questionnaire"]})).mappings().one()
            require(row["application_id"] == ids["application"], "Migration replaced questionnaire identity")
            fields = ("founders", "beneficiaries", "other_representatives")
            person_ids = {field: [str(UUID(person["id"])) for person in row[field]] for field in fields}
            require(person_ids["beneficiaries"] == [str(ids["preserved_beneficiary"])], "Existing UUID changed during migration")
            for path in row["field_sources"]:
                field, dot, tail = path.partition(".")
                if dot and field in fields:
                    require(str(UUID(tail.split(".", 1)[0])) == tail.split(".", 1)[0], "Migration retained a legacy source key")
            sources = row["field_sources"]
            founder = row["founders"][0]
            require(founder["name"] == "Ручное имя" and founder["share"] is None, "Migration changed manual values")
            require(sources[f"founders.{founder['id']}.share"] == "manual", "Manual null lost its source")
            deleted = row["people_identity_map"]["founders"]["inn/000000009902"][0]
            require(sources[f"founders.{deleted}"] == "manual", "Legacy tombstone was lost")
            require(sources[f"beneficiaries.{ids['preserved_beneficiary']}.birth_place"] == "manual", "Mixed old/new source path was not migrated")
            require(sources[f"other_representatives.{person_ids['other_representatives'][0]}.birth_place"] == "manual", "Index source path was not migrated")
            purposes = await connection.scalar(sa.text("SELECT leasing_purposes FROM application_vehicles WHERE id=:id"), {"id": ids["vehicle"]})
            require(purposes == [PURPOSE], "Migration split a legacy purpose phrase")
            equipment_purposes = await connection.scalar(sa.text("SELECT leasing_purposes FROM special_equipment_application_items WHERE id=:id"), {"id": ids["vehicle"]})
            require(equipment_purposes == [PURPOSE], "Migration split the legacy equipment purpose phrase")
            require(row["vehicle_purchase_purpose"] == {"vehicles": [{"vehicle_id": str(ids["vehicle"]), "purposes": [PURPOSE]}]}, "Purpose projection lost application vehicle UUID")
            require(await connection.scalar(sa.text("SELECT count(*) FROM application_questionnaires WHERE application_id=:id"), {"id": ids["application"]}) == 1, "Migration duplicated questionnaire")
    finally:
        await engine.dispose()



DEFAULTS_154 = {
    "loans_credits_leasing": {"status": "missing", "text": "Данные о кредитах, займах и лизинге отсутствуют", "documents": []},
    "third_party_guarantees": {"status": "missing", "text": "Данные о поручительствах за третьих лиц отсутствуют", "documents": []},
    "additional_collateral_available": {"status": "missing", "text": "Данные о возможности предоставления дополнительного обеспечения отсутствуют", "documents": []},
    "state_defense_order": {"status": "missing", "text": "Документ о гособоронзаказе не предоставлен", "documents": []},
    "director_appointment_document": {"status": "missing", "text": "Документ о назначении руководителя не предоставлен", "documents": []},
    "postal_address_matches_legal": False,
    "website_in_blocked_domains_registry": False,
    "director_is_pdl": False,
    "director_name_changed": False,
}
DEFAULTS_DATE = datetime(2026, 9, 20, 12, 30, tzinfo=UTC)


async def seed_defaults_153(url, expected, company_id):
    target_url(url, expected)
    engine = create_async_engine(url)
    meta = sa.MetaData()
    cases = {}
    try:
        async with engine.begin() as connection:
            await verify_connection(connection, expected)
            require(tuple((await connection.scalars(sa.text("SELECT version_num FROM alembic_version"))).all()) == ("153",), "Default seeding requires only actual revision 153")
            await connection.run_sync(meta.reflect, only=["leasing_applications", "application_questionnaires"])
            for case in ("missing", "explicit_null", "nested_null", "existing"):
                app_id, qid = uuid4(), uuid4()
                await connection.execute(meta.tables["leasing_applications"].insert().values(id=app_id, company_id=company_id, name="Migration 154 " + case))
                values = dict.fromkeys(DEFAULTS_154, sa.null())
                sources = {}
                wanted = dict(DEFAULTS_154)
                if case == "explicit_null":
                    # Alternate manual and document-request root clears, including JSON null.
                    values = dict.fromkeys(DEFAULTS_154)
                    sources = {field: "manual" if index % 2 else "document_request" for index, field in enumerate(DEFAULTS_154)}
                    wanted = dict.fromkeys(DEFAULTS_154)
                elif case == "nested_null":
                    for index, (field, value) in enumerate(DEFAULTS_154.items()):
                        if isinstance(value, dict):
                            values[field] = None
                            sources[field + ".text"] = "manual" if index % 2 else "document_request"
                            wanted[field] = None
                elif case == "existing":
                    values = {
                        "loans_credits_leasing": {"status": "attached", "text": None, "documents": [{"document_id": str(uuid4()), "user_title": "Existing contract"}]},
                        "third_party_guarantees": {}, "additional_collateral_available": [],
                        "state_defense_order": {"status": "missing", "text": "Ручной текст", "documents": []},
                        "director_appointment_document": {"text": None},
                        "postal_address_matches_legal": True, "website_in_blocked_domains_registry": False,
                        "director_is_pdl": True, "director_name_changed": False,
                    }
                    sources = {"loans_credits_leasing.text": "manual", "director_appointment_document.text": "document_request"}
                    wanted = dict(values)
                await connection.execute(meta.tables["application_questionnaires"].insert().values(
                    id=qid, application_id=app_id, **values, field_sources=sources,
                    questionnaire_completed_at=DEFAULTS_DATE, created_at=DEFAULTS_DATE, updated_at=DEFAULTS_DATE,
                ))
                cases[case] = {"id": qid, "application_id": app_id, "values": wanted, "sources": sources}
    finally:
        await engine.dispose()
    return cases


async def verify_defaults_migrated(url, expected, cases):
    target_url(url, expected)
    engine = create_async_engine(url)
    snapshots = {}
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            for name, case in cases.items():
                row = dict((await connection.execute(sa.text("SELECT * FROM application_questionnaires WHERE id=:id"), {"id": case["id"]})).mappings().one())
                require(row["application_id"] == case["application_id"], "Backfill changed application link")
                for field, value in case["values"].items():
                    require(row[field] == value, f"Backfill lost {name}.{field}")
                require(all(row["field_sources"].get(path) == source for path, source in case["sources"].items()), "Backfill lost explicit field source")
                require(all(row[field] == DEFAULTS_DATE for field in ("created_at", "updated_at", "questionnaire_completed_at")), "Backfill changed delivery/edit timestamps")
                snapshots[name] = row
    finally:
        await engine.dispose()
    return snapshots



async def questionnaire_snapshots(url, expected):
    target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            rows = (await connection.execute(sa.text("SELECT * FROM application_questionnaires ORDER BY id"))).mappings()
            return {row["id"]: dict(row) for row in rows}
    finally:
        await engine.dispose()


async def verify_branch_schema(url, expected, *, published, address):
    """Prove branch starting states from schema, not just alembic_version."""
    target_url(url, expected)
    engine = create_async_engine(url)
    expected_columns = {
        "special_equipment_categories": {"is_visible_in_catalog"},
        "special_equipment_models": {"category_id"},
        "special_equipment_products": {"chassis_vin", "superstructure_vin"},
    }
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            for table, columns in expected_columns.items():
                actual = await connection.run_sync(lambda sync, table=table: {
                    column["name"] for column in sa.inspect(sync).get_columns(table)
                })
                require((columns <= actual) if published else not (columns & actual), f"Unexpected published-154 columns in {table}")
            junction = await connection.run_sync(lambda sync: sa.inspect(sync).has_table("special_equipment_superstructure_categories"))
            require(junction is published, "Unexpected published-154 junction table")
            questionnaire_columns = await connection.run_sync(lambda sync: {
                column["name"] for column in sa.inspect(sync).get_columns("application_questionnaires")
            })
            require(("actual_address_same_as_legal" in questionnaire_columns) is address, "Unexpected local-155 address column")
    finally:
        await engine.dispose()


async def verify_published_values(url, expected, ids, sentinel=None):
    target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            await verify_connection(connection, expected)
            category = await connection.scalar(sa.text("SELECT category_id FROM special_equipment_models WHERE id=:id"), {"id": ids["model"]})
            require(category == ids["category"], "Published migration lost model-category backfill")
            visible = await connection.scalar(sa.text("SELECT is_visible_in_catalog FROM special_equipment_categories WHERE id=:id"), {"id": ids["category"]})
            require(visible is (sentinel is None), "Published category visibility was reset")
            if sentinel is not None:
                product = (await connection.execute(sa.text(
                    "SELECT no_vin, vin, chassis_vin, superstructure_vin FROM special_equipment_products WHERE id=:id"
                ), {"id": ids["product"]})).mappings().one()
                require(dict(product) == sentinel["product"], "Merge changed existing published VIN values")
                linked = await connection.scalar(sa.text(
                    "SELECT count(*) FROM special_equipment_superstructure_categories WHERE superstructure_id=:superstructure AND category_id=:category"
                ), {"superstructure": sentinel["superstructure_id"], "category": ids["category"]})
                require(linked == 1, "Merge lost existing published category relation")
    finally:
        await engine.dispose()


async def seed_published_values(url, expected, ids):
    target_url(url, expected)
    engine = create_async_engine(url)
    meta = sa.MetaData()
    superstructure_id = uuid4()
    product = {"no_vin": False, "vin": "E2EBASEVIN000001", "chassis_vin": "E2ECHASSIS000001", "superstructure_vin": "E2ESUPER000001"}
    try:
        async with engine.begin() as connection:
            await verify_connection(connection, expected)
            await connection.run_sync(meta.reflect, only=["special_equipment_products", "special_equipment_categories", "special_equipment_superstructures", "special_equipment_superstructure_categories"])
            await connection.execute(meta.tables["special_equipment_products"].update().where(
                meta.tables["special_equipment_products"].c.id == ids["product"]
            ).values(**product))
            await connection.execute(meta.tables["special_equipment_categories"].update().where(
                meta.tables["special_equipment_categories"].c.id == ids["category"]
            ).values(is_visible_in_catalog=False))
            await connection.execute(meta.tables["special_equipment_superstructures"].insert().values(
                id=superstructure_id, code=superstructure_id.hex, slug=superstructure_id.hex,
                name="Published branch fixture " + superstructure_id.hex,
            ))
            await connection.execute(meta.tables["special_equipment_superstructure_categories"].insert().values(
                superstructure_id=superstructure_id, category_id=ids["category"],
            ))
    finally:
        await engine.dispose()
    return {"product": product, "superstructure_id": superstructure_id}


async def seed_local_address(url, expected, questionnaire_id):
    target_url(url, expected)
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await verify_connection(connection, expected)
            await connection.execute(sa.text("""
                UPDATE application_questionnaires
                SET legal_address='Казань, адрес до объединения, 155',
                    actual_address='Казань, адрес до объединения, 155',
                    actual_address_same_as_legal=true,
                    management_company_details='[{"name":"УК до миграции", "inn":"7701234567", "ogrn":"1027700000000"}]'::jsonb,
                    field_sources=field_sources || '{"legal_address":"manual","actual_address":"manual","actual_address_same_as_legal":"manual","management_company_details":"manual"}'::jsonb
                WHERE id=:id
            """), {"id": questionnaire_id})
    finally:
        await engine.dispose()


def migrated_management_snapshot(rows):
    from copy import deepcopy
    rows = deepcopy(rows)
    for row in rows.values():
        value = row.get("management_company_details")
        if isinstance(value, dict) and "requisites" in value and "status" in value:
            continue
        row["management_company_details"] = {
            "requisites": value, "status": "not_provided", "file_name": None, "documents": [],
        }
        row["field_sources"] = {
            ("management_company_details.requisites" + key[len("management_company_details"):]
             if key == "management_company_details" or key.startswith("management_company_details.")
             else key): source for key, source in (row.get("field_sources") or {}).items()
        }
    return rows


def verify_published_questionnaire_preservation(before, after):
    before = migrated_management_snapshot(before)
    require(before.keys() == after.keys(), "Merge changed the set of questionnaires")
    for qid, previous in before.items():
        current = after[qid]
        for field, value in previous.items():
            if field not in (*DEFAULTS_154, "field_sources"):
                require(current[field] == value, f"Merge changed existing questionnaire field {field}")
        require(current["actual_address_same_as_legal"] is False, "Local address migration did not initialize false")
        for path, source in previous["field_sources"].items():
            require(current["field_sources"].get(path) == source, "Merge replaced an existing field source")


def run():
    settings = guard()
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    original_name, original_url = settings.db_name, settings.database_url
    original_dsn = settings.database_dsn
    shared_revisions = asyncio.run(database_revisions(original_dsn, original_name))
    admin_url = sa.engine.make_url(original_dsn).set(database="postgres")
    config = Config("/source/alembic.ini")
    config.set_main_option("script_location", "/source/alembic")
    config.set_main_option("prepend_sys_path", "/source")
    graph = ScriptDirectory.from_config(config)
    require(len(graph.get_heads()) == 1, "Migration graph must have exactly one current head")
    head = graph.get_current_head()
    try:
        for scenario in ("legacy", "published154", "local155"):
            name = "questionnaire22286_m150_" + uuid4().hex[:16]
            isolated_dsn = sa.engine.make_url(original_dsn).set(database=name).render_as_string(hide_password=False)
            asyncio.run(database_operation(admin_url, name, create=True))
            try:
                settings.db_name = name
                settings.database_url = isolated_dsn
                # database_dsn is cached_property; invalidate its old DB value.
                settings.__dict__.pop("database_dsn", None)
                target_url(settings.database_dsn, name)
                isolated_alembic(command.upgrade, config, settings, name, "149")
                require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("149",), "Upgrade did not reach only revision 149")
                ids = asyncio.run(seed_legacy(settings.database_dsn, name))
                isolated_alembic(command.upgrade, config, settings, name, "153")
                defaults = asyncio.run(seed_defaults_153(settings.database_dsn, name, ids["company"]))
                published_values = None
                branch_snapshot = None
                if scenario == "published154":
                    isolated_alembic(command.upgrade, config, settings, name, "154")
                    require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("154",), "Published starting state must be actual revision 154")
                    asyncio.run(verify_branch_schema(settings.database_dsn, name, published=True, address=False))
                    asyncio.run(verify_published_values(settings.database_dsn, name, ids))
                    published_values = asyncio.run(seed_published_values(settings.database_dsn, name, ids))
                    branch_snapshot = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))
                elif scenario == "local155":
                    isolated_alembic(command.upgrade, config, settings, name, "155")
                    require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("155",), "Local starting state must be actual revision 155")
                    asyncio.run(verify_branch_schema(settings.database_dsn, name, published=False, address=True))
                    asyncio.run(verify_defaults_migrated(settings.database_dsn, name, defaults))
                    asyncio.run(seed_local_address(settings.database_dsn, name, defaults["existing"]["id"]))
                    branch_snapshot = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))

                isolated_alembic(command.upgrade, config, settings, name, "head")
                require(asyncio.run(database_revisions(settings.database_dsn, name)) == (head,), "Upgrade left multiple or unexpected database heads")
                asyncio.run(verify_branch_schema(settings.database_dsn, name, published=True, address=True))
                asyncio.run(verify_migrated(settings.database_dsn, name, ids, head))
                asyncio.run(verify_defaults_migrated(settings.database_dsn, name, defaults))
                asyncio.run(verify_published_values(settings.database_dsn, name, ids, published_values))
                merged = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))
                if scenario == "published154":
                    verify_published_questionnaire_preservation(branch_snapshot, merged)
                elif scenario == "local155":
                    require(merged == migrated_management_snapshot(branch_snapshot), "Upgrade lost existing local questionnaire values or manual sources")
                else:
                    isolated_alembic(command.downgrade, config, settings, name, "153")
                    require(asyncio.run(database_revisions(settings.database_dsn, name)) == ("153",), "Downgrade did not return both branches to 153")
                    asyncio.run(verify_branch_schema(settings.database_dsn, name, published=False, address=False))
                    isolated_alembic(command.upgrade, config, settings, name, "head")
                    asyncio.run(verify_migrated(settings.database_dsn, name, ids, head))
                    asyncio.run(verify_defaults_migrated(settings.database_dsn, name, defaults))
                    asyncio.run(verify_branch_schema(settings.database_dsn, name, published=True, address=True))
                    asyncio.run(verify_published_values(settings.database_dsn, name, ids))
                    replayed = asyncio.run(questionnaire_snapshots(settings.database_dsn, name))
                    require(replayed == merged, "Replaying migrations changed questionnaire rows")
                isolated_alembic(command.check, config, settings, name)
                progress("migration_branch_upgrade_passed", scenario=scenario, database=name, revision=head)
            finally:
                settings.db_name = original_name
                settings.database_url = original_url
                settings.__dict__.pop("database_dsn", None)
                asyncio.run(database_operation(admin_url, name, create=False))
                require(asyncio.run(database_revisions(settings.database_dsn, original_name)) == shared_revisions, "Shared database revisions changed")
    finally:
        settings.db_name = original_name
        settings.database_url = original_url
        settings.__dict__.pop("database_dsn", None)
        require(asyncio.run(database_revisions(settings.database_dsn, original_name)) == shared_revisions, "Shared database revisions changed")


if __name__ == "__main__":
    run()
