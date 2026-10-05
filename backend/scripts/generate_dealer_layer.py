#!/usr/bin/env python3
"""Synthesize the dealer / distributor / warehouse / exchange layer.

The exported leasing dataset (clients, leasing companies, applications, vehicle
line-items) has NO dealers, NO distributors, NO vehicle-master rows and NO
exchange data — so the distributor analytics dashboards (which are scoped
entirely by dealer) come up empty.  This generator fabricates that missing layer
and stitches it onto the existing data deterministically.

Usage:  python generate_dealer_layer.py        # small subset
        python generate_dealer_layer.py full    # full dataset

Inputs (read-only, comma-delimited, utf-8-sig):
    generated_data/applications.csv  — financials + final status
    generated_data/vehicles.csv      — line-items (application_key, vehicle_id, unit_price, ...)

Output (semicolon-delimited, utf-8-sig BOM — matches the import routes) into the
SAME folder generate_csv.py uses:
    leasing_export/import/{small,full}/
        companies_dealers.csv
        distributor_dealer_links.csv
        catalog_mini.csv
        vehicles_master.csv
        exchange_requests.csv
        exchange_bids.csv

Determinism: every random choice is seeded from a blake2b hash of a stable key
(application_key / vehicle_id / request id), so re-runs are byte-identical and a
vehicle lands on the same dealer as its application (shared _dealer_ids helper).
"""

from __future__ import annotations

import csv
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

try:
    from scripts import _dealer_ids as ids
except ImportError:
    import _dealer_ids as ids  # type: ignore[import-not-found,no-redef]

# ---------------------------------------------------------------------------
# Paths — read from generated_data/, write to leasing_export/import/{mode}/
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA = SCRIPT_DIR / "generated_data"
EXPORT = Path("~/projects/carcraft-leadgenerator/leasing_export").expanduser()
OUT = EXPORT / "import"

# "small" mode keeps a deterministic, application_key-sorted head slice so the
# dealer assignment is stable and the dashboards still have a usable sample.
SMALL_APP_LIMIT = 200

# Fixed namespace for synthesized row ids (vehicles_master, exchange rows).
_NS = uuid.UUID("c0ffee00-dea1-5eed-b00c-000000000002")

# How many extra (application-free) vehicles to add per dealer for the warehouse
# tab — stock that is not tied to any leasing application.
EXTRA_INVENTORY_PER_DEALER = 20
FULL_AVAILABLE_CAP_PER_DEALER = 300
FULL_RESERVED_CAP_PER_DEALER = 40
FULL_EXTRA_AVAILABLE_PER_DEALER = 15
FULL_EXTRA_RESERVED_PER_DEALER = EXTRA_INVENTORY_PER_DEALER - FULL_EXTRA_AVAILABLE_PER_DEALER
MAX_VEHICLE_PRICE = 2_500_000

# Roughly how many vehicle_ids get exchange requests.
EXCHANGE_REQUEST_TARGET = 300

CATALOG_MARKS = [
    "Lada", "Kia", "Hyundai", "Toyota", "Haval", "Chery", "Geely", "Omoda",
]
MODELS_PER_MARK = 4
_MODEL_NAMES = {
    "Lada": ["Vesta", "Granta", "Largus", "Niva"],
    "Kia": ["Rio", "Sportage", "Seltos", "Sorento"],
    "Hyundai": ["Solaris", "Creta", "Tucson", "Santa Fe"],
    "Toyota": ["Camry", "RAV4", "Corolla", "Land Cruiser"],
    "Haval": ["Jolion", "F7", "Dargo", "H9"],
    "Chery": ["Tiggo 4", "Tiggo 7", "Tiggo 8", "Arrizo 8"],
    "Geely": ["Coolray", "Atlas", "Tugella", "Monjaro"],
    "Omoda": ["C5", "S5", "C5 GT", "S5 GT"],
}

_COLORS = ["Белый", "Чёрный", "Серебристый", "Синий", "Красный", "Серый", "Зелёный"]

# Application final statuses that bias a promoted vehicle toward "sold".
_DEAL_STATUSES = {"deal"}

SEED_LOGIN_USERS = [
    {
        "seed": "seed.admin.1",
        "phone": "+76660000001",
        "role": "carcraft_employee",
        "name": "Админ 1",
        "email": "admin1@carcraft.ru",
        "company_id": "",
    },
    {
        "seed": "seed.admin.2",
        "phone": "+76660000002",
        "role": "carcraft_employee",
        "name": "Админ 2",
        "email": "admin2@carcraft.ru",
        "company_id": "",
    },
    {
        "seed": "seed.role.dealer",
        "phone": "+76661234568",
        "role": "dealer",
        "name": "Тестовый дилер",
        "email": "test-dealer@carcraft-demo.ru",
        "company_id": "",
    },
    {
        "seed": "seed.role.lc.1",
        "phone": "+76661234571",
        "role": "leasing_company",
        "name": "Тестовая ЛК 1",
        "email": "test-lc1@carcraft-demo.ru",
        "company_id": "",
    },
    {
        "seed": "seed.role.lc.2",
        "phone": "+76661234572",
        "role": "leasing_company",
        "name": "Тестовая ЛК 2",
        "email": "test-lc2@carcraft-demo.ru",
        "company_id": "",
    },
    {
        "seed": "seed.role.distributor.1",
        "phone": "+76661234573",
        "role": "distributor",
        "name": "Тестовый дистрибьютор 1",
        "email": "test-distributor1@carcraft-demo.ru",
        "company_id": "",
    },
    {
        "seed": "seed.role.distributor.2",
        "phone": "+76661234574",
        "role": "distributor",
        "name": "Тестовый дистрибьютор 2",
        "email": "test-distributor2@carcraft-demo.ru",
        "company_id": "",
    },
]


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------

def _rng(*parts: str) -> random.Random:
    """A Random seeded deterministically from stable string parts."""
    return random.Random(ids.stable_hash("|".join(parts)))


def _row_uuid(seed: str) -> str:
    return str(uuid.uuid5(_NS, seed))


def _date_in_range(rng: random.Random, start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, span))


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Catalog (a) — built first; vehicles reference it deterministically
# ---------------------------------------------------------------------------

def build_catalog() -> list[dict]:
    rows: list[dict] = []
    for mark in CATALOG_MARKS:
        mark_id = _row_uuid(f"mark.{mark}")
        for model in _MODEL_NAMES[mark]:
            rows.append({
                "mark_id": mark_id,
                "mark_name": mark,
                "model_id": _row_uuid(f"model.{mark}.{model}"),
                "model_name": model,
            })
    return rows


def _catalog_lookup(catalog: list[dict]) -> list[tuple[str, str]]:
    """Flat list of (mark, model) for deterministic picking.

    The distributor analytics charts display ``dwh_vehicles.mark_id`` /
    ``model_id`` verbatim (no catalog join), so we store the human-readable
    NAME in those columns — otherwise the warehouse/financials charts would
    show opaque UUIDs. ``catalog_mini.csv`` keeps the id↔name mapping for
    reference.
    """
    return [(r["mark_name"], r["model_name"]) for r in catalog]


# ---------------------------------------------------------------------------
# Companies (a) + links (b)
# ---------------------------------------------------------------------------

def build_companies_dealers() -> list[dict]:
    rows: list[dict] = []
    for d in ids.DISTRIBUTORS:
        rows.append(_company_row(d))
    for d in ids.DEALERS:
        rows.append(_company_row(d))
    return rows


def _company_row(meta: dict) -> dict:
    return {
        "id": meta["id"],
        "name": meta["name"],
        "inn": meta["inn"],
        "company_type": meta["company_type"],
        "phone": meta["phone"],
        "email": meta["email"],
        "legal_address": meta["legal_address"],
        "actual_address": meta["actual_address"],
        "city": meta["city"],
        "region": meta["region"],
    }


def build_links() -> list[dict]:
    rows: list[dict] = []
    for dealer in ids.DEALERS:
        rows.append({
            "distributor_company_id": ids.distributor_id(dealer["distributor_index"]),
            "dealer_company_id": dealer["id"],
        })
    return rows


# ---------------------------------------------------------------------------
# Read source vehicles + application statuses
# ---------------------------------------------------------------------------

def _load_app_status(mode: str) -> dict[str, str]:
    """application_key -> final status. Honours the small subset."""
    apps = DATA / "applications.csv"
    status: dict[str, str] = {}
    with open(apps, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            status[r["application_key"].strip()] = r.get("status", "").strip()
    if mode == "small":
        keep = sorted(status)[:SMALL_APP_LIMIT]
        status = {k: status[k] for k in keep}
    return status


def _load_vehicles(allowed_apps: set[str] | None) -> list[dict]:
    """Distinct source vehicle line-items, optionally filtered to small subset."""
    veh = DATA / "vehicles.csv"
    seen: set[str] = set()
    out: list[dict] = []
    with open(veh, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            app_key = r["application_key"].strip()
            vehicle_id = r["vehicle_id"].strip()
            if allowed_apps is not None and app_key not in allowed_apps:
                continue
            if vehicle_id in seen:
                continue
            seen.add(vehicle_id)
            out.append({
                "vehicle_id": vehicle_id,
                "application_key": app_key,
                "unit_price": r.get("unit_price", "").strip(),
            })
    return out


# ---------------------------------------------------------------------------
# Vehicles master (d)
# ---------------------------------------------------------------------------

def _price_int(raw: str, fallback: int) -> int:
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = fallback
    return min(value, MAX_VEHICLE_PRICE)


WAREHOUSES_PER_DEALER = 2


def build_warehouses() -> tuple[list[dict], dict[int, list[str]]]:
    """One+ warehouse per dealer. Returns (rows, {dealer_idx: [warehouse_id, ...]})."""
    rows: list[dict] = []
    by_dealer: dict[int, list[str]] = {}
    for i, dealer in enumerate(ids.DEALERS):
        wh_ids: list[str] = []
        for k in range(WAREHOUSES_PER_DEALER):
            wid = _row_uuid(f"warehouse.{i}.{k}")
            wh_ids.append(wid)
            rows.append({
                "id": wid,
                "address": f"{dealer['city']}, складская площадка №{k + 1}",
                "brand": "Мультибренд",
                "dealer_id": ids.dealer_id(i),
                "company_id": ids.dealer_id(i),
                "status": "active",
            })
        by_dealer[i] = wh_ids
    return rows, by_dealer


def build_vehicles_master(
    mode: str,
    catalog: list[dict],
    app_status: dict[str, str],
    warehouses_by_dealer: dict[int, list[str]],
) -> list[dict]:
    pairs = _catalog_lookup(catalog)

    def _warehouse_for(dealer_idx: int, vehicle_id: str) -> str:
        whs = warehouses_by_dealer[dealer_idx]
        index = int(ids.stable_hash(f"wh.{vehicle_id}")) % len(whs)
        return whs[index]

    allowed = set(app_status) if mode == "small" else None
    src = _load_vehicles(allowed)
    full_stock_statuses = (
        _full_application_stock_statuses(src, app_status) if mode == "full" else {}
    )

    start = datetime(2022, 1, 1)
    end = datetime(2024, 12, 31, 23, 59, 59)
    rows: list[dict] = []
    used_vins: set[str] = set()

    # --- promoted vehicles (tied to applications) ---
    for v in src:
        vehicle_id = v["vehicle_id"]
        app_key = v["application_key"]
        rng = _rng("vehicle", vehicle_id)

        dealer_idx = ids.dealer_index_for_key(app_key)
        dealer = ids.dealer_id(dealer_idx)
        mark_id, model_id = pairs[ids.stable_hash(f"cat.{vehicle_id}") % len(pairs)]

        base_price = _price_int(v["unit_price"], rng.randint(1_500_000, 9_000_000))
        special = int(base_price * rng.choice([0.0, 0.0, 0.95, 0.97, 0.93])) or ""

        if mode == "full":
            status = full_stock_statuses.get(vehicle_id, "sold")
        else:
            is_deal = app_status.get(app_key, "") in _DEAL_STATUSES
            status = _pick_status(rng, bias_sold=is_deal)

        rows.append(_vehicle_row(
            vehicle_id=vehicle_id,
            dealer=dealer,
            warehouse_id=_warehouse_for(dealer_idx, vehicle_id),
            mark_id=mark_id,
            model_id=model_id,
            base_price=base_price,
            special=special,
            status=status,
            rng=rng,
            start=start,
            end=end,
            used_vins=used_vins,
        ))

    # --- extra free inventory per dealer (warehouse stock, no application) ---
    for dealer_idx in range(ids.NUM_DEALERS):
        dealer = ids.dealer_id(dealer_idx)
        for j in range(EXTRA_INVENTORY_PER_DEALER):
            seed = f"extra.{dealer_idx}.{j}"
            vehicle_id = _row_uuid(seed)
            rng = _rng("extra-vehicle", seed)
            mark_id, model_id = pairs[ids.stable_hash(f"cat.{seed}") % len(pairs)]
            base_price = _price_int("", rng.randint(1_500_000, 9_000_000))
            special = int(base_price * rng.choice([0.0, 0.0, 0.95, 0.97])) or ""
            # Free stock is only available/reserved (never sold). In full mode
            # this split is fixed so total current stock remains capped.
            status = (
                _full_extra_inventory_status(j)
                if mode == "full"
                else rng.choice(["available", "available", "available", "reserved"])
            )
            rows.append(_vehicle_row(
                vehicle_id=vehicle_id,
                dealer=dealer,
                warehouse_id=_warehouse_for(dealer_idx, vehicle_id),
                mark_id=mark_id,
                model_id=model_id,
                base_price=base_price,
                special=special,
                status=status,
                rng=rng,
                start=start,
                end=end,
                used_vins=used_vins,
            ))

    return rows


def _full_application_stock_statuses(
    src: list[dict],
    app_status: dict[str, str],
) -> dict[str, str]:
    """Pick bounded current-stock application rows per dealer for full exports."""
    available_limit = FULL_AVAILABLE_CAP_PER_DEALER - FULL_EXTRA_AVAILABLE_PER_DEALER
    reserved_limit = FULL_RESERVED_CAP_PER_DEALER - FULL_EXTRA_RESERVED_PER_DEALER
    by_dealer: dict[int, list[dict]] = {}
    for row in src:
        app_key = row["application_key"]
        if app_status.get(app_key, "") in _DEAL_STATUSES:
            continue
        dealer_idx = ids.dealer_index_for_key(app_key)
        by_dealer.setdefault(dealer_idx, []).append(row)

    statuses: dict[str, str] = {}
    for dealer_idx, dealer_rows in by_dealer.items():
        ordered = sorted(
            dealer_rows,
            key=lambda row: ids.stable_hash(
                f"full-stock.{dealer_idx}.{row['vehicle_id']}"
            ),
        )
        for row in ordered[:available_limit]:
            statuses[row["vehicle_id"]] = "available"
        reserved_start = available_limit
        reserved_end = reserved_start + reserved_limit
        for row in ordered[reserved_start:reserved_end]:
            statuses[row["vehicle_id"]] = "reserved"
    return statuses


def _full_extra_inventory_status(index: int) -> str:
    if index < FULL_EXTRA_AVAILABLE_PER_DEALER:
        return "available"
    if index < FULL_EXTRA_AVAILABLE_PER_DEALER + FULL_EXTRA_RESERVED_PER_DEALER:
        return "reserved"
    return "sold"


def _pick_status(rng: random.Random, bias_sold: bool) -> str:
    if bias_sold:
        return rng.choices(
            ["sold", "reserved", "available"], weights=[70, 20, 10]
        )[0]
    return rng.choices(
        ["available", "reserved", "sold"], weights=[55, 25, 20]
    )[0]


def _make_vin(seed: str, used: set[str]) -> str:
    """Deterministic 17-char VIN-ish string, unique within the run."""
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    salt = 0
    while True:
        h = ids.stable_hash(f"vin.{seed}.{salt}")
        chars = []
        n = h
        for _ in range(17):
            chars.append(alphabet[n % len(alphabet)])
            n //= len(alphabet)
        vin = "".join(chars)
        if vin not in used:
            used.add(vin)
            return vin
        salt += 1


def _vehicle_row(
    *,
    vehicle_id: str,
    dealer: str,
    warehouse_id: str,
    mark_id: str,
    model_id: str,
    base_price: int,
    special: int | str,
    status: str,
    rng: random.Random,
    start: datetime,
    end: datetime,
    used_vins: set[str],
) -> dict:
    return {
        "id": vehicle_id,
        "vin": _make_vin(vehicle_id, used_vins),
        "dealer_id": dealer,
        "warehouse_id": warehouse_id,
        "mark_id": mark_id,
        "model_id": model_id,
        "year": 2022 + (ids.stable_hash(f"year.{vehicle_id}") % 5),
        "base_price": base_price,
        "special_price": special,
        "color": rng.choice(_COLORS),
        "status": status,
        "is_available": 1 if status == "available" else 0,
        "created_at": _iso(_date_in_range(rng, start, end)),
    }


# ---------------------------------------------------------------------------
# Exchange requests (e) + bids (f)
# ---------------------------------------------------------------------------

def build_exchange(
    vehicles_master: list[dict],
    lc_user_ids: list[str],
) -> tuple[list[dict], list[dict]]:
    """Generate requests for a deterministic subset of vehicles, plus bids.

    Returns (requests, bids).  Some requests are closed because a bid was
    accepted; we set those request statuses to 'closed' accordingly.
    """
    # Deterministic subset: sort by id, stride to hit ~EXCHANGE_REQUEST_TARGET.
    candidates = sorted(vehicles_master, key=lambda r: r["id"])
    if not candidates:
        return [], []
    stride = max(1, len(candidates) // EXCHANGE_REQUEST_TARGET)
    subset = candidates[::stride][:EXCHANGE_REQUEST_TARGET]

    requests: list[dict] = []
    bids: list[dict] = []

    start = datetime(2023, 1, 1)
    end = datetime(2024, 12, 31)

    for v in subset:
        vehicle_id = v["id"]
        rng = _rng("exchange-req", vehicle_id)
        req_id = _row_uuid(f"exreq.{vehicle_id}")

        created = _date_in_range(rng, start, end)
        expiration = created + timedelta(days=rng.randint(7, 60))
        discount_type = rng.choice(["fixed", "percent"])
        discount_value = (
            rng.choice([50_000, 100_000, 150_000, 200_000])
            if discount_type == "fixed"
            else rng.choice([3, 5, 7, 10])
        )
        quantity = rng.randint(1, 5)
        # lc_user_id: the leasing-company-side requester — a REAL seeded LC user
        # (FK → users.id), chosen deterministically per vehicle.
        lc_user_id = lc_user_ids[ids.stable_hash(f"lcuser.{vehicle_id}") % len(lc_user_ids)]

        # --- bids for this request ---
        n_bids = rng.randint(1, 4)
        bid_rows, accepted = _build_bids(req_id, vehicle_id, quantity, created, n_bids)
        bids.extend(bid_rows)

        status = "closed" if accepted else rng.choices(
            ["active", "cancelled"], weights=[80, 20]
        )[0]

        requests.append({
            "id": req_id,
            "lc_user_id": lc_user_id,
            "vehicle_id": vehicle_id,
            "quantity": quantity,
            "expiration_date": _iso(expiration),
            "discount_type": discount_type,
            "discount_value": discount_value,
            "status": status,
            "created_at": _iso(created),
        })

    return requests, bids


def _build_bids(
    req_id: str,
    vehicle_id: str,
    req_quantity: int,
    req_created: datetime,
    n_bids: int,
) -> tuple[list[dict], bool]:
    rng = _rng("exchange-bids", req_id)
    # Pick distinct dealers to bid.
    dealer_indices = list(range(ids.NUM_DEALERS))
    rng.shuffle(dealer_indices)
    chosen = dealer_indices[:n_bids]

    # Decide acceptance: ~40% of requests have one accepted bid.
    accept = rng.random() < 0.40
    accept_pos = rng.randrange(n_bids) if accept else -1

    rows: list[dict] = []
    accepted = False
    for pos, dealer_idx in enumerate(chosen):
        brng = _rng("exchange-bid", req_id, str(dealer_idx))
        created = req_created + timedelta(
            hours=brng.randint(1, 24 * 14)
        )
        is_accepted = 1 if pos == accept_pos else 0
        if is_accepted:
            accepted = True
        rows.append({
            "id": _row_uuid(f"exbid.{req_id}.{dealer_idx}"),
            "request_id": req_id,
            "dealer_id": ids.dealer_user_id(dealer_idx),
            "price": brng.randint(1_500_000, 9_000_000),
            "is_accepted": is_accepted,
            "quantity": brng.randint(1, max(1, req_quantity)),
            "created_at": _iso(created),
        })
    return rows, accepted


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print(f"  ✅ {path.name}: {len(rows)} rows")


# Explicit column orders (also the documented import contract).
COLS_COMPANIES = ["id", "name", "inn", "company_type", "phone", "email",
                  "legal_address", "actual_address", "city", "region"]
COLS_LINKS = ["distributor_company_id", "dealer_company_id"]
COLS_USERS = ["id", "phone", "role", "name", "email", "company_id", "is_active"]
COLS_CATALOG = ["mark_id", "mark_name", "model_id", "model_name"]
COLS_WAREHOUSES = ["id", "address", "brand", "dealer_id", "company_id", "status"]
COLS_VEHICLES = ["id", "vin", "dealer_id", "warehouse_id", "mark_id", "model_id",
                 "year", "base_price", "special_price", "color", "status",
                 "is_available", "created_at"]
COLS_EX_REQ = ["id", "lc_user_id", "vehicle_id", "quantity", "expiration_date",
               "discount_type", "discount_value", "status", "created_at"]
COLS_EX_BID = ["id", "request_id", "dealer_id", "price", "is_accepted",
               "quantity", "created_at"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_users() -> tuple[list[dict], list[str]]:
    """Dealer users (one per dealer) + leasing-company users (one per LC).

    Returns (rows, lc_user_ids). Exchange bids reference the dealer users and
    exchange requests reference the LC users, so both FKs (→ users.id) resolve.
    """
    rows: list[dict] = []

    for seed_user in SEED_LOGIN_USERS:
        rows.append({
            "id": _row_uuid(seed_user["seed"]),
            "phone": seed_user["phone"],
            "role": seed_user["role"],
            "name": seed_user["name"],
            "email": seed_user["email"],
            "company_id": seed_user["company_id"],
            "is_active": "true",
        })

    # Dealer users — company_id = dealer COMPANY id.
    for i, dealer in enumerate(ids.DEALERS):
        rows.append({
            "id": ids.dealer_user_id(i),
            "phone": f"+7666{1000000 + i:07d}",
            "role": "dealer",
            "name": f"Менеджер {dealer['name']}",
            "email": f"dealer-user{i}@carcraft-demo.ru",
            "company_id": ids.dealer_id(i),
            "is_active": "true",
        })

    # Leasing-company users — one per LC from the source export.
    lc_user_ids: list[str] = []
    lc_csv = DATA / "leasing_companies.csv"
    with open(lc_csv, encoding="utf-8-sig") as f:
        for j, r in enumerate(csv.DictReader(f)):
            lc_key = r["lc_key"].strip()
            uid = _row_uuid(f"lcuser.account.{lc_key}")
            lc_user_ids.append(uid)
            rows.append({
                "id": uid,
                "phone": f"+7666{2000000 + j:07d}",
                "role": "leasing_company",
                "name": f"ЛК {r.get('company_name', '').strip()}".strip(),
                "email": f"lc-user{j}@carcraft-demo.ru",
                # No company link: leasing companies often pre-exist (under
                # different ids / same INN), which would make the LC user's
                # company FK fail. Exchange only needs a valid users.id.
                "company_id": "",
                "is_active": "true",
            })

    return rows, lc_user_ids


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "small"
    if mode not in ("small", "full"):
        print("Usage: python generate_dealer_layer.py [small|full]")
        sys.exit(1)

    out_dir = OUT / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n=== Generating dealer layer ({mode}) → {out_dir} ===\n")

    print("a. catalog_mini.csv")
    catalog = build_catalog()
    write_csv(out_dir / "catalog_mini.csv", catalog, COLS_CATALOG)

    print("\nb. companies_dealers.csv")
    companies = build_companies_dealers()
    write_csv(out_dir / "companies_dealers.csv", companies, COLS_COMPANIES)

    print("\nc. distributor_dealer_links.csv")
    links = build_links()
    write_csv(out_dir / "distributor_dealer_links.csv", links, COLS_LINKS)

    print("\nc2. users.csv (dealer + leasing-company users)")
    users, lc_user_ids = build_users()
    write_csv(out_dir / "users.csv", users, COLS_USERS)

    print("\nc3. warehouses.csv")
    warehouses, warehouses_by_dealer = build_warehouses()
    write_csv(out_dir / "warehouses.csv", warehouses, COLS_WAREHOUSES)

    print("\nd. vehicles_master.csv")
    app_status = _load_app_status(mode)
    vehicles = build_vehicles_master(mode, catalog, app_status, warehouses_by_dealer)
    write_csv(out_dir / "vehicles_master.csv", vehicles, COLS_VEHICLES)

    print("\ne/f. exchange_requests.csv + exchange_bids.csv")
    requests, bids = build_exchange(vehicles, lc_user_ids)
    write_csv(out_dir / "exchange_requests.csv", requests, COLS_EX_REQ)
    write_csv(out_dir / "exchange_bids.csv", bids, COLS_EX_BID)

    print(f"\n=== Done: {out_dir} ===\n")


if __name__ == "__main__":
    main()
