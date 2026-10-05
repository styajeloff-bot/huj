"""Read INNs from a file, resolve them via DaData, and export company info."""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

API_KEY = os.getenv('DADATA_API_KEY')
MAX_CONCURRENCY = 10
CACHE_PATH = Path(__file__).with_name("dadata_inn_cache.json")
CompanyExportRow = tuple[str, str, str, str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Читает файл со списком ИНН по одному на строку, запрашивает DaData "
            "и сохраняет ИНН, название компании и ФИО генерального директора."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Путь к входному txt-файлу со списком ИНН, по одному на строку.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Путь к выходному tsv-файлу.",
    )
    return parser.parse_args()


def _read_inns(path: Path) -> list[str]:
    values: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        inn = line.strip()
        if inn:
            values.append(inn)
    return values


def _manager_name_for_export(company_name: str, manager_name: str) -> str:
    if company_name.startswith("ИП "):
        return company_name.removeprefix("ИП ").strip()
    return manager_name


def _load_cache(path: Path) -> dict[str, CompanyExportRow]:
    if not path.exists():
        return {}

    raw_cache = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_cache, dict):
        return {}

    cache: dict[str, CompanyExportRow] = {}
    for inn, value in raw_cache.items():
        if isinstance(inn, str) and isinstance(value, list) and len(value) == 4:
            cache[inn] = cast('CompanyExportRow', tuple(str(item) for item in value))
    return cache


def _write_cache(path: Path, cache: dict[str, CompanyExportRow]) -> None:
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _resolve_company(
    provider: Any,
    inn: str,
    semaphore: asyncio.Semaphore,
) -> tuple[str, CompanyExportRow]:
    async with semaphore:
        results = await provider.search(inn, limit=1)

    company = results[0] if results else None
    company_name = company.name if company and company.name else ""
    manager_name = company.manager_name if company and company.manager_name else ""
    return inn, (
        company_name,
        _manager_name_for_export(company_name, manager_name),
        company.phone if company and company.phone else "",
        company.email if company and company.email else "",
    )

async def _resolve_rows(inns: list[str]) -> list[tuple[str, str, str, str, str]]:
    from infrastructure.services.company_lookup.dadata import (
        DadataCompanyLookupProvider,
    )

    if API_KEY is None:
        raise RuntimeError("DADATA_API_KEY environment variable is required")
    provider = DadataCompanyLookupProvider(api_key=API_KEY)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    cache = _load_cache(CACHE_PATH)
    unique_inns = list(dict.fromkeys(inns))
    missing_inns = [inn for inn in unique_inns if inn not in cache]
    tasks = [
        asyncio.create_task(_resolve_company(provider, inn, semaphore))
        for inn in missing_inns
    ]
    for task in asyncio.as_completed(tasks):
        inn, row = await task
        cache[inn] = row
        _write_cache(CACHE_PATH, cache)
    return [
        (
            inn,
            cache[inn][0],
            cache[inn][1],
            cache[inn][2],
            cache[inn][3],
        )
        for inn in inns
    ]


def _write_rows(path: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file_obj:
        writer = csv.writer(file_obj, delimiter="\t")
        writer.writerow(
            [
                "ИНН",
                "Название компании",
                "ФИО генерального директора",
                "Телефон",
                "Email",
            ]
        )
        writer.writerows(rows)


async def _main() -> int:
    args = _parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".tsv")

    inns = _read_inns(input_path)
    rows = await _resolve_rows(inns)
    _write_rows(output_path, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
