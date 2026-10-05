"""Company lookup routes — provider-agnostic external company search."""
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from application.errors import ServiceError, domain_to_http
from application.queries.company_lookup import (
    SearchCompanyQuery,
    handle_search_company,
)
from domain.errors import DomainError
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.services.company_lookup import get_company_lookup_provider
from presentation.schemas.company_lookup import CompanySearchResponse

router = APIRouter()


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get(
    "/search",
    response_model=CompanySearchResponse,
    summary="Поиск компании по названию или ИНН",
    description=(
        "Ищет компанию во внешнем реестре по названию или ИНН. "
        "Возвращает нормализованный список (`items`) — формат не зависит "
        "от конкретного провайдера. Пустой результат — это успешный ответ "
        "с пустым `items`, а не 404."
    ),
)
async def search_company(
    provider: Annotated[
        CompanyLookupProvider, Depends(get_company_lookup_provider)
    ],
    q: str = Query(..., min_length=2, description="Название или ИНН"),
    limit: int = Query(10, ge=1, le=20),
) -> JSONResponse:
    try:
        items = await handle_search_company(
            SearchCompanyQuery(query=q, limit=limit), provider
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(
        content={"items": jsonable_encoder([asdict(i) for i in items])}
    )
