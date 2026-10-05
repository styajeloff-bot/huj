#!/usr/bin/env python3
"""Generate import-ready CSV files from the generated_data export.

Usage:  python generate_csv.py        # small (200 apps, deterministic head slice)
        python generate_csv.py full   # full (~600K apps)

Reads source from:
    scripts/generated_data/{leasing_companies,clients,applications}.csv

Output:
    leasing_export/import/small/    — small test CSVs
    leasing_export/import/full/     — full CSVs

Each folder contains:
    companies.csv  — clients + leasing companies (for /companies/import)
    lca.csv        — LCA rows + dealer_company_id + financials (for /admin/applications/import)

The "small" subset is the same 200 application_keys (sorted) that
generate_dealer_layer.py uses, so the two outputs reference the same apps.
"""

import csv
import sys
import uuid
from collections import defaultdict
from pathlib import Path

try:
    from scripts import _dealer_ids as dealer_ids
except ImportError:
    import _dealer_ids as dealer_ids  # type: ignore[import-not-found,no-redef]

SCRIPT_DIR = Path(__file__).resolve().parent
DATA = SCRIPT_DIR / "generated_data"
EXPORT = Path("~/projects/carcraft-leadgenerator/leasing_export").expanduser()
OUT = EXPORT / "import"

# Must match generate_dealer_layer.SMALL_APP_LIMIT so both scripts pick the
# same subset of applications in "small" mode.
SMALL_APP_LIMIT = 200
FULL_APP_TARGET = 50_043

# Financial columns copied verbatim from applications.csv onto each LCA row so
# the distributor analytics dashboards have per-application financials.
FINANCIAL_COLS = [
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
]

STATUS_MAP = {
    "under_review": "under_review",
    "under_review_with_docs": "under_review_with_docs",
    "document_request": "documents_required",
    "approved": "approved_final",
    "rejected": "rejected_approved",
    "rejected_prescoring": "rejected_prescoring",
}

GRANULAR_LCA_STATUSES = {
    "under_review",
    "under_review_with_docs",
    "documents_required",
    "approved_scoring",
    "approved_scoring_another_cond",
    "approved_final",
    "approved_final_another_cond",
    "selected_lc",
    "deal",
    "rejected_approved",
    "rejected_prescoring",
}


# ---------------------------------------------------------------------------
# Subset selection (shared logic with generate_dealer_layer.py)
# ---------------------------------------------------------------------------

def _small_app_keys() -> set[str]:
    """First SMALL_APP_LIMIT application_keys, sorted — deterministic subset."""
    keys: set[str] = set()
    with open(DATA / "applications.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            k = r.get("application_key", "").strip()
            if k:
                keys.add(k)
    return set(sorted(keys)[:SMALL_APP_LIMIT])


def _load_lc_keys() -> set[str]:
    with open(DATA / "leasing_companies.csv", encoding="utf-8-sig") as f:
        return {
            row["lc_key"].strip()
            for row in csv.DictReader(f)
            if row.get("lc_key", "").strip()
        }


def _full_app_keys() -> set[str]:
    """Deterministic full-mode sample of LCA-eligible parent applications."""
    lc_keys = _load_lc_keys()
    vehicle_keys = set(_load_vehicle_rows())
    eligible: set[str] = set()

    with open(DATA / "applications.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            app_key = row.get("application_key", "").strip()
            if not app_key or app_key not in vehicle_keys:
                continue
            if not row.get("lc_link_status", "").strip():
                continue
            if not any(
                key.strip() in lc_keys
                for key in row.get("leasing_company_keys", "").split(";")
            ):
                continue
            eligible.add(app_key)

    return set(sorted(eligible)[:FULL_APP_TARGET])


# ---------------------------------------------------------------------------
# Step 1: companies.csv
# ---------------------------------------------------------------------------

def build_companies_csv(mode: str, keep_apps: set[str] | None) -> list[dict]:
    """Merge LCs + clients into import format. UUIDs from CSV preserved as id."""
    rows: list[dict] = []

    # Leasing companies (always full — only 15)
    with open(DATA / "leasing_companies.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({
                "id": r["lc_key"].strip(),
                "name": r["company_name"].strip(),
                "inn": r.get("company_inn", "").strip(),
                "company_type": "leasing_company",
                "phone": r.get("company_phone", "").strip(),
                "email": r.get("company_email", "").strip(),
            })
    print(f"  LCs: {len(rows)}")

    # Clients — for small mode, only those referenced by the kept applications.
    needed: set[str] | None = None
    if mode == "small":
        needed = set()
        with open(DATA / "applications.csv", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("application_key", "").strip() in (keep_apps or set()):
                    needed.add(r.get("client_key", "").strip())

    with open(DATA / "clients.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            ck = r["client_key"].strip()
            if needed is not None and ck not in needed:
                continue
            rows.append({
                "id": ck,
                "name": r.get("company_name", "").strip() or f"Клиент {ck[:8]}",
                "inn": r.get("company_inn", "").strip(),
                "company_type": "other",
                "phone": r.get("company_phone", "").strip(),
                "email": r.get("company_email", "").strip(),
            })

    print(f"  Total companies: {len(rows)}")
    return rows


# ---------------------------------------------------------------------------
# Step 2: lca.csv
# ---------------------------------------------------------------------------

def _load_vehicle_rows() -> dict[str, dict[str, str]]:
    vehicles: dict[str, dict[str, str]] = {}
    with open(DATA / "vehicles.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            app_key = row.get("application_key", "").strip()
            if app_key and app_key not in vehicles:
                vehicles[app_key] = row
    return vehicles


def _load_client_inns() -> dict[str, str]:
    client_inns: dict[str, str] = {}
    with open(DATA / "clients.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            client_key = row.get("client_key", "").strip()
            if client_key:
                client_inns[client_key] = row.get("company_inn", "").strip()
    return client_inns


def _normalize_percent_value(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    try:
        numeric = float(stripped)
    except ValueError:
        return stripped
    if 0 < numeric <= 1:
        numeric *= 100
    return f"{numeric:g}"


def _display_inn(raw_inn: str, client_key: str) -> str:
    digits = "".join(ch for ch in raw_inn if ch.isdigit())
    if len(digits) in {10, 12}:
        return digits
    synthetic = 1_000_000_000 + (
        dealer_ids.stable_hash(f"display-inn.{client_key}.{digits}") % 9_000_000_000
    )
    return str(synthetic)


def _display_mmdd(created_at: str, application_key: str) -> str:
    if len(created_at) >= 10 and created_at[4] == "-" and created_at[7] == "-":
        month = created_at[5:7]
        day = created_at[8:10]
        if month.isdigit() and day.isdigit() and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return f"{month}{day}"
    digest = dealer_ids.stable_hash(f"display-date.{application_key}")
    month_val = (digest % 12) + 1
    day_val = ((digest // 12) % 28) + 1
    return f"{month_val:02d}{day_val:02d}"


def build_lca_csv(mode: str, keep_apps: set[str] | None) -> list[dict]:
    """Generate LCA rows with status mapping and LC key splitting."""
    vehicle_rows = _load_vehicle_rows()
    client_inns = _load_client_inns()
    display_sequences: defaultdict[tuple[str, str], int] = defaultdict(int)
    lc_key_map = {}
    with open(DATA / "leasing_companies.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            lc_key_map[r["lc_key"].strip()] = True

    rows: list[dict] = []
    skipped_no_lc = 0
    skipped_no_status = 0

    with open(DATA / "applications.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            app_key = r["application_key"].strip()
            if keep_apps is not None and app_key not in keep_apps:
                continue
            lc_status = r.get("lc_link_status", "").strip()
            lc_keys_raw = r.get("leasing_company_keys", "")
            client_key = r.get("client_key", "").strip()
            created_at = r.get("created_at", "").strip()

            if not lc_status:
                skipped_no_status += 1
                continue

            lc_ids = [
                k.strip()
                for k in lc_keys_raw.split(";")
                if k.strip() and k.strip() in lc_key_map
            ]
            if not lc_ids:
                skipped_no_lc += 1
                continue

            source_status = r.get("status", "").strip()
            lca_status = (
                source_status
                if source_status in GRANULAR_LCA_STATUSES
                else STATUS_MAP.get(lc_status, lc_status)
            )

            # Same hashing as vehicles_master so a vehicle and its application
            # land on the SAME dealer (shared _dealer_ids helper).
            dealer_company_id = dealer_ids.dealer_id_for_key(app_key)

            financials = {col: r.get(col, "").strip() for col in FINANCIAL_COLS}
            for col in ("down_payment_percent", "rate"):
                financials[col] = _normalize_percent_value(financials[col])

            vehicle_row = vehicle_rows.get(app_key, {})
            vehicle_linkage = {
                "vehicle_id": vehicle_row.get("vehicle_id", "").strip(),
                "modification_id": vehicle_row.get("modification_id", "").strip(),
                "quantity": vehicle_row.get("quantity", "1").strip() or "1",
                "unit_price": vehicle_row.get("unit_price", "").strip(),
                "total_price": vehicle_row.get("total_price", "").strip(),
            }
            client_inn = _display_inn(client_inns.get(client_key) or "", client_key)
            mmdd = _display_mmdd(created_at, app_key)
            display_key = (client_inn, mmdd)
            display_sequences[display_key] += 1
            display_number = (
                f"{client_inn}-{mmdd}-{display_sequences[display_key]:03d}"
            )

            for lc_id in lc_ids:
                row = {
                    "id": str(uuid.uuid4()),
                    "application_id": app_key,
                    "leasing_company_id": lc_id,
                    "status": lca_status,
                    "created_at": created_at,
                    "company_id": client_key,
                    "dealer_company_id": dealer_company_id,
                    "display_number": display_number,
                    "name": r.get("name", "").strip(),
                    "email": r.get("email", "").strip(),
                }
                row.update(financials)
                row.update(vehicle_linkage)
                rows.append(row)

    print(f"  LCA rows: {len(rows)}, skipped: no_LC={skipped_no_lc} no_status={skipped_no_status}")
    return rows


# ---------------------------------------------------------------------------
# Write CSVs
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        print(f"  ⚠️  {path}: empty!")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"  ✅ {path}: {len(rows)} rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "small"
    if mode not in ("small", "full"):
        print("Usage: python generate_csv.py [small|full]")
        sys.exit(1)

    out_dir = OUT / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Generating {mode} CSVs → {out_dir} ===\n")

    keep_apps = _small_app_keys() if mode == "small" else _full_app_keys()
    if keep_apps is not None:
        print(f"  {mode} subset: {len(keep_apps)} applications")

    print("1. companies.csv")
    companies = build_companies_csv(mode, keep_apps)
    write_csv(out_dir / "companies.csv", companies)

    print("\n2. lca.csv")
    lca = build_lca_csv(mode, keep_apps)
    write_csv(out_dir / "lca.csv", lca)

    print(f"\n=== Done: {out_dir} ===\n")


if __name__ == "__main__":
    main()
