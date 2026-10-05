"""Use-case: upload and persist XML accounting reports."""

from __future__ import annotations

import uuid
import uuid as _uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.object_storage import ObjectStorage
from domain.services.xml_accounting import parse_xml
from domain.services.xml_accounting.models import ParsedReport
from infrastructure.repositories import accounting_report_repository as repo
from infrastructure.repositories import documents_repository as docs_repo


async def upload_xml(
    session: AsyncSession,
    xml_bytes: bytes,
    filename: str,
    storage: ObjectStorage,
    company_id: uuid.UUID,
    application_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Parse an uploaded 1C XML accounting file and persist all forms.

    Also stores the raw XML file in object storage and creates a
    ``documents`` row so the LC cabinet can download it later.

    Returns a summary dict with INN, year, period, per-form counts and
    the created ``document_id``.
    """
    # Parse XML (accepts str or bytes)
    reports: list[ParsedReport] = parse_xml(xml_bytes)

    if not reports:
        return {
            "inn": None,
            "year": None,
            "period": None,
            "period_name": None,
            "forms": [],
            "total_rows": 0,
            "document_id": None,
        }

    # All reports in a single file share the same metadata
    meta = reports[0].metadata
    inn = meta.inn
    year = meta.report_year
    period = meta.period_code
    period_name = meta.period_name

    forms: list[dict[str, Any]] = []
    total_rows = 0

    for report in reports:
        # Convert ParsedRow dataclasses to plain dicts and inject metadata
        rows: list[dict[str, Any]] = []
        for parsed_row in report.rows:
            row_dict: dict[str, Any] = {
                "line_code": parsed_row.line_code,
                "line_name": parsed_row.line_name,
                "amount": parsed_row.amount,
                "amount_prev": parsed_row.amount_prev,
                "amount_before_prev": parsed_row.amount_before_prev,
                "component_code": parsed_row.component_code,
                "component_name": parsed_row.component_name,
                "tax_amount": parsed_row.tax_amount,
                "total_tax_payable": parsed_row.total_tax_payable,
                "total_deductions": parsed_row.total_deductions,
                "total_recovered": parsed_row.total_recovered,
                "xml_raw": parsed_row.xml_raw,
                # Metadata shared across all rows of this report
                "company_kpp": meta.kpp,
                "company_name": meta.company_name,
                "period_name": period_name,
                "okei_code": meta.okei_code,
            }
            rows.append(row_dict)

        report_type = report.metadata.okud  # e.g. "0710001"
        # Map OKUD to our internal type for routing
        okud_to_type = {
            "0710001": "balance_sheet",
            "0710002": "financial_result",
            "0710004": "capital_changes",
            "0710005": "cash_flow",
            "1151001": "nds_declaration",
        }
        form_type = okud_to_type.get(report_type, report_type)

        if form_type == "balance_sheet":
            await repo.save_balance_sheet(session, rows, inn, year, period)
        elif form_type == "financial_result":
            await repo.save_financial_result(session, rows, inn, year, period)
        elif form_type == "cash_flow":
            await repo.save_cash_flow(session, rows, inn, year, period)
        elif form_type == "capital_changes":
            await repo.save_capital_changes(session, rows, inn, year, period)
        elif form_type == "nds_declaration":
            await repo.save_nds_declaration(session, rows, inn, year, period)

        forms.append(
            {
                "type": form_type,
                "okud": report.metadata.okud,
                "name": report.metadata.period_name,
                "rows_count": len(rows),
            }
        )
        total_rows += len(rows)

    # ------------------------------------------------------------------
    # Store the raw XML file so the LC cabinet can download it later
    # ------------------------------------------------------------------
    s3_key = f"accounting-xml/{_uuid.uuid4()}/{filename}"
    await storage.put(s3_key, xml_bytes, "application/xml")

    doc_id = await docs_repo.create_document(
        session,
        company_id=company_id,
        document_type="accounting_xml",
        file_name=filename,
        s3_key=s3_key,
        file_size=len(xml_bytes),
        related_application_id=application_id,
        status="uploaded",
        review_status="approved",
    )

    if application_id is not None:
        await docs_repo.link_to_application(
            session, document_id=doc_id, application_id=application_id
        )

    return {
        "inn": inn,
        "year": year,
        "period": period,
        "period_name": period_name,
        "forms": forms,
        "total_rows": total_rows,
        "document_id": doc_id,
    }
