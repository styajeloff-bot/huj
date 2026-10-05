"""Prometheus metrics registry for custom application metrics.

Metrics defined here are scraped automatically by the FastAPI ``/metrics``
endpoint (API process), the event-worker HTTP server, or the Taskiq container
entrypoint's multiprocess HTTP exporter (worker counters and histograms).
"""

from prometheus_client import Counter, Gauge, Histogram

NOTIFICATION_EVENTS = Counter(
    "notification_events_total", "Notification transport attempts", ["stage"]
)
NOTIFICATION_RECIPIENTS = Counter(
    "notification_recipients_total", "Notification recipient outcomes", ["outcome"]
)
NOTIFICATION_DELIVERIES = Counter(
    "notification_email_outcomes_total", "SMTP attempt or skip outcomes", ["state"]
)
NOTIFICATION_SMTP_SECONDS = Histogram(
    "notification_smtp_duration_seconds", "SMTP operation duration without a DB session"
)
NOTIFICATION_OUTBOX_BACKLOG = Gauge(
    "notification_outbox_backlog", "Events awaiting broker acknowledgement"
)
NOTIFICATION_OUTBOX_AGE = Gauge(
    "notification_outbox_oldest_age_seconds", "Age of oldest pending event"
)
NOTIFICATION_EMAIL_BACKLOG = Gauge(
    "notification_email_backlog", "Pending email delivery intents"
)
NOTIFICATION_EMAIL_AGE = Gauge(
    "notification_email_oldest_age_seconds", "Age of oldest pending delivery"
)

# ---------------------------------------------------------------------------
# DWH Producer (FastAPI process)
# ---------------------------------------------------------------------------

DWH_MESSAGES_PUBLISHED = Counter(
    "dwh_messages_published_total",
    "Total DWH snapshot / changed messages published to Kafka",
    ["topic"],
)

DWH_PUBLISH_FAILURES = Counter(
    "dwh_publish_failures_total",
    "Total DWH messages that failed to publish to Kafka",
    ["topic"],
)

DWH_DURABLE_BATCHES = Counter(
    "dwh_durable_batches_total",
    "Total durable import DWH batch transitions",
    ["result"],
)

LCA_HISTORY_OUTBOX_BACKLOG = Gauge(
    "lca_history_outbox_backlog",
    "Number of committed LCA status events awaiting Kafka delivery",
)

LCA_HISTORY_OUTBOX_OLDEST_AGE_SECONDS = Gauge(
    "lca_history_outbox_oldest_age_seconds",
    "Age in seconds of the oldest unpublished LCA status event",
)

LCA_HISTORY_PUBLISH_FAILURES = Counter(
    "lca_history_publish_failures_total",
    "Total failed LCA status history Kafka publish attempts",
)

LCA_HISTORY_MESSAGES_PUBLISHED = Counter(
    "lca_history_messages_published_total",
    "Total LCA status history events acknowledged by Kafka",
)

APPLICATION_FUNNEL_INVARIANT_FAILURES = Counter(
    "application_funnel_invariant_failures_total",
    "Total application status funnel end-state invariant failures",
)

APPLICATION_FUNNEL_QUERY_DURATION_SECONDS = Histogram(
    "application_funnel_query_duration_seconds",
    "End-to-end duration of application status funnel requests",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

APPLICATION_FUNNEL_CACHE_HITS = Counter(
    "application_funnel_cache_hits_total",
    "Total application status funnel responses served from Redis cache",
)

APPLICATION_FUNNEL_CACHE_ERRORS = Counter(
    "application_funnel_cache_errors_total",
    "Total application status funnel Redis cache errors",
    ["operation"],
)

APPLICATION_FUNNEL_ERRORS = Counter(
    "application_funnel_errors_total",
    "Total application status funnel request errors",
    ["error_code"],
)

REPOSITORY_QUERY_DURATION_SECONDS = Histogram(
    "repository_query_duration_seconds",
    "Aggregate duration of repository operations without entity identifiers",
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2.5, 5],
)

# ---------------------------------------------------------------------------
# DWH Consumer (event-worker process)
# ---------------------------------------------------------------------------

DWH_MESSAGES_CONSUMED = Counter(
    "dwh_messages_consumed_total",
    "Total DWH messages consumed from Kafka",
    ["table"],
)

DWH_BATCH_SIZE = Histogram(
    "dwh_batch_size",
    "Number of messages in a consumed batch",
    ["table"],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500],
)

DWH_INSERT_DURATION = Histogram(
    "dwh_batch_insert_duration_seconds",
    "Time spent inserting a batch into ClickHouse",
    ["table"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

DWH_INSERT_ERRORS = Counter(
    "dwh_insert_errors_total",
    "Total ClickHouse batch insert errors",
    ["table"],
)

LCA_HISTORY_MESSAGES_CONSUMED = Counter(
    "lca_history_messages_consumed_total",
    "Total LCA status history Kafka messages consumed",
)

LCA_HISTORY_ROWS_INSERTED = Counter(
    "lca_history_rows_inserted_total",
    "Total LCA status history rows inserted into ClickHouse",
)

LCA_HISTORY_CONSUMER_ERRORS = Counter(
    "lca_history_consumer_errors_total",
    "Total LCA status history validation or ClickHouse insert errors",
)

LCA_HISTORY_INGEST_LAG_SECONDS = Histogram(
    "lca_history_ingest_lag_seconds",
    "Elapsed seconds between an LCA transition and ClickHouse ingestion",
    buckets=[0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900, 3600, 21600],
)

# ---------------------------------------------------------------------------
# Kafka Consumer Lag (event-worker process)
# ---------------------------------------------------------------------------

KAFKA_CONSUMER_LAG = Gauge(
    "kafka_consumer_lag",
    "Consumer lag per topic / partition / group",
    ["topic", "partition", "group"],
)

KAFKA_CONSUMER_LAG_TOTAL = Gauge(
    "kafka_consumer_lag_total",
    "Total consumer lag across all partitions for a group",
    ["group"],
)
