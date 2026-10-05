"""Backfill management-company evidence from completed historical responses.

Revision ID: 159
Revises: 158
"""
import sqlalchemy as sa
from alembic import op

revision = "159"
down_revision = "158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        WITH response_file_dates AS (
            SELECT link.document_request_id, link.application_id, link.leasing_company_id,
                count(*) AS file_count,
                max(COALESCE(document.uploaded_at, link.submitted_at,
                    document.created_at)) AS uploaded_at
            FROM application_documents link
            JOIN documents document ON document.id = link.document_id
                AND document.document_type = 'management_company'
            GROUP BY link.document_request_id, link.application_id, link.leasing_company_id
        ), answered_requests AS (
            SELECT request.id, request.application_id, request.leasing_company_id,
                request.requested_at,
                -- Historical single-file autoapproval omitted provided_at.
                -- A later review must not reorder older files after a newer answer.
                COALESCE(request.provided_at, files.uploaded_at,
                    request.reviewed_at) AS answered_at
            FROM application_document_requests request
            LEFT JOIN response_file_dates files ON files.document_request_id = request.id
                AND files.application_id = request.application_id
                AND files.leasing_company_id = request.leasing_company_id
            WHERE request.document_type = 'management_company'
              AND request.status IN ('provided', 'approved')
              AND (request.provided_at IS NOT NULL
                   OR (request.status = 'approved' AND files.file_count > 0))
        ), latest_response AS (
            SELECT DISTINCT ON (application_id)
                id, application_id, leasing_company_id
            FROM answered_requests
            ORDER BY application_id, answered_at DESC NULLS LAST,
                requested_at DESC NULLS LAST, id DESC
        ), response_files AS (
            SELECT latest.application_id, document.id AS document_id,
                document.created_at,
                -- Both historical title columns are nullable. Keep the reference
                -- with a safe label rather than exposing null to the LC projection.
                COALESCE(NULLIF(btrim(link.user_title), ''),
                    NULLIF(btrim(document.file_name), ''),
                    'Документ об управляющей компании') AS user_title
            FROM latest_response latest
            LEFT JOIN application_documents link
                ON link.document_request_id = latest.id
               AND link.application_id = latest.application_id
               AND link.leasing_company_id = latest.leasing_company_id
            LEFT JOIN documents document ON document.id = link.document_id
                AND document.document_type = 'management_company'
        ), evidence AS (
            SELECT application_id,
                COALESCE(jsonb_agg(jsonb_build_object(
                    'document_id', document_id::text, 'user_title', user_title
                ) ORDER BY created_at ASC NULLS LAST, document_id)
                    FILTER (WHERE document_id IS NOT NULL), '[]'::jsonb) AS documents,
                string_agg(user_title, '; ' ORDER BY created_at ASC NULLS LAST, document_id)
                    FILTER (WHERE document_id IS NOT NULL) AS file_name
            FROM response_files
            GROUP BY application_id
        )
        UPDATE application_questionnaires questionnaire
        SET management_company_details = questionnaire.management_company_details
                || jsonb_build_object(
                    'status', CASE WHEN jsonb_array_length(evidence.documents) > 0
                        THEN 'file_attached' ELSE 'not_provided' END,
                    'file_name', evidence.file_name, 'documents', evidence.documents
                ),
            field_sources = COALESCE(questionnaire.field_sources, '{}'::jsonb)
                || jsonb_build_object(
                    'management_company_details.status', 'document_request',
                    'management_company_details.file_name', 'document_request',
                    'management_company_details.documents', 'document_request'
                )
        FROM evidence
        WHERE questionnaire.application_id = evidence.application_id
          AND jsonb_typeof(questionnaire.management_company_details) = 'object'
          AND questionnaire.management_company_details ? 'requisites'
    """))


def downgrade() -> None:
    # Data-only repair: reverting it would discard known historical evidence.
    # Revision 158 continues to guard any later downgrade that would lose files.
    pass
