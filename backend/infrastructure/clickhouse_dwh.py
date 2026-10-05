"""ClickHouse DWH table schemas for the analytics platform.

All tables are created idempotently by ``ensure_dwh_tables()`` which is
called from ``clickhouse.ensure_tables()`` on event-worker startup.

Table naming: ``dwh_<entity>``
Engines: ``ReplacingMergeTree(updated_at)`` for mutable entities,
``MergeTree()`` for append-only.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# DWH tables (source replicas from Postgres)
# ---------------------------------------------------------------------------

# Idempotent ALTERs applied after CREATE so existing tables gain new columns
# (CREATE TABLE IF NOT EXISTS never alters an already-created table).
_DWH_ALTERS: list[str] = [
    "ALTER TABLE dwh_leasing_company_applications "
    "ADD COLUMN IF NOT EXISTS leasing_company_name Nullable(String) AFTER model_name",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS application_id Nullable(UUID) AFTER leasing_company_application_id",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS leasing_company_id Nullable(UUID) AFTER application_id",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS dealer_id Nullable(UUID) AFTER leasing_company_id",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS dealer_company_id Nullable(UUID) AFTER dealer_id",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS client_company_id Nullable(UUID) AFTER dealer_company_id",
    "ALTER TABLE dwh_leasing_proposals "
    "ADD COLUMN IF NOT EXISTS distributor_id Nullable(UUID) AFTER client_company_id",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS production_date_from Nullable(Date) AFTER production_year_to",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS production_date_to Nullable(Date) AFTER production_date_from",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS delivery_date_from Nullable(Date) AFTER production_date_to",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS delivery_date_to Nullable(Date) AFTER delivery_date_from",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS is_compatible UInt8 DEFAULT 0 AFTER is_active",
    "ALTER TABLE dwh_support_programs "
    "ADD COLUMN IF NOT EXISTS compatible_support_ids Nullable(String) AFTER is_compatible",
]

_DWH_TABLES: dict[str, str] = {
    "dwh_lca_status_history": """
        CREATE TABLE IF NOT EXISTS dwh_lca_status_history (
            event_id               UUID,
            lca_id                 UUID,
            application_id         Nullable(UUID),
            old_status             Nullable(String),
            new_status             String,
            changed_at             DateTime64(3, 'UTC'),
            changed_by             Nullable(UUID),
            reason                 Nullable(String),
            application_created_at Nullable(DateTime64(3, 'UTC')),
            lca_created_at         DateTime64(3, 'UTC'),
            dealer_company_id      Nullable(UUID),
            distributor_id         Nullable(UUID),
            leasing_company_id     Nullable(UUID),
            is_baseline            UInt8 DEFAULT 0,
            ingested_at            DateTime64(3, 'UTC')
        ) ENGINE = ReplacingMergeTree(ingested_at)
        PARTITION BY toYYYYMM(changed_at)
        ORDER BY (lca_id, changed_at, event_id)
    """,
    "dwh_leasing_company_applications": """
        CREATE TABLE IF NOT EXISTS dwh_leasing_company_applications (
            lca_id                  UUID,
            application_id          Nullable(UUID),
            leasing_company_id      Nullable(UUID),
            -- Denormalized bridge fields (from LCA/LA events)
            dealer_id               Nullable(UUID),
            dealer_company_id       Nullable(UUID),
            client_company_id       Nullable(UUID),
            distributor_id          Nullable(UUID),
            display_number          Nullable(String),
            vehicle_id              Nullable(UUID),
            -- Denormalized application fields (merged from dwh_leasing_applications)
            name                    Nullable(String),
            email                   Nullable(String),
            application_status      Nullable(String),
            total_amount            Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            total_cost              Nullable(Decimal(15,2)),
            markup                  Nullable(Decimal(15,2)),
            rate                    Nullable(Decimal(5,2)),
            total_interest          Nullable(Decimal(15,2)),
            buyout_amount           Nullable(Decimal(15,2)),
            vat_refund              Nullable(Decimal(15,2)),
            profit_tax_savings      Nullable(Decimal(15,2)),
            total_savings           Nullable(Decimal(15,2)),
            selected_leasing_companies Nullable(String),   -- JSON Array
            leasing_company_comments Nullable(String),
            requested_documents     Nullable(String),       -- JSON
            questionnaire_completed Nullable(UInt8) DEFAULT 0,
            questionnaire_progress  Nullable(Int32),
            current_stage           Nullable(String),
            -- LCA fields
            status                  Nullable(String),
            review_notes            Nullable(String),
            decision_comment        Nullable(String),
            response_pdf_s3_key     Nullable(String),
            response_pdf_file_name  Nullable(String),
            response_pdf_size       Nullable(Int32),
            response_pdf_uploaded_at Nullable(DateTime64(3)),
            submitted_at            Nullable(DateTime64(3)),
            vehicle_mark_id         Nullable(String),
            vehicle_model_id        Nullable(String),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            mark_name               Nullable(String),
            model_name              Nullable(String),
            leasing_company_name    Nullable(String),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (lca_id, leasing_company_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_leasing_proposals": """
        CREATE TABLE IF NOT EXISTS dwh_leasing_proposals (
            proposal_id             UUID,
            leasing_company_application_id UUID,
            application_id          Nullable(UUID),
            leasing_company_id      Nullable(UUID),
            dealer_id               Nullable(UUID),
            dealer_company_id       Nullable(UUID),
            client_company_id       Nullable(UUID),
            distributor_id          Nullable(UUID),
            kind                    Nullable(String),
            position                Nullable(Int32),
            total_amount            Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            total_cost              Nullable(Decimal(15,2)),
            markup                  Nullable(Decimal(15,2)),
            rate                    Nullable(Decimal(5,2)),
            total_interest          Nullable(Decimal(15,2)),
            buyout_amount           Nullable(Decimal(15,2)),
            vat_refund              Nullable(Decimal(15,2)),
            profit_tax_savings      Nullable(Decimal(15,2)),
            total_savings           Nullable(Decimal(15,2)),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            leasing_company_name    Nullable(String),
            client_decision_action  Nullable(String),
            client_decision_at      Nullable(DateTime64(3)),
            client_decision_comment Nullable(String),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (proposal_id, leasing_company_application_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_documents": """
        CREATE TABLE IF NOT EXISTS dwh_documents (
            document_id             UUID,
            company_id              UUID,
            document_type           Nullable(String),
            file_path               Nullable(String),
            file_name               Nullable(String),
            file_size               Nullable(Int32),
            s3_key                  Nullable(String),
            period_label            Nullable(String),
            comments                Nullable(String),
            is_required             UInt8 DEFAULT 0,
            status                  Nullable(String),
            version                 Nullable(Int32),
            parent_document_id      Nullable(UUID),
            is_current_version      UInt8 DEFAULT 1,
            related_application_id  Nullable(UUID),
            approved_by_leasing_company Nullable(UUID),
            leasing_company_status  Nullable(String),
            leasing_company_comments Nullable(String),
            leasing_company_reviewed_at Nullable(DateTime64(3)),
            extracted_data          Nullable(String),       -- JSON
            recognition_status      Nullable(String),
            recognition_error       Nullable(String),
            dbrain_task_id          Nullable(String),
            recognized_at           Nullable(DateTime64(3)),
            uploaded_at             Nullable(DateTime64(3)),
            verified_at             Nullable(DateTime64(3)),
            verified_by             Nullable(UUID),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (document_id, company_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_vehicles": """
        CREATE TABLE IF NOT EXISTS dwh_vehicles (
            vehicle_id              UUID,
            vin                     Nullable(String),
            dealer_id               Nullable(UUID),
            mark_id                 Nullable(String),
            model_id                Nullable(String),
            generation_id           Nullable(String),
            configuration_id        Nullable(String),
            complectation_id        Nullable(String),
            year                    Nullable(Int32),
            base_price              Nullable(Decimal(12,2)),
            special_price           Nullable(Decimal(12,2)),
            dealer_cost             Nullable(Decimal(12,2)),
            discount_price          Nullable(Decimal(12,2)),
            color                   Nullable(String),
            color_inter             Nullable(String),
            images                  Nullable(String),       -- JSON
            status                  Nullable(String),
            is_available            UInt8 DEFAULT 1,
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(vehicle_id)) % 16
        ORDER BY (vehicle_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_application_vehicles": """
        CREATE TABLE IF NOT EXISTS dwh_application_vehicles (
            id                      UUID,
            application_id          UUID,
            vehicle_id              Nullable(UUID),
            modification_id         Nullable(String),
            quantity                Nullable(Int32),
            unit_price              Nullable(Decimal(15,2)),
            total_price             Nullable(Decimal(15,2)),
            comment                 Nullable(String),
            vin                     Nullable(String),
            vin_assigned_by         Nullable(UUID),
            vin_assigned_at         Nullable(DateTime64(3)),
            is_model_order          UInt8 DEFAULT 0,
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(id)) % 16
        ORDER BY (application_id, id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_companies": """
        CREATE TABLE IF NOT EXISTS dwh_companies (
            company_id              UUID,
            name                    Nullable(String),
            inn                     Nullable(String),
            kpp                     Nullable(String),
            ogrn                    Nullable(String),
            company_type            Nullable(String),
            address                 Nullable(String),       -- JSON
            contact_info            Nullable(String),       -- JSON
            legal_address           Nullable(String),
            actual_address          Nullable(String),
            phone                   Nullable(String),
            email                   Nullable(String),
            website                 Nullable(String),
            is_active               UInt8 DEFAULT 1,
            full_name               Nullable(String),
            short_name              Nullable(String),
            okpo                    Nullable(String),
            okato                   Nullable(String),
            legal_form              Nullable(String),
            region                  Nullable(String),
            city                    Nullable(String),
            registration_date       Nullable(Date),
            employees_count         Nullable(Int32),
            main_okved_code         Nullable(String),
            main_okved_description  Nullable(String),
            director_full_name      Nullable(String),
            bank_bik                Nullable(String),
            bank_name               Nullable(String),
            authorized_capital      Nullable(Int64),
            net_profit              Nullable(Int64),
            reporting_year          Nullable(Int32),
            tax_system              Nullable(String),
            enrichment_status       Nullable(String),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(company_id)) % 16
        ORDER BY (company_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_users": """
        CREATE TABLE IF NOT EXISTS dwh_users (
            user_id                 UUID,
            email                   Nullable(String),
            name                    Nullable(String),
            role                    Nullable(String),
            company_id              Nullable(UUID),
            phone                   Nullable(String),
            is_active               UInt8 DEFAULT 1,
            email_verified          UInt8 DEFAULT 0,
            phone_verified          UInt8 DEFAULT 0,
            last_login              Nullable(DateTime64(3)),
            deleted_at              Nullable(DateTime64(3)),
            mfa_enabled             UInt8 DEFAULT 0,
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(user_id)) % 16
        ORDER BY (user_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_purchase_orders": """
        CREATE TABLE IF NOT EXISTS dwh_purchase_orders (
            order_id                UUID,
            user_id                 UUID,
            vehicle_id              UUID,
            purchase_type           Nullable(String),
            status                  Nullable(String),
            total_price             Decimal(15,2),
            paid_amount             Decimal(15,2) DEFAULT 0,
            remaining_amount        Decimal(15,2) DEFAULT 0,
            leasing_application_id  Nullable(UUID),
            cancellation_reason     Nullable(String),
            cancellation_requested_at Nullable(DateTime64(3)),
            cancelled_at            Nullable(DateTime64(3)),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (order_id, user_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_calculations": """
        CREATE TABLE IF NOT EXISTS dwh_calculations (
            calc_id                 UUID,
            user_id                 Nullable(UUID),
            vehicle_ids             Nullable(String),       -- JSON Array
            total_amount            Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            total_cost              Nullable(Decimal(15,2)),
            markup                  Nullable(Decimal(15,2)),
            rate                    Nullable(Decimal(5,2)),
            total_interest          Nullable(Decimal(15,2)),
            buyout_amount           Nullable(Decimal(15,2)),
            vat_refund              Nullable(Decimal(15,2)),
            profit_tax_savings      Nullable(Decimal(15,2)),
            total_savings           Nullable(Decimal(15,2)),
            calculation_type        Nullable(String),
            created_at              Nullable(DateTime64(3))
        ) ENGINE = MergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (calc_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_questionnaires": """
        CREATE TABLE IF NOT EXISTS dwh_questionnaires (
            questionnaire_id        UUID,
            application_id          UUID,
            full_company_name       Nullable(String),
            short_company_name      Nullable(String),
            inn                     Nullable(String),
            ogrn                    Nullable(String),
            kpp                     Nullable(String),
            okpo                    Nullable(String),
            okato                   Nullable(String),
            okved_main              Nullable(String),
            tax_system              Nullable(String),
            legal_form              Nullable(String),
            legal_address           Nullable(String),
            actual_address          Nullable(String),
            phone                   Nullable(String),
            email                   Nullable(String),
            director_full_name      Nullable(String),
            director_position       Nullable(String),
            director_phone          Nullable(String),
            director_email          Nullable(String),
            founders                Nullable(String),       -- JSON
            beneficiaries           Nullable(String),       -- JSON
            has_beneficiary         UInt8 DEFAULT 0,
            management_bodies       Nullable(String),       -- JSON
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(questionnaire_id)) % 16
        ORDER BY (application_id, questionnaire_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_exchange_requests": """
        CREATE TABLE IF NOT EXISTS dwh_exchange_requests (
            request_id              UUID,
            lc_user_id              UUID,
            vehicle_id              UUID,
            quantity                Int32 DEFAULT 1,
            expiration_date         Nullable(Date),
            discount_type           Nullable(String),
            discount_value          Nullable(Decimal(15,2)),
            file_url                Nullable(String),
            file_name               Nullable(String),
            status                  Nullable(String),
            accepted_bid_id         Nullable(UUID),
            batch_number            Nullable(Int32),
            batch_index             Nullable(Int32),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (request_id, lc_user_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_exchange_bids": """
        CREATE TABLE IF NOT EXISTS dwh_exchange_bids (
            bid_id                  UUID,
            request_id              UUID,
            dealer_id               UUID,
            price                   Decimal(15,2),
            comment                 Nullable(String),
            is_accepted             UInt8 DEFAULT 0,
            kp_file_url             Nullable(String),
            kp_file_name            Nullable(String),
            kp_status               Nullable(String),
            kp_dealer_comment       Nullable(String),
            kp_sent_at              Nullable(DateTime64(3)),
            kp_responded_at         Nullable(DateTime64(3)),
            quantity                Int32 DEFAULT 1,
            bid_file_url            Nullable(String),
            bid_file_name           Nullable(String),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (bid_id, request_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_support_programs": """
        CREATE TABLE IF NOT EXISTS dwh_support_programs (
            program_id              UUID,
            name                    Nullable(String),
            mark_id                 Nullable(String),
            model_id                Nullable(String),
            model_ids               Nullable(String),       -- JSON Array
            complectation_ids       Nullable(String),       -- JSON Array
            vin                     Nullable(String),
            vins                    Nullable(String),       -- JSON Array
            dealer_group_id         Nullable(UUID),
            distributor_id          Nullable(UUID),
            support_type            Nullable(String),
            support_params          Nullable(String),       -- JSON
            production_year_from    Nullable(Int32),
            production_year_to      Nullable(Int32),
            production_date_from    Nullable(Date),
            production_date_to      Nullable(Date),
            delivery_date_from      Nullable(Date),
            delivery_date_to        Nullable(Date),
            starts_at               Nullable(Date),
            ends_at                 Nullable(Date),
            is_active               UInt8 DEFAULT 1,
            is_compatible           UInt8 DEFAULT 0,
            compatible_support_ids  Nullable(String),       -- JSON Array
            show_to_leasing_company UInt8 DEFAULT 1,
            show_to_client          UInt8 DEFAULT 1,
            comment                 Nullable(String),
            created_by              Nullable(UUID),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY cityHash64(toString(program_id)) % 16
        ORDER BY (program_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dwh_compensations": """
        CREATE TABLE IF NOT EXISTS dwh_compensations (
            compensation_id         UUID,
            applied_support_id      UUID,
            application_id          Nullable(UUID),
            exchange_request_id     Nullable(UUID),
            source                  String DEFAULT 'platform',
            vehicle_id              Nullable(UUID),
            payer                   Nullable(String),
            recipient               Nullable(String),
            calculation_base        Nullable(String),
            calculation_base_amount Decimal(15,2),
            value_type              Nullable(String),
            value                   Decimal(15,2),
            min_amount              Nullable(Decimal(15,2)),
            max_amount              Nullable(Decimal(15,2)),
            min_percent             Nullable(Decimal(10,4)),
            max_percent             Nullable(Decimal(10,4)),
            amount                  Decimal(15,2),
            status                  Nullable(String),
            payment_schedule_type   Nullable(String),
            payment_schedule_period Nullable(String),
            payment_schedule_value  Nullable(String),
            due_date                Nullable(Date),
            paid_at                 Nullable(DateTime64(3)),
            documents               Nullable(String),       -- JSON
            comment                 Nullable(String),
            created_by              Nullable(UUID),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3),
            _deleted                UInt8 DEFAULT 0
        ) ENGINE = ReplacingMergeTree(updated_at)
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (compensation_id, application_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,
}

_DWH_TABLES.update(
    {
        "dwh_special_equipment_products": """
            CREATE TABLE IF NOT EXISTS dwh_special_equipment_products (
                product_id                       UUID,
                manufacturer_id                  UUID,
                manufacturer_name                String,
                seller_company_id                Nullable(UUID),
                model                            String,
                modification                     Nullable(String),
                price                            Nullable(Decimal(15,2)),
                currency_code                    LowCardinality(String),
                manufacture_year                 Nullable(UInt16),
                publication_status               LowCardinality(String),
                sale_status                      LowCardinality(String),
                published_at                     Nullable(DateTime64(3, 'UTC')),
                primary_category_id              Nullable(UUID),
                primary_category_name            Nullable(String),
                category_ids                     Array(UUID),
                category_path_ids                Array(UUID),
                category_path_names              Array(String),
                numeric_attributes               Map(String, Decimal(20,4)),
                text_attributes                  Map(String, String),
                boolean_attributes               Map(String, UInt8),
                attribute_count                  UInt16,
                missing_required_attribute_codes Array(String),
                image_count                      UInt16,
                has_primary_image                UInt8,
                has_description                  UInt8,
                created_at                       DateTime64(3, 'UTC'),
                source_updated_at                DateTime64(3, 'UTC'),
                projected_at                     DateTime64(6, 'UTC'),
                _deleted                         UInt8 DEFAULT 0
            ) ENGINE = ReplacingMergeTree(projected_at)
            PARTITION BY cityHash64(toString(product_id)) % 16
            ORDER BY product_id
            SETTINGS index_granularity = 8192
        """,
        "dwh_special_equipment_categories": """
            CREATE TABLE IF NOT EXISTS dwh_special_equipment_categories (
                category_id                       UUID,
                parent_id                         Nullable(UUID),
                name                              String,
                slug                              String,
                depth                             UInt8,
                path_ids                          Array(UUID),
                path_names                        Array(String),
                has_image                         UInt8,
                sort_order                        UInt32,
                is_active                         UInt8,
                effective_filter_codes            Array(String),
                effective_visible_attribute_codes Array(String),
                effective_required_attribute_codes Array(String),
                created_at                        DateTime64(3, 'UTC'),
                source_updated_at                 DateTime64(3, 'UTC'),
                projected_at                      DateTime64(6, 'UTC'),
                _deleted                          UInt8 DEFAULT 0
            ) ENGINE = ReplacingMergeTree(projected_at)
            ORDER BY category_id
            SETTINGS index_granularity = 8192
        """,
        "fct_special_equipment_events": """
            CREATE TABLE IF NOT EXISTS fct_special_equipment_events (
                event_id                UUID,
                schema_version          UInt16,
                event_name              LowCardinality(String),
                occurred_at             DateTime64(3, 'UTC'),
                event_source            LowCardinality(String),
                session_id              Nullable(UUID),
                page_view_id            Nullable(UUID),
                user_id                 Nullable(UUID),
                product_id              Nullable(UUID),
                cart_item_id            Nullable(UUID),
                application_id          Nullable(UUID),
                order_id                Nullable(UUID),
                payment_id              Nullable(UUID),
                purchase_type           Nullable(String),
                payment_type            Nullable(String),
                amount                  Nullable(Decimal(15,2)),
                currency_code           Nullable(String),
                manufacturer_id         Nullable(UUID),
                selected_category_id    Nullable(UUID),
                primary_category_id     Nullable(UUID),
                category_path_ids       Array(UUID),
                position                Nullable(UInt16),
                page                    Nullable(UInt16),
                result_count            Nullable(UInt32),
                filter_codes            Array(String),
                filter_values_json      Nullable(String),
                search_query_normalized Nullable(String),
                sort_code               Nullable(String),
                device_type             LowCardinality(String),
                referrer_domain         Nullable(String),
                checkout_kind           Nullable(String),
                transition_class        Nullable(String),
                cancellation_class      Nullable(String),
                ingested_at             DateTime64(3, 'UTC')
            ) ENGINE = ReplacingMergeTree(ingested_at)
            PARTITION BY cityHash64(toString(event_id)) % 16
            ORDER BY event_id
            TTL occurred_at + INTERVAL 25 MONTH DELETE
            SETTINGS index_granularity = 8192
        """,
    }
)

# Retained only because historical ClickHouse migration 005 imports these DDL
# definitions while upgrading a clean database. Runtime bootstrap, current ORM
# metadata, and generated ER diagrams must not recreate retired analytics.
_RETIRED_DWH_TABLES: frozenset[str] = frozenset(
    {
        "dwh_special_equipment_products",
        "dwh_special_equipment_categories",
        "fct_special_equipment_events",
    }
)

# ---------------------------------------------------------------------------
# Data marts (dm_lk_*)
# ---------------------------------------------------------------------------

_DATA_MARTS: dict[str, str] = {
    "dm_lk_daily_metrics": """
        CREATE TABLE IF NOT EXISTS dm_lk_daily_metrics (
            date                    Date,
            leasing_company_id      UUID,
            distributor_id          Nullable(UUID),
            new_applications        UInt32,
            reviewed_applications   UInt32,
            approved_count          UInt32,
            rejected_count          UInt32,
            issued_count            UInt32,
            total_requested_amount  Decimal(18,2),
            total_approved_amount   Decimal(18,2),
            review_time_sum_seconds UInt64,
            review_time_count       UInt32,
            decision_time_sum_seconds UInt64,
            decision_time_count     UInt32
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(date)
        ORDER BY (date, leasing_company_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_lk_application_funnel": """
        CREATE TABLE IF NOT EXISTS dm_lk_application_funnel (
            application_id          UUID,
            leasing_company_id      UUID,
            distributor_id          Nullable(UUID),
            dealer_id               Nullable(UUID),
            dealer_company_id       Nullable(UUID),
            client_company_id       Nullable(UUID),
            display_number          Nullable(String),
            vehicle_id              Nullable(UUID),
            vehicle_mark_id         Nullable(String),
            vehicle_model_id        Nullable(String),
            application_status      Nullable(String),
            lca_status              Nullable(String),
            created_at              Nullable(DateTime64(3)),
            submitted_at            Nullable(DateTime64(3)),
            under_review_at         Nullable(DateTime64(3)),
            prescoring_at           Nullable(DateTime64(3)),
            approved_at             Nullable(DateTime64(3)),
            rejected_at             Nullable(DateTime64(3)),
            issued_at               Nullable(DateTime64(3)),
            closed_at               Nullable(DateTime64(3)),
            review_notes            Nullable(String),
            decision_comment        Nullable(String),
            total_amount            Nullable(Decimal(18,2)),
            down_payment            Nullable(Decimal(18,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(UInt8),
            monthly_payment         Nullable(Decimal(18,2)),
            total_cost              Nullable(Decimal(18,2)),
            markup                  Nullable(Decimal(6,4)),
            rate                    Nullable(Decimal(6,4)),
            total_interest          Nullable(Decimal(18,2)),
            buyout_amount           Nullable(Decimal(18,2)),
            vat_refund              Nullable(Decimal(18,2)),
            profit_tax_savings      Nullable(Decimal(18,2)),
            total_savings           Nullable(Decimal(18,2)),
            current_stage           Nullable(String),
            questionnaire_completed Nullable(UInt8) DEFAULT 0,
            status_count            UInt32 DEFAULT 1,
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (leasing_company_id, lca_status, created_at, application_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_lk_proposals": """
        CREATE TABLE IF NOT EXISTS dm_lk_proposals (
            proposal_id             UUID,
            lca_id                  UUID,
            application_id          UUID,
            leasing_company_id      UUID,
            distributor_id          Nullable(UUID),
            dealer_id               Nullable(UUID),
            kind                    Nullable(String),
            total_amount            Nullable(Decimal(18,2)),
            down_payment            Nullable(Decimal(18,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       UInt8,
            monthly_payment         Nullable(Decimal(18,2)),
            total_cost              Nullable(Decimal(18,2)),
            markup                  Nullable(Decimal(6,4)),
            rate                    Nullable(Decimal(6,4)),
            total_interest          Nullable(Decimal(18,2)),
            buyout_amount           Nullable(Decimal(18,2)),
            vat_refund              Nullable(Decimal(18,2)),
            profit_tax_savings      Nullable(Decimal(18,2)),
            total_savings           Nullable(Decimal(18,2)),
            client_decision_action  Nullable(String),
            client_decision_comment Nullable(String),
            client_decision_at      Nullable(DateTime64(3)),
            decision_speed_hours    Nullable(Float32),
            proposal_created_at     DateTime64(3),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(proposal_created_at)
        ORDER BY (leasing_company_id, kind, proposal_created_at, application_id, proposal_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_lk_financial_pipeline": """
        CREATE TABLE IF NOT EXISTS dm_lk_financial_pipeline (
            date                    Date,
            leasing_company_id      UUID,
            distributor_id          Nullable(UUID),
            pipeline_amount         Decimal(18,2),
            approved_amount         Decimal(18,2),
            issued_amount           Decimal(18,2),
            total_markup_sum        Decimal(18,4),
            markup_count            UInt32,
            total_rate_sum          Decimal(18,4),
            rate_count              UInt32,
            avg_lease_term_months_sum UInt64,
            avg_lease_term_count    UInt32
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(date)
        ORDER BY (date, leasing_company_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_financials": """
        CREATE TABLE IF NOT EXISTS dm_distributor_financials (
            date                    Date,
            dealer_company_id       Nullable(UUID),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            leasing_company_name    Nullable(String),
            kind                    Nullable(String),
            application_count       UInt64,
            pipeline_amount         Decimal(18,2),
            approved_amount         Decimal(18,2),
            issued_amount           Decimal(18,2),
            total_down_payment      Decimal(18,2),
            total_down_payment_count UInt64,
            down_payment_percent_sum Decimal(18,4),
            down_payment_percent_count UInt64,
            lease_term_months_sum   UInt64,
            lease_term_months_count UInt64,
            rate_sum                Decimal(18,4),
            rate_count              UInt64,
            markup_sum              Decimal(18,4),
            markup_count            UInt64,
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(date)
        ORDER BY (date, dealer_company_id, dealer_name, dealer_city, leasing_company_name, kind)
        TTL date + INTERVAL 3 YEAR
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_applications": """
        CREATE TABLE IF NOT EXISTS dm_distributor_applications (
            lca_id                  UUID,
            application_id          Nullable(UUID),
            leasing_company_id      Nullable(UUID),
            dealer_company_id       Nullable(UUID),
            client_company_id       Nullable(UUID),
            vehicle_id              Nullable(UUID),
            display_number          Nullable(String),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            leasing_company_name    Nullable(String),
            mark_name               Nullable(String),
            model_name              Nullable(String),
            vehicle_mark_id         Nullable(String),
            vehicle_model_id        Nullable(String),
            application_status      Nullable(String),
            lca_status              Nullable(String),
            total_amount            Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            total_cost              Nullable(Decimal(15,2)),
            markup                  Nullable(Decimal(15,2)),
            rate                    Nullable(Decimal(5,2)),
            total_interest          Nullable(Decimal(15,2)),
            buyout_amount           Nullable(Decimal(15,2)),
            vat_refund              Nullable(Decimal(15,2)),
            profit_tax_savings      Nullable(Decimal(15,2)),
            total_savings           Nullable(Decimal(15,2)),
            vehicle_price           Nullable(Decimal(15,2)),
            review_notes            Nullable(String),
            decision_comment        Nullable(String),
            submitted_at            Nullable(DateTime64(3)),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (dealer_company_id, application_status, created_at, lca_id)
        TTL toDate(assumeNotNull(created_at)) + INTERVAL 3 YEAR
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_warehouse": """
        CREATE TABLE IF NOT EXISTS dm_distributor_warehouse (
            vehicle_id              UUID,
            vin                     Nullable(String),
            dealer_id               Nullable(UUID),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            mark_id                 Nullable(String),
            model_id                Nullable(String),
            generation_id           Nullable(String),
            configuration_id        Nullable(String),
            complectation_id        Nullable(String),
            year                    Nullable(Int32),
            base_price              Nullable(Decimal(12,2)),
            special_price           Nullable(Decimal(12,2)),
            dealer_cost             Nullable(Decimal(12,2)),
            discount_price          Nullable(Decimal(12,2)),
            color                   Nullable(String),
            color_inter             Nullable(String),
            status                  Nullable(String),
            is_available            UInt8 DEFAULT 1,
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY cityHash64(toString(vehicle_id)) % 16
        ORDER BY (dealer_id, vehicle_id)
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_exchange": """
        CREATE TABLE IF NOT EXISTS dm_distributor_exchange (
            request_id              UUID,
            lc_user_id              UUID,
            vehicle_id              UUID,
            requested_dealer_id     Nullable(UUID),
            requested_dealer_name   Nullable(String),
            requested_dealer_city   Nullable(String),
            mark                    Nullable(String),
            model                   Nullable(String),
            quantity                Int32,
            expiration_date         Nullable(Date),
            discount_type           Nullable(String),
            discount_value          Nullable(Decimal(15,2)),
            file_url                Nullable(String),
            file_name               Nullable(String),
            request_status          Nullable(String),
            accepted_bid_id         Nullable(UUID),
            batch_number            Nullable(Int32),
            batch_index             Nullable(Int32),
            bids_count              UInt64 DEFAULT 0,
            accepted_bids           UInt64 DEFAULT 0,
            average_price           Nullable(Decimal(15,2)),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (requested_dealer_id, request_status, created_at, request_id)
        TTL toDate(assumeNotNull(created_at)) + INTERVAL 3 YEAR
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_sales_dc": """
        CREATE TABLE IF NOT EXISTS dm_distributor_sales_dc (
            lca_id                  UUID,
            application_id          UUID,
            leasing_company_id      Nullable(UUID),
            display_number          Nullable(String),
            dealer_company_id       Nullable(UUID),
            client_company_id       Nullable(UUID),
            vehicle_id              Nullable(UUID),
            vehicle_price           Nullable(Decimal(15,2)),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            leasing_company_name    Nullable(String),
            mark_name               Nullable(String),
            model_name              Nullable(String),
            vehicle_mark_id         Nullable(String),
            vehicle_model_id        Nullable(String),
            status                  Nullable(String),
            lca_status              Nullable(String),
            total_amount            Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            total_cost              Nullable(Decimal(15,2)),
            markup                  Nullable(Decimal(15,2)),
            rate                    Nullable(Decimal(5,2)),
            total_interest          Nullable(Decimal(15,2)),
            buyout_amount           Nullable(Decimal(15,2)),
            vat_refund              Nullable(Decimal(15,2)),
            profit_tax_savings      Nullable(Decimal(15,2)),
            total_savings           Nullable(Decimal(15,2)),
            client_decision_action  Nullable(String),
            client_decision_at      Nullable(DateTime64(3)),
            kind                    Nullable(String),
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (dealer_company_id, status, created_at, application_id, lca_id)
        TTL toDate(assumeNotNull(created_at)) + INTERVAL 3 YEAR
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,

    "dm_distributor_sales_dc_regions": """
        CREATE TABLE IF NOT EXISTS dm_distributor_sales_dc_regions (
            application_id          UUID,
            application_vehicle_id  UUID,
            vehicle_id              Nullable(UUID),
            leasing_company_id      Nullable(UUID),
            dealer_id               Nullable(UUID),
            dealer_name             Nullable(String),
            dealer_city             Nullable(String),
            dealer_region           Nullable(String),
            mark_id                 Nullable(String),
            model_id                Nullable(String),
            vin                     Nullable(String),
            quantity                Nullable(Int32),
            unit_price              Nullable(Decimal(15,2)),
            total_price             Nullable(Decimal(15,2)),
            year                    Nullable(Int32),
            base_price              Nullable(Decimal(12,2)),
            special_price           Nullable(Decimal(12,2)),
            discount_price          Nullable(Decimal(12,2)),
            color                   Nullable(String),
            application_status      Nullable(String),
            lca_status              Nullable(String),
            application_total_amount Nullable(Decimal(15,2)),
            down_payment            Nullable(Decimal(15,2)),
            down_payment_percent    Nullable(Decimal(5,2)),
            lease_term_months       Nullable(Int32),
            monthly_payment         Nullable(Decimal(12,2)),
            is_model_order          UInt8 DEFAULT 0,
            created_at              Nullable(DateTime64(3)),
            updated_at              DateTime64(3)
        ) ENGINE = SummingMergeTree()
        PARTITION BY toYYYYMM(assumeNotNull(created_at))
        ORDER BY (dealer_id, dealer_region, created_at, application_id, application_vehicle_id)
        TTL toDate(assumeNotNull(created_at)) + INTERVAL 3 YEAR
        SETTINGS allow_nullable_key = 1, index_granularity = 8192
    """,
}

_DATA_MARTS.update(
    {
        "dm_special_equipment_daily_funnel": """
            CREATE TABLE IF NOT EXISTS dm_special_equipment_daily_funnel (
                date                         Date,
                selected_category_id         Nullable(UUID),
                manufacturer_id              Nullable(UUID),
                device_type                  LowCardinality(String),
                sessions_state               AggregateFunction(uniqCombined64, Nullable(UUID)),
                impression_sessions_state    AggregateFunction(uniqCombined64, Nullable(UUID)),
                detail_sessions_state        AggregateFunction(uniqCombined64, Nullable(UUID)),
                favorite_sessions_state      AggregateFunction(uniqCombined64, Nullable(UUID)),
                cart_sessions_state          AggregateFunction(uniqCombined64, Nullable(UUID)),
                checkout_sessions_state      AggregateFunction(uniqCombined64, Nullable(UUID)),
                leasing_sessions_state       AggregateFunction(uniqCombined64, Nullable(UUID)),
                prepayment_sessions_state    AggregateFunction(uniqCombined64, Nullable(UUID)),
                purchase_sessions_state      AggregateFunction(uniqCombined64, Nullable(UUID)),
                zero_result_sessions_state   AggregateFunction(uniqCombined64, Nullable(UUID)),
                catalog_views                UInt64,
                category_views               UInt64,
                product_impressions          UInt64,
                product_opens                UInt64,
                favorite_adds                UInt64,
                cart_adds                    UInt64,
                checkout_starts              UInt64,
                leasing_applications         UInt64,
                reservation_orders           UInt64,
                full_purchase_orders         UInt64,
                prepayment_successes         UInt64,
                purchase_successes           UInt64,
                payment_failures             UInt64,
                order_cancellations          UInt64,
                zero_result_events           UInt64,
                rebuilt_at                   DateTime64(3, 'UTC')
            ) ENGINE = AggregatingMergeTree()
            PARTITION BY date
            ORDER BY (date, selected_category_id, manufacturer_id, device_type)
            SETTINGS allow_nullable_key = 1, index_granularity = 8192
        """,
        "dm_special_equipment_product_daily": """
            CREATE TABLE IF NOT EXISTS dm_special_equipment_product_daily (
                date                         Date,
                product_id                   UUID,
                manufacturer_id              Nullable(UUID),
                manufacturer_name            String,
                product_name                 String,
                primary_category_id          Nullable(UUID),
                primary_category_name        Nullable(String),
                device_type                  LowCardinality(String),
                impression_sessions_state    AggregateFunction(uniqCombined64, Nullable(UUID)),
                detail_sessions_state        AggregateFunction(uniqCombined64, Nullable(UUID)),
                cart_sessions_state          AggregateFunction(uniqCombined64, Nullable(UUID)),
                checkout_sessions_state      AggregateFunction(uniqCombined64, Nullable(UUID)),
                product_impressions          UInt64,
                product_opens                UInt64,
                favorite_adds                UInt64,
                cart_adds                    UInt64,
                checkout_starts              UInt64,
                leasing_applications         UInt64,
                prepayment_successes         UInt64,
                purchase_successes           UInt64,
                payment_failures             UInt64,
                order_cancellations          UInt64,
                position_sum                 UInt64,
                position_count               UInt64,
                rebuilt_at                   DateTime64(3, 'UTC')
            ) ENGINE = AggregatingMergeTree()
            PARTITION BY date
            ORDER BY (date, product_id, device_type)
            SETTINGS allow_nullable_key = 1, index_granularity = 8192
        """,
        "dm_special_equipment_filter_daily": """
            CREATE TABLE IF NOT EXISTS dm_special_equipment_filter_daily (
                date                         Date,
                selected_category_id         Nullable(UUID),
                filter_code                  String,
                device_type                  LowCardinality(String),
                sessions_state               AggregateFunction(uniqCombined64, Nullable(UUID)),
                zero_result_sessions_state   AggregateFunction(uniqCombined64, Nullable(UUID)),
                product_open_sessions_state  AggregateFunction(uniqCombined64, Nullable(UUID)),
                use_count                    UInt64,
                zero_result_count            UInt64,
                product_open_count           UInt64,
                rebuilt_at                   DateTime64(3, 'UTC')
            ) ENGINE = AggregatingMergeTree()
            PARTITION BY date
            ORDER BY (date, selected_category_id, filter_code, device_type)
            SETTINGS allow_nullable_key = 1, index_granularity = 8192
        """,
        "dm_special_equipment_search_daily": """
            CREATE TABLE IF NOT EXISTS dm_special_equipment_search_daily (
                date                         Date,
                search_term                  String,
                device_type                  LowCardinality(String),
                sessions_state               AggregateFunction(uniqCombined64, Nullable(UUID)),
                zero_result_sessions_state   AggregateFunction(uniqCombined64, Nullable(UUID)),
                product_open_sessions_state  AggregateFunction(uniqCombined64, Nullable(UUID)),
                cart_sessions_state          AggregateFunction(uniqCombined64, Nullable(UUID)),
                checkout_sessions_state      AggregateFunction(uniqCombined64, Nullable(UUID)),
                search_count                 UInt64,
                zero_result_count            UInt64,
                product_open_count           UInt64,
                cart_add_count               UInt64,
                checkout_count               UInt64,
                rebuilt_at                   DateTime64(3, 'UTC')
            ) ENGINE = AggregatingMergeTree()
            PARTITION BY date
            ORDER BY (date, search_term, device_type)
            SETTINGS index_granularity = 8192
        """,
        "dm_special_equipment_catalog_quality_daily": """
            CREATE TABLE IF NOT EXISTS dm_special_equipment_catalog_quality_daily (
                date                         Date,
                primary_category_id          Nullable(UUID),
                manufacturer_id              UUID,
                published_products           UInt64,
                complete_products            UInt64,
                products_without_price       UInt64,
                products_without_image       UInt64,
                products_without_description UInt64,
                products_missing_attributes  UInt64,
                min_price                    Nullable(Decimal(15,2)),
                median_price                 Nullable(Decimal(15,2)),
                max_price                    Nullable(Decimal(15,2)),
                newly_published              UInt64,
                rebuilt_at                   DateTime64(3, 'UTC')
            ) ENGINE = MergeTree()
            PARTITION BY date
            ORDER BY (date, primary_category_id, manufacturer_id)
            SETTINGS allow_nullable_key = 1, index_granularity = 8192
        """,
    }
)

_RETIRED_DATA_MARTS: frozenset[str] = frozenset(
    {
        "dm_special_equipment_daily_funnel",
        "dm_special_equipment_product_daily",
        "dm_special_equipment_filter_daily",
        "dm_special_equipment_search_daily",
        "dm_special_equipment_catalog_quality_daily",
    }
)
_RETIRED_TABLES: frozenset[str] = _RETIRED_DWH_TABLES | _RETIRED_DATA_MARTS

_DATA_MART_ALTERS: list[str] = [
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS dealer_id Nullable(UUID) AFTER distributor_id",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS vehicle_mark_id Nullable(String) AFTER vehicle_id",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS vehicle_model_id Nullable(String) AFTER vehicle_mark_id",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS submitted_at Nullable(DateTime64(3)) AFTER created_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS under_review_at Nullable(DateTime64(3)) AFTER submitted_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS prescoring_at Nullable(DateTime64(3)) AFTER under_review_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS approved_at Nullable(DateTime64(3)) AFTER prescoring_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS rejected_at Nullable(DateTime64(3)) AFTER approved_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS issued_at Nullable(DateTime64(3)) AFTER rejected_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS closed_at Nullable(DateTime64(3)) AFTER issued_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS review_notes Nullable(String) AFTER closed_at",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS decision_comment Nullable(String) AFTER review_notes",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS profit_tax_savings Nullable(Decimal(18,2)) AFTER vat_refund",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS total_savings Nullable(Decimal(18,2)) AFTER profit_tax_savings",
    "ALTER TABLE dm_lk_application_funnel "
    "ADD COLUMN IF NOT EXISTS status_count UInt32 DEFAULT 1 AFTER questionnaire_completed",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS application_id UUID AFTER lca_id",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS leasing_company_id UUID AFTER application_id",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS distributor_id Nullable(UUID) AFTER leasing_company_id",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS dealer_id Nullable(UUID) AFTER distributor_id",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS decision_speed_hours Nullable(Float32) AFTER client_decision_at",
    "ALTER TABLE dm_lk_proposals "
    "ADD COLUMN IF NOT EXISTS proposal_created_at DateTime64(3) AFTER decision_speed_hours",
    "ALTER TABLE dm_lk_financial_pipeline "
    "ADD COLUMN IF NOT EXISTS distributor_id Nullable(UUID) AFTER leasing_company_id",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS client_company_id Nullable(UUID) AFTER dealer_company_id",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS leasing_company_name Nullable(String) AFTER dealer_city",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS total_amount Nullable(Decimal(15,2)) AFTER lca_status",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS down_payment Nullable(Decimal(15,2)) AFTER total_amount",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS down_payment_percent Nullable(Decimal(5,2)) AFTER down_payment",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS lease_term_months Nullable(Int32) AFTER down_payment_percent",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS monthly_payment Nullable(Decimal(12,2)) AFTER lease_term_months",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS total_cost Nullable(Decimal(15,2)) AFTER monthly_payment",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS markup Nullable(Decimal(15,2)) AFTER total_cost",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS rate Nullable(Decimal(5,2)) AFTER markup",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS total_interest Nullable(Decimal(15,2)) AFTER rate",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS buyout_amount Nullable(Decimal(15,2)) AFTER total_interest",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS vat_refund Nullable(Decimal(15,2)) AFTER buyout_amount",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS profit_tax_savings Nullable(Decimal(15,2)) AFTER vat_refund",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS total_savings Nullable(Decimal(15,2)) AFTER profit_tax_savings",
    "ALTER TABLE dm_distributor_applications "
    "ADD COLUMN IF NOT EXISTS vehicle_price Nullable(Decimal(15,2)) AFTER total_savings",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS requested_dealer_id Nullable(UUID) AFTER vehicle_id",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS requested_dealer_name Nullable(String) AFTER requested_dealer_id",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS requested_dealer_city Nullable(String) AFTER requested_dealer_name",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS mark Nullable(String) AFTER requested_dealer_city",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS model Nullable(String) AFTER mark",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS file_url Nullable(String) AFTER discount_value",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS file_name Nullable(String) AFTER file_url",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS batch_number Nullable(Int32) AFTER accepted_bid_id",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS batch_index Nullable(Int32) AFTER batch_number",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS bids_count UInt64 DEFAULT 0 AFTER batch_index",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS accepted_bids UInt64 DEFAULT 0 AFTER bids_count",
    "ALTER TABLE dm_distributor_exchange "
    "ADD COLUMN IF NOT EXISTS average_price Nullable(Decimal(15,2)) AFTER accepted_bids",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS lca_id UUID AFTER application_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS leasing_company_id Nullable(UUID) AFTER application_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS client_company_id Nullable(UUID) AFTER dealer_company_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS vehicle_id Nullable(UUID) AFTER client_company_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS vehicle_price Nullable(Decimal(15,2)) AFTER vehicle_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS mark_name Nullable(String) AFTER leasing_company_name",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS model_name Nullable(String) AFTER mark_name",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS vehicle_mark_id Nullable(String) AFTER model_name",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS vehicle_model_id Nullable(String) AFTER vehicle_mark_id",
    "ALTER TABLE dm_distributor_sales_dc "
    "ADD COLUMN IF NOT EXISTS lca_status Nullable(String) AFTER status",
    "ALTER TABLE dm_distributor_sales_dc_regions "
    "ADD COLUMN IF NOT EXISTS leasing_company_id Nullable(UUID) AFTER vehicle_id",
    "ALTER TABLE dm_distributor_sales_dc_regions "
    "ADD COLUMN IF NOT EXISTS lca_status Nullable(String) AFTER application_status",
]

_LC_DATA_MARTS_WITH_REMOVED_TTL: tuple[str, ...] = (
    "dm_lk_daily_metrics",
    "dm_lk_application_funnel",
    "dm_lk_proposals",
    "dm_lk_financial_pipeline",
)


def _remove_table_ttl_if_present(client: Any, table_name: str) -> None:
    result = client.query(f"SHOW CREATE TABLE {table_name}")
    rows = getattr(result, "result_rows", [])
    create_sql = str(rows[0][0]) if rows else ""
    if " TTL " in create_sql:
        client.query(f"ALTER TABLE {table_name} REMOVE TTL")


def ensure_dwh_tables(client: Any) -> None:
    """Create all DWH source tables, data marts, and materialized views if they do not exist."""
    for table_name, ddl in _DWH_TABLES.items():
        if table_name in _RETIRED_DWH_TABLES:
            continue
        client.query(ddl)

    # Idempotent column additions for tables that already exist (CREATE ... IF
    # NOT EXISTS does not add new columns to an existing table).
    for alter in _DWH_ALTERS:
        client.query(alter)

    for table_name, ddl in _DATA_MARTS.items():
        if table_name in _RETIRED_DATA_MARTS:
            continue
        client.query(ddl)

    for alter in _DATA_MART_ALTERS:
        client.query(alter)

    for table_name in _LC_DATA_MARTS_WITH_REMOVED_TTL:
        _remove_table_ttl_if_present(client, table_name)

    # Materialized views for data mart population
    from infrastructure.clickhouse.materialized_views import ALL_MV_STATEMENTS
    for mv_ddl in ALL_MV_STATEMENTS:
        client.query(mv_ddl)
