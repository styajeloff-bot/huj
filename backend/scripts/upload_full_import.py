#!/usr/bin/env python3
"""Upload full import CSV files and real-stock catalog Excel chunks."""
# ruff: noqa: T201
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

DEFAULT_FULL_DIR = Path(
    "/Users/a_belianskii/projects/carcraft-leadgenerator/"
    "leasing_export/import/full"
)
DEFAULT_CATALOG_DIR = DEFAULT_FULL_DIR / "catalog_real_stock_capped_2500000"
DEFAULT_PHONE = "+76660000001"
DEFAULT_CODE = "0000"
CSV_CONTENT_TYPE = "text/csv"
XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@dataclass(frozen=True)
class UploadStep:
    label: str
    path: Path
    endpoint: str
    poll_endpoint_template: str
    content_type: str
    phase: str
    required: bool = True


@dataclass(frozen=True)
class JobRecord:
    label: str
    filename: str
    source_path: str
    endpoint: str
    poll_endpoint: str
    job_id: str
    status: str
    upload_seconds: str


def normalize_api_base(*, domain: str | None, api_base: str | None) -> str:
    """Build an `/api/v1` base URL from a domain or use an explicit base."""
    if api_base:
        return api_base.strip().rstrip("/")
    if not domain:
        raise ValueError("Provide --domain or --api-base")

    value = domain.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    if value.endswith("/api/v1"):
        return value
    return f"{value}/api/v1"


def _csv_step(
    full_dir: Path,
    filename: str,
    label: str,
    endpoint: str,
    *,
    phase: str = "prerequisite",
    required: bool = True,
) -> UploadStep:
    return UploadStep(
        label=label,
        path=full_dir / filename,
        endpoint=endpoint,
        poll_endpoint_template="/imports/{job_id}",
        content_type=CSV_CONTENT_TYPE,
        phase=phase,
        required=required,
    )


def _catalog_step(path: Path) -> UploadStep:
    return UploadStep(
        label=f"catalog {path.name}",
        path=path,
        endpoint="/catalog/upload",
        poll_endpoint_template="/catalog/uploads/{job_id}",
        content_type=XLSX_CONTENT_TYPE,
        phase="catalog",
    )


def build_upload_plan(
    *,
    full_dir: Path,
    catalog_dir: Path,
    include_vehicles_master: bool = False,
    skip_catalog: bool = False,
    csv_only: bool = False,
    catalog_only: bool = False,
    dependent_only: bool = False,
) -> list[UploadStep]:
    """Return deterministic upload order for a full import run."""
    steps: list[UploadStep] = []

    if not catalog_only and not dependent_only:
        steps.extend(
            [
                _csv_step(
                    full_dir,
                    "companies_clients.csv",
                    "companies clients",
                    "/companies/import",
                ),
                _csv_step(
                    full_dir,
                    "companies_distributor_dealer.csv",
                    "companies dealers/distributors",
                    "/companies/import",
                ),
                _csv_step(
                    full_dir,
                    "distributor_dealer_links.csv",
                    "distributor-dealer links",
                    "/admin/companies/distributor-dealer-links/import",
                ),
                _csv_step(full_dir, "users.csv", "users", "/users/import"),
                _csv_step(
                    full_dir,
                    "warehouses.csv",
                    "warehouses",
                    "/warehouses/import",
                ),
            ]
        )

    if not skip_catalog and not csv_only and not dependent_only:
        steps.extend(_catalog_step(path) for path in sorted(catalog_dir.glob("*.xlsx")))

    if not catalog_only:
        if include_vehicles_master:
            steps.append(
                _csv_step(
                    full_dir,
                    "vehicles_master.csv",
                    "vehicles master legacy CSV",
                    "/vehicles/import",
                    phase="dependent",
                )
            )
        steps.extend(
            [
                _csv_step(
                    full_dir,
                    "lca.csv",
                    "applications LCA",
                    "/admin/applications/import",
                    phase="dependent",
                ),
                _csv_step(
                    full_dir,
                    "exchange_requests.csv",
                    "exchange requests",
                    "/exchange/requests/import",
                    phase="dependent",
                ),
                _csv_step(
                    full_dir,
                    "exchange_bids.csv",
                    "exchange bids",
                    "/exchange/bids/import",
                    phase="dependent",
                ),
            ]
        )

    return steps


def extract_job_id(payload: dict[str, Any]) -> str | None:
    value = payload.get("job_id") or payload.get("jobId") or payload.get("id")
    return str(value) if value else None


def login(
    session: requests.Session,
    *,
    api_base: str,
    phone: str,
    code: str,
    timeout: float,
) -> dict[str, Any]:
    login_response = session.post(
        f"{api_base}/auth/login", json={"phone": phone}, timeout=timeout
    )
    if login_response.status_code >= 400:
        raise RuntimeError(
            f"login failed: {login_response.status_code} "
            f"{login_response.text[:300]}"
        )

    verify_response = session.post(
        f"{api_base}/auth/verify-phone",
        json={"phone": phone, "code": code},
        timeout=timeout,
    )
    if verify_response.status_code >= 400:
        raise RuntimeError(
            f"verify failed: {verify_response.status_code} "
            f"{verify_response.text[:300]}"
        )
    payload = verify_response.json()
    user = payload.get("user") or {}
    if not isinstance(user, dict):
        return {}
    return user


def upload_step(
    session: requests.Session,
    *,
    api_base: str,
    step: UploadStep,
    timeout: float,
    phone: str,
    code: str,
    auth_timeout: float,
) -> JobRecord:
    if not step.path.exists():
        if step.required:
            raise FileNotFoundError(step.path)
        return JobRecord(
            label=step.label,
            filename=step.path.name,
            source_path=str(step.path),
            endpoint=step.endpoint,
            poll_endpoint="",
            job_id="",
            status="skipped",
            upload_seconds="0.000",
        )

    started = time.monotonic()
    with step.path.open("rb") as file_obj:
        response = session.post(
            f"{api_base}{step.endpoint}",
            files={"file": (step.path.name, file_obj, step.content_type)},
            timeout=timeout,
        )
    if response.status_code == 401:
        login(session, api_base=api_base, phone=phone, code=code, timeout=auth_timeout)
        with step.path.open("rb") as file_obj:
            response = session.post(
                f"{api_base}{step.endpoint}",
                files={"file": (step.path.name, file_obj, step.content_type)},
                timeout=timeout,
            )
    elapsed = time.monotonic() - started

    if response.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"{step.label} failed: {response.status_code} "
            f"{response.text[:500]}"
        )

    payload = response.json()
    job_id = extract_job_id(payload)
    status = str(payload.get("status") or "accepted")
    poll_endpoint = (
        step.poll_endpoint_template.format(job_id=job_id) if job_id else ""
    )
    return JobRecord(
        label=step.label,
        filename=step.path.name,
        source_path=str(step.path),
        endpoint=step.endpoint,
        poll_endpoint=poll_endpoint,
        job_id=job_id or "",
        status=status,
        upload_seconds=f"{elapsed:.3f}",
    )


def write_jobs(path: Path, records: list[JobRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(
            file_obj,
            delimiter="\t",
            fieldnames=list(asdict(records[0]).keys()) if records else [
                "label",
                "filename",
                "source_path",
                "endpoint",
                "poll_endpoint",
                "job_id",
                "status",
                "upload_seconds",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))


SUCCESS_STATUSES = {"done", "completed", "success", "succeeded"}
FAILURE_STATUSES = {"failed", "error"}


def poll_job(
    session: requests.Session,
    *,
    api_base: str,
    record: JobRecord,
    timeout: float,
    phone: str,
    code: str,
    auth_timeout: float,
) -> dict[str, Any]:
    """Return a normalized-enough job payload for dependency waiting."""
    if not record.poll_endpoint:
        return {"status": record.status}

    response = session.get(f"{api_base}{record.poll_endpoint}", timeout=timeout)
    if response.status_code == 401:
        login(session, api_base=api_base, phone=phone, code=code, timeout=auth_timeout)
        response = session.get(f"{api_base}{record.poll_endpoint}", timeout=timeout)
    if response.status_code >= 400:
        return {
            "status": "error",
            "error": f"{response.status_code} {response.text[:300]}",
        }
    payload = response.json()
    if not isinstance(payload, dict):
        return {"status": "error", "error": "poll response is not an object"}
    payload["status"] = str(payload.get("status") or "unknown").lower()
    return payload


def _rows_text(payload: dict[str, Any]) -> str:
    rows_done = payload.get("rows_done", payload.get("rowsDone", 0))
    rows_total = payload.get("rows_total", payload.get("rowsTotal", 0))
    return f"{rows_done}/{rows_total}"


def wait_for_records(
    session: requests.Session,
    *,
    api_base: str,
    records: list[JobRecord],
    title: str,
    poll_timeout: float,
    poll_interval: float,
    max_wait: float,
    phone: str,
    code: str,
    auth_timeout: float,
) -> None:
    """Block until a phase is fully materialized before dependent uploads."""
    active_records = [record for record in records if record.job_id]
    if not active_records:
        return

    print(f"Waiting for {title}: {len(active_records)} job(s)")
    deadline = time.monotonic() + max_wait if max_wait else None
    while True:
        snapshots = [
            (
                record,
                poll_job(
                    session,
                    api_base=api_base,
                    record=record,
                    timeout=poll_timeout,
                    phone=phone,
                    code=code,
                    auth_timeout=auth_timeout,
                ),
            )
            for record in active_records
        ]
        status_counts: dict[str, int] = {}
        failures: list[tuple[JobRecord, dict[str, Any]]] = []
        for record, payload in snapshots:
            status = str(payload.get("status") or "unknown").lower()
            status_counts[status] = status_counts.get(status, 0) + 1
            if status in FAILURE_STATUSES:
                failures.append((record, payload))

        summary = ", ".join(
            f"{status}={count}" for status, count in sorted(status_counts.items())
        )
        current = max(
            snapshots,
            key=lambda item: int(
                item[1].get("rows_done", item[1].get("rowsDone", 0)) or 0
            ),
        )
        print(
            f"  {title}: {summary}; "
            f"sample={current[0].filename} rows={_rows_text(current[1])}"
        )

        if failures:
            record, payload = failures[0]
            raise RuntimeError(
                f"{title} failed at {record.filename}: "
                f"{payload.get('error') or payload}"
            )
        if all(
            str(payload.get("status") or "").lower() in SUCCESS_STATUSES
            for _, payload in snapshots
        ):
            return
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {title}")
        time.sleep(poll_interval)


def _default_jobs_file(full_dir: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return full_dir / f"full-import-jobs-{stamp}.tsv"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload full CSV imports and catalog Excel chunks."
    )
    parser.add_argument("--domain", help="Deployment domain, e.g. test.multileasing.ru")
    parser.add_argument("--api-base", help="Explicit API base, e.g. https://host/api/v1")
    parser.add_argument("--phone", default=DEFAULT_PHONE)
    parser.add_argument("--code", default=DEFAULT_CODE)
    parser.add_argument("--full-dir", type=Path, default=DEFAULT_FULL_DIR)
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_CATALOG_DIR)
    parser.add_argument("--jobs-file", type=Path)
    parser.add_argument("--include-vehicles-master", action="store_true")
    parser.add_argument("--skip-catalog", action="store_true")
    parser.add_argument("--csv-only", action="store_true")
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument(
        "--dependent-only",
        action="store_true",
        help="Upload only LCA/exchange dependent CSV files.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--auth-timeout", type=float, default=30.0)
    parser.add_argument("--upload-timeout", type=float, default=900.0)
    parser.add_argument("--poll-timeout", type=float, default=60.0)
    parser.add_argument("--poll-interval", type=float, default=30.0)
    parser.add_argument(
        "--max-wait",
        type=float,
        default=0.0,
        help="Maximum seconds to wait per phase; 0 means wait indefinitely.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Only enqueue uploads; do not wait for prerequisite phases.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    api_base = normalize_api_base(domain=args.domain, api_base=args.api_base)
    full_dir = args.full_dir.expanduser()
    catalog_dir = args.catalog_dir.expanduser()
    jobs_file = args.jobs_file or _default_jobs_file(full_dir)

    steps = build_upload_plan(
        full_dir=full_dir,
        catalog_dir=catalog_dir,
        include_vehicles_master=args.include_vehicles_master,
        skip_catalog=args.skip_catalog,
        csv_only=args.csv_only,
        catalog_only=args.catalog_only,
        dependent_only=args.dependent_only,
    )
    missing = [step.path for step in steps if step.required and not step.path.exists()]
    if missing:
        print("Missing required inputs:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 2

    print(f"API base: {api_base}")
    print(f"Full dir: {full_dir}")
    print(f"Catalog dir: {catalog_dir}")
    print("Safe skips: vehicles_master.csv and catalog_mini.csv by default")
    print(f"Steps: {len(steps)}")
    for index, step in enumerate(steps, start=1):
        print(f"{index:02d}. {step.label}: {step.path.name} -> {step.endpoint}")

    if args.dry_run:
        print("Dry run only, nothing uploaded.")
        return 0

    session = requests.Session()
    user = login(
        session,
        api_base=api_base,
        phone=args.phone,
        code=args.code,
        timeout=args.auth_timeout,
    )
    print(
        "Authenticated: "
        f"phone={user.get('phone', args.phone)} role={user.get('role', 'unknown')}"
    )

    records: list[JobRecord] = []
    phase_records: list[JobRecord] = []
    current_phase: str | None = None
    for index, step in enumerate(steps, start=1):
        if (
            current_phase is not None
            and step.phase != current_phase
            and not args.no_wait
        ):
            wait_for_records(
                session,
                api_base=api_base,
                records=phase_records,
                title=current_phase,
                poll_timeout=args.poll_timeout,
                poll_interval=args.poll_interval,
                max_wait=args.max_wait,
                phone=args.phone,
                code=args.code,
                auth_timeout=args.auth_timeout,
            )
            phase_records = []
        current_phase = step.phase

        print(f"[{index}/{len(steps)}] Uploading {step.path.name}...")
        record = upload_step(
            session,
            api_base=api_base,
            step=step,
            timeout=args.upload_timeout,
            phone=args.phone,
            code=args.code,
            auth_timeout=args.auth_timeout,
        )
        records.append(record)
        phase_records.append(record)
        write_jobs(jobs_file, records)
        print(
            f"  status={record.status} job_id={record.job_id or '-'} "
            f"elapsed={record.upload_seconds}s"
        )

    if phase_records and not args.no_wait:
        wait_for_records(
            session,
            api_base=api_base,
            records=phase_records,
            title=current_phase or "final",
            poll_timeout=args.poll_timeout,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait,
            phone=args.phone,
            code=args.code,
            auth_timeout=args.auth_timeout,
        )

    print(f"Jobs written: {jobs_file}")
    print(
        "Poll with: uv run python scripts/poll_full_import_jobs.py "
        f"--api-base {api_base} --jobs-file {jobs_file}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
