#!/bin/sh
set -eu

marker="${SMOKE_MARKER:-local_observability_smoke}"

case "$marker" in
  *[!A-Za-z0-9_.:-]*)
    echo "SMOKE_MARKER may contain only ASCII letters, numbers, dot, colon, underscore, and dash" >&2
    exit 2
    ;;
esac

# Give Alloy discovery time to attach before the short-lived fixture writes.
sleep 3

for level in debug info warning error critical; do
  timestamp="$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"
  printf '%s\n' "{\"timestamp\":\"${timestamp}\",\"schema_version\":1,\"level\":\"${level}\",\"service_name\":\"carcraft-api\",\"component\":\"observability\",\"event\":\"local.observability.smoke\",\"message\":\"Structured logging smoke event (${level})\",\"environment\":\"local\",\"service_version\":\"smoke\",\"correlation_id\":\"${marker}\",\"result\":\"${level}\"}"
  sleep 1
done

# Keep the container discoverable long enough for its final line to be tailed.
sleep 5
