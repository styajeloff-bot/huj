#!/usr/bin/env python3
"""Poll jobs saved by upload_full_import.py."""
# ruff: noqa: T201
from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests  # type: ignore[import-untyped]

try:
    from scripts.upload_full_import import (
        DEFAULT_CODE,
        DEFAULT_PHONE,
        login,
        normalize_api_base,
    )
except ImportError:  # pragma: no cover - used when run from scripts/ directly
    from upload_full_import import (  # type: ignore[no-redef,import-not-found]
        DEFAULT_CODE,
        DEFAULT_PHONE,
        login,
        normalize_api_base,
    )


SUCCESS_STATUSES = {"done", "completed", "success", "succeeded"}
FAILURE_STATUSES = {"failed", "error"}


@dataclass(frozen=True)
class Progress:
    status: str
    rows_total: int = 0
    rows_done: int = 0
    images_total: int = 0
    images_done: int = 0
    images_failed: int = 0
    errors_count: int = 0
    error: str = ""


def _int_value(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return 0


def normalize_progress(payload: dict[str, Any]) -> Progress:
    """Normalize data-import and catalog job response shapes."""
    return Progress(
        status=str(payload.get("status") or "unknown").lower(),
        rows_total=_int_value(payload, "rows_total", "rowsTotal"),
        rows_done=_int_value(payload, "rows_done", "rowsDone"),
        images_total=_int_value(payload, "images_total", "imagesTotal"),
        images_done=_int_value(payload, "images_done", "imagesDone"),
        images_failed=_int_value(payload, "images_failed", "imagesFailed"),
        errors_count=_int_value(payload, "errors_count", "errorsCount"),
        error=str(payload.get("error") or ""),
    )


def read_jobs(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file_obj:
        return list(csv.DictReader(file_obj, delimiter="\t"))


def poll_record(
    session: requests.Session,
    *,
    api_base: str,
    record: dict[str, str],
    timeout: float,
) -> Progress:
    poll_endpoint = record.get("poll_endpoint") or ""
    if not poll_endpoint:
        return Progress(status=record.get("status") or "unknown")
    response = session.get(f"{api_base}{poll_endpoint}", timeout=timeout)
    if response.status_code >= 400:
        return Progress(
            status="error",
            error=f"{response.status_code} {response.text[:300]}",
        )
    return normalize_progress(response.json())


def poll_once(
    session: requests.Session,
    *,
    api_base: str,
    records: list[dict[str, str]],
    timeout: float,
) -> list[tuple[dict[str, str], Progress]]:
    return [
        (
            record,
            poll_record(
                session,
                api_base=api_base,
                record=record,
                timeout=timeout,
            ),
        )
        for record in records
    ]


def print_snapshot(snapshot: list[tuple[dict[str, str], Progress]]) -> None:
    status_counts: dict[str, int] = {}
    rows_total = rows_done = 0
    images_total = images_done = images_failed = errors_count = 0
    for record, progress in snapshot:
        status_counts[progress.status] = status_counts.get(progress.status, 0) + 1
        rows_total += progress.rows_total
        rows_done += progress.rows_done
        images_total += progress.images_total
        images_done += progress.images_done
        images_failed += progress.images_failed
        errors_count += progress.errors_count
        print(
            f"{record.get('filename', '-')}: {progress.status} "
            f"rows={progress.rows_done}/{progress.rows_total} "
            f"images={progress.images_done}/{progress.images_total} "
            f"failed_images={progress.images_failed} "
            f"errors={progress.errors_count} {progress.error[:120]}"
        )

    print("Summary:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print(f"  rows: {rows_done}/{rows_total}")
    print(f"  images: {images_done}/{images_total} failed={images_failed}")
    print(f"  errors: {errors_count}")


def is_terminal(progress: Progress) -> bool:
    return progress.status in SUCCESS_STATUSES | FAILURE_STATUSES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll saved full import jobs.")
    parser.add_argument("--jobs-file", type=Path, required=True)
    parser.add_argument("--domain")
    parser.add_argument("--api-base")
    parser.add_argument("--phone", default=DEFAULT_PHONE)
    parser.add_argument("--code", default=DEFAULT_CODE)
    parser.add_argument("--auth-timeout", type=float, default=30.0)
    parser.add_argument("--poll-timeout", type=float, default=60.0)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--max-wait", type=float, default=0.0)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    api_base = normalize_api_base(domain=args.domain, api_base=args.api_base)
    records = read_jobs(args.jobs_file.expanduser())
    session = requests.Session()
    login(
        session,
        api_base=api_base,
        phone=args.phone,
        code=args.code,
        timeout=args.auth_timeout,
    )

    deadline = time.monotonic() + args.max_wait if args.max_wait else None
    while True:
        snapshot = poll_once(
            session,
            api_base=api_base,
            records=records,
            timeout=args.poll_timeout,
        )
        print_snapshot(snapshot)
        if not args.watch:
            return 0
        if all(is_terminal(progress) for _, progress in snapshot):
            return 0
        if deadline is not None and time.monotonic() >= deadline:
            return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
