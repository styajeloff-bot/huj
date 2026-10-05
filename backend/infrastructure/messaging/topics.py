"""Kafka topic constants and partition layout."""

CATALOG_UPLOAD_REQUESTED = "catalog.upload.requested.v1"
CATALOG_IMPORT_ROW = "catalog.import.row.v1"
CATALOG_IMAGE_FETCH = "catalog.image.fetch.v1"

# Authentication / authorization audit trail. 2 partitions to support
# 2 event-worker replicas (Kafka constraint: consumers per group ≤ partitions).
AUTH_EVENTS = "auth.events.v1"
NOTIFICATION_EVENTS = "notification.events.v1"
NOTIFICATION_EVENTS_DLQ = "notification.events.dlq.v1"

# Status-change events for documents and leasing applications.
# FastAPI publishes these; event-worker persists them to ClickHouse.
DOCUMENT_STATUS_CHANGED = "document.status_changed.v1"
LEASING_APP_STATUS_CHANGED = "leasing_app.status_changed.v1"

# DWH status-change topics for additional entities.
LCA_STATUS_CHANGED = "lca.status_changed.v1"
LCA_STATUS_CHANGED_V2 = "lca.status_changed.v2"
CLIENT_STATUS_CHANGED = "client.status_changed.v1"
COMPANY_STATUS_CHANGED = "company.status_changed.v1"
WAREHOUSE_STATUS_CHANGED = "warehouse.status_changed.v1"
EXCHANGE_REQUEST_STATUS_CHANGED = "exchange_request.status_changed.v1"
EXCHANGE_BID_STATUS_CHANGED = "exchange_bid.status_changed.v1"
VEHICLE_STATUS_CHANGED = "vehicle.status_changed.v1"

# ---------------------------------------------------------------------------
# DWH snapshot / changed topics (ТЗ ClickHouse DWH Аналитика ЛК)
# ---------------------------------------------------------------------------

# Snapshot topics — full row dumps (batch, e.g. nightly)
LEASING_APPLICATION_SNAPSHOT = "leasing_application.snapshot.v1"
LCA_SNAPSHOT = "lca.snapshot.v1"
PROPOSAL_SNAPSHOT = "proposal.snapshot.v1"
DOCUMENT_SNAPSHOT = "document.snapshot.v1"
VEHICLE_SNAPSHOT = "vehicle.snapshot.v1"
APP_VEHICLE_SNAPSHOT = "app_vehicle.snapshot.v1"
COMPANY_SNAPSHOT = "company.snapshot.v1"
USER_SNAPSHOT = "user.snapshot.v1"
PURCHASE_ORDER_SNAPSHOT = "purchase_order.snapshot.v1"
CALCULATION_SNAPSHOT = "calculation.snapshot.v1"
QUESTIONNAIRE_SNAPSHOT = "questionnaire.snapshot.v1"
EXCHANGE_REQUEST_SNAPSHOT = "exchange_request.snapshot.v1"
EXCHANGE_BID_SNAPSHOT = "exchange_bid.snapshot.v1"
SUPPORT_PROGRAM_SNAPSHOT = "support_program.snapshot.v1"
COMPENSATION_SNAPSHOT = "compensation.snapshot.v1"

# Changed topics — CDC events (real-time, ReplacingMergeTree upserts)
LEASING_APPLICATION_CHANGED = "leasing_application.changed.v1"
LCA_CHANGED = "lca.changed.v1"
PROPOSAL_CHANGED = "proposal.changed.v1"
DOCUMENT_CHANGED = "document.changed.v1"
VEHICLE_CHANGED = "vehicle.changed.v1"
APP_VEHICLE_CHANGED = "app_vehicle.changed.v1"
COMPANY_CHANGED = "company.changed.v1"
USER_CHANGED = "user.changed.v1"
PURCHASE_ORDER_CHANGED = "purchase_order.changed.v1"
CALCULATION_CREATED = "calculation.created.v1"        # append-only
QUESTIONNAIRE_CHANGED = "questionnaire.changed.v1"
EXCHANGE_REQUEST_CHANGED = "exchange_request.changed.v1"
EXCHANGE_BID_CHANGED = "exchange_bid.changed.v1"
SUPPORT_PROGRAM_CHANGED = "support_program.changed.v1"
COMPENSATION_CHANGED = "compensation.changed.v1"

# Partition counts — chosen so that horizontal scaling of event-worker
# replicas can actually parallelise. The image topic gets the most because
# image fetch is the dominant bottleneck (~1.5s/image, network-bound).
TOPIC_PARTITIONS: dict[str, int] = {
    CATALOG_UPLOAD_REQUESTED: 3,
    CATALOG_IMPORT_ROW: 12,
    CATALOG_IMAGE_FETCH: 24,
    AUTH_EVENTS: 2,
    NOTIFICATION_EVENTS: 3,
    NOTIFICATION_EVENTS_DLQ: 3,
    DOCUMENT_STATUS_CHANGED: 3,
    LEASING_APP_STATUS_CHANGED: 3,
    LCA_STATUS_CHANGED: 3,
    LCA_STATUS_CHANGED_V2: 3,
    CLIENT_STATUS_CHANGED: 3,
    COMPANY_STATUS_CHANGED: 3,
    WAREHOUSE_STATUS_CHANGED: 3,
    EXCHANGE_REQUEST_STATUS_CHANGED: 3,
    EXCHANGE_BID_STATUS_CHANGED: 3,
    VEHICLE_STATUS_CHANGED: 3,
    # DWH snapshot / changed topics
    LEASING_APPLICATION_SNAPSHOT: 3,
    LEASING_APPLICATION_CHANGED: 3,
    LCA_SNAPSHOT: 3,
    LCA_CHANGED: 3,
    PROPOSAL_SNAPSHOT: 3,
    PROPOSAL_CHANGED: 3,
    DOCUMENT_SNAPSHOT: 3,
    DOCUMENT_CHANGED: 3,
    VEHICLE_SNAPSHOT: 3,
    VEHICLE_CHANGED: 3,
    APP_VEHICLE_SNAPSHOT: 3,
    APP_VEHICLE_CHANGED: 3,
    COMPANY_SNAPSHOT: 3,
    COMPANY_CHANGED: 3,
    USER_SNAPSHOT: 3,
    USER_CHANGED: 3,
    PURCHASE_ORDER_SNAPSHOT: 3,
    PURCHASE_ORDER_CHANGED: 3,
    CALCULATION_SNAPSHOT: 3,
    CALCULATION_CREATED: 3,
    QUESTIONNAIRE_SNAPSHOT: 3,
    QUESTIONNAIRE_CHANGED: 3,
    EXCHANGE_REQUEST_SNAPSHOT: 3,
    EXCHANGE_REQUEST_CHANGED: 3,
    EXCHANGE_BID_SNAPSHOT: 3,
    EXCHANGE_BID_CHANGED: 3,
    SUPPORT_PROGRAM_SNAPSHOT: 3,
    SUPPORT_PROGRAM_CHANGED: 3,
    COMPENSATION_SNAPSHOT: 3,
    COMPENSATION_CHANGED: 3,
}
