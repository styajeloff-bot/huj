"""Expanded per-application questionnaire and beneficiary dictionaries.
Revision ID: 147
Revises: 146
"""

import uuid
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "147"
down_revision = "146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "application_questionnaires",
        "director_passport_series",
        existing_type=sa.String(10),
        type_=sa.String(30),
        existing_nullable=True,
    )
    op.alter_column(
        "application_questionnaires",
        "director_passport_number",
        existing_type=sa.String(20),
        type_=sa.String(30),
        existing_nullable=True,
    )
    op.alter_column(
        "application_questionnaires",
        "director_passport_department_code",
        existing_type=sa.String(10),
        type_=sa.String(30),
        existing_nullable=True,
    )
    op.create_table(
        "beneficial_owner_absence_reasons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    table = sa.table(
        "beneficial_owner_absence_reasons",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.Text),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.UUID("a3dfb9ff-b30e-5ace-ab03-90fff29ee9d2"),
                "code": "no_person_over_25_percent",
                "name": "Не выявлено физическое лицо, владеющее прямо или косвенно более 25% компании",
            },
            {
                "id": uuid.UUID("b838aab1-b929-5973-b5b4-0eb5e1e52110"),
                "code": "no_person_controls_company",
                "name": "Не выявлено физическое лицо, осуществляющее фактический контроль над компанией",
            },
            {
                "id": uuid.UUID("989a7de2-2d8f-5d96-a5c6-5d8adea3d234"),
                "code": "dispersed_ownership",
                "name": "Доли участия распределены между несколькими участниками",
            },
            {
                "id": uuid.UUID("baac87f5-c452-596e-9be1-9ef43ad276b7"),
                "code": "state_or_municipal_ownership",
                "name": "Государственное или муниципальное участие",
            },
            {
                "id": uuid.UUID("c15f673e-1394-5e16-a407-69008d267764"),
                "code": "public_company",
                "name": "Публичная компания с распределённым владением акциями",
            },
            {
                "id": uuid.UUID("ac3dcff8-fe81-53fe-87e6-a1ebd25bfb67"),
                "code": "nonprofit_organization",
                "name": "Организационно-правовая форма не предполагает наличие бенефициарного владельца",
            },
            {
                "id": uuid.UUID("f509a744-ea5f-53d9-82d5-603d76566c8c"),
                "code": "other",
                "name": "Иная причина",
            },
        ],
    )
    op.create_table(
        "beneficial_owner_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    table = sa.table(
        "beneficial_owner_bases",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.Text),
    )
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.UUID("c93db83a-137a-5955-a504-7c9ed2edcf40"),
                "code": "direct_ownership_over_25",
                "name": "Прямое владение более 25% долей в уставном капитале или голосующих акций",
            },
            {
                "id": uuid.UUID("0c785e56-8359-5c4d-9a8c-ec761e07563f"),
                "code": "indirect_ownership_over_25",
                "name": "Косвенное владение более 25% долей в уставном капитале или голосующих акций",
            },
            {
                "id": uuid.UUID("fb854860-d06d-59e6-a6df-4128bdeced3e"),
                "code": "control_by_agreement",
                "name": "Контроль над юридическим лицом на основании договора или иного соглашения",
            },
            {
                "id": uuid.UUID("ea3fb94e-dda5-5c3a-9e19-7babee9ec813"),
                "code": "control_through_management",
                "name": "Возможность определяющим образом влиять на решения и деятельность юридического лица",
            },
            {
                "id": uuid.UUID("2bc76bdb-93fb-58be-82ba-43cc5950c70c"),
                "code": "right_to_appoint_management",
                "name": "Право назначать или прекращать полномочия руководителя либо органов управления",
            },
            {
                "id": uuid.UUID("dfba0d7d-2ee9-51f6-8cb6-ada2fbbf4aaf"),
                "code": "combined_ownership_and_control",
                "name": "Одновременное владение долей и осуществление фактического контроля",
            },
            {
                "id": uuid.UUID("47ba480d-13e0-587f-804a-3cbe41e6d598"),
                "code": "executive_body_by_default",
                "name": "Единоличный исполнительный орган, если фактический бенефициар не выявлен",
            },
            {
                "id": uuid.UUID("4dd61067-3297-55b4-8c6f-bc7f7b9cbb59"),
                "code": "other_control_basis",
                "name": "Иное основание фактического контроля",
            },
        ],
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("registration_date", sa.Date, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("registration_authority_name", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("postal_address_matches_legal", sa.Boolean, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("company_phone", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("company_email", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("company_website", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires", sa.Column("contact_person", JSONB, nullable=True)
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("correspondent_account", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_inn", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_snils", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_appointment_document", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_is_pdl", sa.Boolean, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_pdl_related_person", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("director_name_changed", sa.Boolean, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("employee_count", sa.Integer, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("licenses_or_sro_membership", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("main_counterparties", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("open_bank_accounts", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("loans_credits_leasing", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("third_party_guarantees", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("additional_collateral_available", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("vehicle_purchase_purpose", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("management_company_details", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("transaction_beneficiary", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("electronic_document_management_systems", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("website_in_blocked_domains_registry", sa.Boolean, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("state_defense_order", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("personal_data_processing_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("legal_entity_credit_report_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("individual_credit_report_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("credit_bureau_data_transfer_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("marketing_communications_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("information_accuracy_declaration", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("information_verification_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("permitted_data_recipients", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("telecom_data_transfer_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("federal_register_inclusion_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("affiliates_data_transfer_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("electronic_documents_equivalence_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("automated_marketing_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("biometric_data_processing_consent", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("consent_validity_period", sa.Text, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("consent_revocation_procedure", sa.Text, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column(
            "questionnaire_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("authorized_person_signature", JSONB, nullable=True),
    )
    op.add_column(
        "application_questionnaires", sa.Column("company_seal", JSONB, nullable=True)
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("foreign_company_name", sa.String(), nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column(
            "no_beneficial_owner_reason",
            UUID(as_uuid=True),
            sa.ForeignKey("beneficial_owner_absence_reasons.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column("no_beneficial_owner_reason_details", sa.Text, nullable=True),
    )
    op.add_column(
        "application_questionnaires",
        sa.Column(
            "field_sources",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute("""UPDATE application_questionnaires q SET field_sources = COALESCE(
      (SELECT jsonb_object_agg(key, 'manual') FROM jsonb_each(to_jsonb(q))
       WHERE key NOT IN ('id','application_id','created_at','updated_at','field_sources')
         AND value <> 'null'::jsonb), '{}'::jsonb)""")
    op.execute("""INSERT INTO application_questionnaires (id, application_id)
      SELECT gen_random_uuid(), a.id FROM leasing_applications a
      WHERE NOT EXISTS (SELECT 1 FROM application_questionnaires q WHERE q.application_id=a.id)""")


def downgrade() -> None:
    op.alter_column(
        "application_questionnaires",
        "director_passport_series",
        existing_type=sa.String(30),
        type_=sa.String(10),
        existing_nullable=True,
    )
    op.alter_column(
        "application_questionnaires",
        "director_passport_number",
        existing_type=sa.String(30),
        type_=sa.String(20),
        existing_nullable=True,
    )
    op.alter_column(
        "application_questionnaires",
        "director_passport_department_code",
        existing_type=sa.String(30),
        type_=sa.String(10),
        existing_nullable=True,
    )
    op.drop_column("application_questionnaires", "field_sources")
    op.drop_column("application_questionnaires", "no_beneficial_owner_reason_details")
    op.drop_column("application_questionnaires", "no_beneficial_owner_reason")
    op.drop_column("application_questionnaires", "foreign_company_name")
    op.drop_column("application_questionnaires", "company_seal")
    op.drop_column("application_questionnaires", "authorized_person_signature")
    op.drop_column("application_questionnaires", "questionnaire_completed_at")
    op.drop_column("application_questionnaires", "consent_revocation_procedure")
    op.drop_column("application_questionnaires", "consent_validity_period")
    op.drop_column("application_questionnaires", "biometric_data_processing_consent")
    op.drop_column("application_questionnaires", "automated_marketing_consent")
    op.drop_column(
        "application_questionnaires", "electronic_documents_equivalence_consent"
    )
    op.drop_column("application_questionnaires", "affiliates_data_transfer_consent")
    op.drop_column("application_questionnaires", "federal_register_inclusion_consent")
    op.drop_column("application_questionnaires", "telecom_data_transfer_consent")
    op.drop_column("application_questionnaires", "permitted_data_recipients")
    op.drop_column("application_questionnaires", "information_verification_consent")
    op.drop_column("application_questionnaires", "information_accuracy_declaration")
    op.drop_column("application_questionnaires", "marketing_communications_consent")
    op.drop_column("application_questionnaires", "credit_bureau_data_transfer_consent")
    op.drop_column("application_questionnaires", "individual_credit_report_consent")
    op.drop_column("application_questionnaires", "legal_entity_credit_report_consent")
    op.drop_column("application_questionnaires", "personal_data_processing_consent")
    op.drop_column("application_questionnaires", "state_defense_order")
    op.drop_column("application_questionnaires", "website_in_blocked_domains_registry")
    op.drop_column(
        "application_questionnaires", "electronic_document_management_systems"
    )
    op.drop_column("application_questionnaires", "transaction_beneficiary")
    op.drop_column("application_questionnaires", "management_company_details")
    op.drop_column("application_questionnaires", "vehicle_purchase_purpose")
    op.drop_column("application_questionnaires", "additional_collateral_available")
    op.drop_column("application_questionnaires", "third_party_guarantees")
    op.drop_column("application_questionnaires", "loans_credits_leasing")
    op.drop_column("application_questionnaires", "open_bank_accounts")
    op.drop_column("application_questionnaires", "main_counterparties")
    op.drop_column("application_questionnaires", "licenses_or_sro_membership")
    op.drop_column("application_questionnaires", "employee_count")
    op.drop_column("application_questionnaires", "director_name_changed")
    op.drop_column("application_questionnaires", "director_pdl_related_person")
    op.drop_column("application_questionnaires", "director_is_pdl")
    op.drop_column("application_questionnaires", "director_appointment_document")
    op.drop_column("application_questionnaires", "director_snils")
    op.drop_column("application_questionnaires", "director_inn")
    op.drop_column("application_questionnaires", "correspondent_account")
    op.drop_column("application_questionnaires", "contact_person")
    op.drop_column("application_questionnaires", "company_website")
    op.drop_column("application_questionnaires", "company_email")
    op.drop_column("application_questionnaires", "company_phone")
    op.drop_column("application_questionnaires", "postal_address_matches_legal")
    op.drop_column("application_questionnaires", "registration_authority_name")
    op.drop_column("application_questionnaires", "registration_date")
    op.drop_table("beneficial_owner_bases")
    op.drop_table("beneficial_owner_absence_reasons")
