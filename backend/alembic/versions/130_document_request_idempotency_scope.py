"""Scope typed document request idempotency to a request.

Revision ID: 130
Revises: 129
"""
from __future__ import annotations

from alembic import op

revision = "130"
down_revision = "129"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The key is stored on a single request row. A global unique constraint
    # rejects unrelated client responses that happen to reuse a UUID, while
    # providing no extra safety for an already locked request row.
    op.drop_constraint(
        "uq_document_request_idempotency_key",
        "application_document_requests",
        type_="unique",
    )


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_document_request_idempotency_key",
        "application_document_requests",
        ["idempotency_key"],
    )
