"""LC-side leasing-applications commands (Phase 5 E3).

These are the LC cabinet's *create-side* operations — distinct from Phase 4
D3's review-side (``approve`` / ``reject`` / ``request-documents``). The
three endpoints owned here are:

- ``POST /api/v1/leasing-applications/`` — LC creates a preliminary
  application on behalf of a client.
- ``PUT /api/v1/leasing-applications/{id}`` — partial update (draft only).
- ``POST /api/v1/leasing-applications/{id}/submit`` — move ``draft`` →
  ``pending_distribution`` via the Phase 3 aggregate root.

All three delegate into Phase 3 machinery so the status-machine lives in
exactly one place (``LeasingApplication`` aggregate).
"""
from application.commands.leasing_applications_lc.change_status import (
    ChangeLeasingAppStatusCommand,
    handle_change_leasing_app_status,
)
from application.commands.leasing_applications_lc.create_lc_application import (
    CreateLcApplicationCommand,
    handle_create_lc_application,
)
from application.commands.leasing_applications_lc.submit_lc_application import (
    SubmitLcApplicationCommand,
    handle_submit_lc_application,
)
from application.commands.leasing_applications_lc.update_lc_application import (
    UpdateLcApplicationCommand,
    handle_update_lc_application,
)
from application.commands.leasing_applications_lc.upsert_questionnaire import (
    UpsertQuestionnaireCommand,
    handle_upsert_questionnaire,
)

__all__ = [
    "ChangeLeasingAppStatusCommand",
    "CreateLcApplicationCommand",
    "SubmitLcApplicationCommand",
    "UpdateLcApplicationCommand",
    "UpsertQuestionnaireCommand",
    "handle_change_leasing_app_status",
    "handle_create_lc_application",
    "handle_submit_lc_application",
    "handle_update_lc_application",
    "handle_upsert_questionnaire",
]
