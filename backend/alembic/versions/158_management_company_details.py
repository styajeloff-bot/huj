"""Preserve management-company requisites alongside document-request evidence.

Revision ID: 158
Revises: 157
"""
from alembic import op
import sqlalchemy as sa

revision = "158"
down_revision = "157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE application_questionnaires q
        SET management_company_details = jsonb_build_object(
                'requisites', COALESCE(q.management_company_details, 'null'::jsonb),
                'status', 'not_provided', 'file_name', NULL, 'documents', '[]'::jsonb
            ),
            field_sources = COALESCE((
                SELECT jsonb_object_agg(
                    CASE WHEN key = 'management_company_details'
                        THEN 'management_company_details.requisites'
                        WHEN key LIKE 'management_company_details.%'
                        THEN 'management_company_details.requisites' || substr(key, 27)
                        ELSE key END, value
                ) FROM jsonb_each(COALESCE(q.field_sources, '{}'::jsonb))
            ), '{}'::jsonb)
        WHERE q.management_company_details IS NULL
           OR jsonb_typeof(q.management_company_details) <> 'object'
           OR NOT (q.management_company_details ? 'requisites'
               AND q.management_company_details ? 'status')
    """))


def downgrade() -> None:
    connection = op.get_bind()
    has_documents = connection.scalar(sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM application_questionnaires
            WHERE management_company_details ? 'requisites'
              AND (management_company_details->>'status' IS DISTINCT FROM 'not_provided'
                   OR management_company_details->'documents' IS DISTINCT FROM '[]'::jsonb
                   OR management_company_details->>'file_name' IS NOT NULL)
        )
    """))
    if has_documents:
        raise RuntimeError("Cannot downgrade 158 without discarding management-company document evidence")
    op.execute(sa.text("""
        UPDATE application_questionnaires q
        SET management_company_details = NULLIF(q.management_company_details->'requisites', 'null'::jsonb),
            field_sources = COALESCE((
                SELECT jsonb_object_agg(
                    CASE WHEN key = 'management_company_details.requisites'
                        THEN 'management_company_details'
                        WHEN key LIKE 'management_company_details.requisites.%'
                        THEN 'management_company_details' || substr(key, 38)
                        ELSE key END, value
                ) FROM jsonb_each(COALESCE(q.field_sources, '{}'::jsonb))
                WHERE key NOT IN ('management_company_details.status',
                    'management_company_details.file_name', 'management_company_details.documents')
            ), '{}'::jsonb)
        WHERE q.management_company_details ? 'requisites'
    """))
