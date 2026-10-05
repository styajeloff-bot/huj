"""Document queries (Phase 4 D1 + Phase 7a G2 backport)."""
from application.queries.documents.download_archive import (
    ApplicationArchive,
    DownloadApplicationArchiveQuery,
    handle_download_application_archive,
)
from application.queries.documents.download_document import (
    DownloadDocumentQuery,
    DownloadedDocument,
    handle_download_document,
)
from application.queries.documents.get_document import (
    GetDocumentQuery,
    handle_get_document,
)
from application.queries.documents.list_document_requests import (
    ListDocumentRequestsQuery,
    handle_list_document_requests,
)
from application.queries.documents.list_document_requirements import (
    ListDocumentRequirementsQuery,
    handle_list_document_requirements,
)
from application.queries.documents.list_document_types import (
    ListDocumentTypesQuery,
    handle_list_document_types,
)
from application.queries.documents.list_document_versions import (
    ListDocumentVersionsQuery,
    handle_list_document_versions,
)
from application.queries.documents.list_documents import (
    ListDocumentsQuery,
    handle_list_documents,
)
from application.queries.documents.list_documents_for_application import (
    ListDocumentsForApplicationQuery,
    handle_list_documents_for_application,
)
from application.queries.documents.list_user_documents_enhanced import (
    ListUserDocumentsEnhancedQuery,
    handle_list_user_documents_enhanced,
)
from application.queries.documents.list_user_requirements import (
    ListUserRequirementsQuery,
    handle_list_user_requirements,
)

__all__ = [
    "ApplicationArchive",
    "DownloadApplicationArchiveQuery",
    "DownloadDocumentQuery",
    "DownloadedDocument",
    "GetDocumentQuery",
    "ListDocumentRequestsQuery",
    "ListDocumentRequirementsQuery",
    "ListDocumentTypesQuery",
    "ListDocumentVersionsQuery",
    "ListDocumentsForApplicationQuery",
    "ListDocumentsQuery",
    "ListUserDocumentsEnhancedQuery",
    "ListUserRequirementsQuery",
    "handle_download_application_archive",
    "handle_download_document",
    "handle_get_document",
    "handle_list_document_requests",
    "handle_list_document_requirements",
    "handle_list_document_types",
    "handle_list_document_versions",
    "handle_list_documents",
    "handle_list_documents_for_application",
    "handle_list_user_documents_enhanced",
    "handle_list_user_requirements",
]
