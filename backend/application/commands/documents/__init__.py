"""Document command handlers (Phase 4 D1 + Phase 10 R4 unify)."""
from application.commands.documents.change_document_status import (
    ChangeDocumentStatusCommand,
    handle_change_document_status,
)
from application.commands.documents.restore_document import (
    RestoreDocumentCommand,
    handle_restore_document,
)
from application.commands.documents.soft_delete_document import (
    SoftDeleteDocumentCommand,
    handle_soft_delete_document,
)
from application.commands.documents.upload_document import (
    UploadDocumentCommand,
    UploadedDocumentFile,
    handle_upload_document,
)
from application.commands.documents.upload_document_version import (
    UploadDocumentVersionCommand,
    handle_upload_document_version,
)
from application.commands.documents.upload_for_application import (
    UploadDocumentForApplicationCommand,
    handle_upload_document_for_application,
)

__all__ = [
    "ChangeDocumentStatusCommand",
    "RestoreDocumentCommand",
    "SoftDeleteDocumentCommand",
    "UploadDocumentCommand",
    "UploadDocumentForApplicationCommand",
    "UploadDocumentVersionCommand",
    "UploadedDocumentFile",
    "handle_change_document_status",
    "handle_restore_document",
    "handle_soft_delete_document",
    "handle_upload_document",
    "handle_upload_document_for_application",
    "handle_upload_document_version",
]
