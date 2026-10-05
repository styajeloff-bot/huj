#!/usr/bin/env python3
"""Bulk import script — uploads the full seed in dependency order, then verifies.

Usage:
    python import_all.py small     # quick test subset
    python import_all.py full      # full dataset, long run

All bulk-import endpoints are ASYNC: they return HTTP 202 ``{"job_id": ...}``.
After uploading we POLL ``GET /api/v1/imports/{job_id}`` until the job reports
``status`` done/failed before moving to the next step.

Import order (dependencies flow downward):
    1. companies                — clients + LCs + dealers + distributors
         a) companies.csv        (POST /companies/import)
         b) companies_dealers.csv (POST /companies/import)
    2. distributor-dealer links — POST /admin/companies/distributor-dealer-links/import
    3. users                    — POST /users/import (optional; skipped if absent)
    4. vehicles master          — POST /vehicles/import
    5. applications (LCA)        — POST /admin/applications/import
    6. exchange requests         — POST /exchange/requests/import
       exchange bids             — POST /exchange/bids/import
    7. verify                   — GET /distributor/analytics/applications
"""

import os
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE = os.environ.get("API_BASE", "http://localhost/api/v1")
PHONE = "+76660000001"
CODE = "0000"
CSV_DIR = Path("~/projects/carcraft-leadgenerator/leasing_export/import").expanduser()

# Upload (connection) timeouts per step (seconds). The async job itself is
# bounded by JOB_POLL_TIMEOUT below, not by these.
TIMEOUT_UPLOAD = 600
TIMEOUT_ANALYTICS = 30

# Async job polling.
JOB_POLL_INTERVAL = 2.0          # seconds between polls
JOB_POLL_TIMEOUT_SMALL = 600     # 10 min
JOB_POLL_TIMEOUT_FULL = 7200     # 120 min


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def login(session: requests.Session) -> bool:
    """Authenticate via OTP. Returns True on success."""
    print("🔐 Logging in...")

    r = session.post(f"{BASE}/auth/login", json={"phone": PHONE}, timeout=10)
    if r.status_code >= 400:
        print(f"   ❌ login failed: {r.status_code} {r.text[:200]}")
        return False

    r = session.post(f"{BASE}/auth/verify-phone", json={"phone": PHONE, "code": CODE}, timeout=10)
    if r.status_code >= 400:
        print(f"   ❌ verify failed: {r.status_code} {r.text[:200]}")
        return False

    data = r.json()
    user = data.get("user", {})
    print(f"   ✅ {user.get('phone')} role={user.get('role')} company_id={user.get('company_id', 'none')}")
    return True


# ---------------------------------------------------------------------------
# Async job polling
# ---------------------------------------------------------------------------

def poll_job(session: requests.Session, job_id: str, label: str, poll_timeout: int) -> bool:
    """Poll GET /imports/{job_id} until status is terminal. Returns True on done."""
    deadline = time.monotonic() + poll_timeout
    last_status = None
    while time.monotonic() < deadline:
        try:
            r = session.get(f"{BASE}/imports/{job_id}", timeout=TIMEOUT_ANALYTICS)
        except requests.exceptions.RequestException as exc:
            print(f"   ⚠️  poll error: {exc}")
            time.sleep(JOB_POLL_INTERVAL)
            continue

        if r.status_code >= 400:
            print(f"   ❌ poll {job_id}: {r.status_code} {r.text[:200]}")
            return False

        data = r.json()
        status = (data.get("status") or "").lower()
        if status != last_status:
            progress = data.get("progress")
            extra = f" progress={progress}" if progress is not None else ""
            print(f"   … {label} job {job_id}: {status}{extra}")
            last_status = status

        if status in ("done", "completed", "success", "succeeded"):
            created = data.get("created", "?")
            updated = data.get("updated", "?")
            errors = data.get("errors", []) or []
            print(f"   ✅ {label}: created={created} updated={updated} errors={len(errors)}")
            for e in errors[:5]:
                print(f"      • {e}")
            return True

        if status in ("failed", "error"):
            print(f"   ❌ {label} job failed: {data.get('error') or data}")
            return False

        time.sleep(JOB_POLL_INTERVAL)

    print(f"   ❌ {label}: poll timeout after {poll_timeout}s")
    return False


def upload_and_wait(
    session: requests.Session,
    endpoint: str,
    csv_path: Path,
    label: str,
    poll_timeout: int,
    *,
    required: bool = True,
) -> bool:
    """POST a CSV to an async import endpoint, then poll the returned job_id.

    ``endpoint`` is the path after BASE (may include query string).
    Returns True on success. If ``required`` is False and the file is missing,
    the step is skipped (returns True).
    """
    print(f"\n📦 {label} ← {csv_path.name}")
    if not csv_path.exists():
        if required:
            print(f"   ❌ File not found: {csv_path}")
            return False
        print(f"   ⏭️  skipped (no {csv_path.name})")
        return True

    with open(csv_path, "rb") as f:
        r = session.post(
            f"{BASE}{endpoint}",
            files={"file": (csv_path.name, f, "text/csv")},
            timeout=TIMEOUT_UPLOAD,
        )

    if r.status_code not in (200, 202):
        print(f"   ❌ {r.status_code}: {r.text[:300]}")
        return False

    data = r.json()
    job_id = data.get("job_id") or data.get("id")
    if not job_id:
        # Synchronous fallback (older endpoint): report inline result.
        msg = data.get("message", data)
        print(f"   ✅ (sync) {msg}")
        return True

    print(f"   📨 accepted, job_id={job_id}")
    return poll_job(session, job_id, label, poll_timeout)


# ---------------------------------------------------------------------------
# Verification: distributor analytics
# ---------------------------------------------------------------------------

def check_analytics(session: requests.Session) -> bool:
    """GET /distributor/analytics/applications — verify DWH is populated."""
    print("\n📊 Checking distributor analytics...")
    try:
        r = session.get(
            f"{BASE}/distributor/analytics/applications",
            timeout=TIMEOUT_ANALYTICS,
        )
    except requests.exceptions.ReadTimeout:
        print(f"   ⚠️  Timeout ({TIMEOUT_ANALYTICS}s) — ClickHouse may still be processing")
        return False

    if r.status_code == 403:
        print("   ⚠️  403 Forbidden — user is not a distributor. Skipping analytics check.")
        return True

    if r.status_code >= 400:
        print(f"   ❌ {r.status_code}: {r.text[:200]}")
        return False

    data = r.json()
    by_status = data.get("by_status", {})
    total = sum(v.get("count", 0) for v in by_status.values())
    print(f"   ✅ Total LCA in DWH: {total}")
    for status, info in sorted(by_status.items()):
        print(f"      {status}: {info.get('count', 0)}")
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "small"
    if mode not in ("small", "full"):
        print(f"Usage: {sys.argv[0]} [small|full]")
        sys.exit(1)

    d = CSV_DIR / mode
    poll_timeout = JOB_POLL_TIMEOUT_SMALL if mode == "small" else JOB_POLL_TIMEOUT_FULL

    # Required files (companies.csv + lca.csv from generate_csv.py;
    # the rest from generate_dealer_layer.py).
    companies_csv = d / "companies.csv"
    dealers_csv = d / "companies_dealers.csv"
    links_csv = d / "distributor_dealer_links.csv"
    users_csv = d / "users.csv"            # optional
    vehicles_csv = d / "vehicles_master.csv"
    lca_csv = d / "lca.csv"
    ex_req_csv = d / "exchange_requests.csv"
    ex_bid_csv = d / "exchange_bids.csv"

    missing = [p for p in (companies_csv, dealers_csv, links_csv, vehicles_csv,
                           lca_csv, ex_req_csv, ex_bid_csv) if not p.exists()]
    if missing:
        print("❌ Missing inputs — run generators first:")
        print(f"     python generate_csv.py {mode}")
        print(f"     python generate_dealer_layer.py {mode}")
        for p in missing:
            print(f"   • {p}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"BULK IMPORT — {mode.upper()}  ({d})")
    print(f"{'='*60}")

    t0 = time.monotonic()
    session = requests.Session()

    if not login(session):
        sys.exit(1)

    # 1. Companies (clients + LCs first, then dealers + distributors).
    steps = [
        ("/companies/import", companies_csv, "companies (clients+LCs)", True),
        ("/companies/import", dealers_csv, "companies (dealers+distributors)", True),
        # 2. Distributor ⇄ dealer links.
        ("/admin/companies/distributor-dealer-links/import", links_csv,
         "distributor-dealer links", True),
        # 3. Users (optional).
        ("/users/import", users_csv, "users", False),
        # 4. Vehicles master (warehouse stock).
        ("/vehicles/import", vehicles_csv, "vehicles master", True),
        # 5. Applications / LCA.
        ("/admin/applications/import", lca_csv, "applications (LCA)", True),
        # 6. Exchange requests then bids (bids reference requests).
        ("/exchange/requests/import", ex_req_csv, "exchange requests", True),
        ("/exchange/bids/import", ex_bid_csv, "exchange bids", True),
    ]

    for endpoint, path, label, required in steps:
        if not upload_and_wait(session, endpoint, path, label, poll_timeout, required=required):
            print(f"\n❌ Step failed: {label}. Aborting.")
            sys.exit(1)
        time.sleep(0.5)  # let the DB settle between steps

    # 7. Verify.
    check_analytics(session)

    elapsed = time.monotonic() - t0
    print(f"\n{'='*60}")
    print(f"✅ DONE in {elapsed:.0f}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
