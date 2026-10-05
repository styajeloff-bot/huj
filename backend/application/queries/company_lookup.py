"""Company lookup query and handler."""
from dataclasses import dataclass

from domain.services.company_lookup import CompanyLookupProvider
from domain.values import CompanyInfo


@dataclass
class SearchCompanyQuery:
    query: str
    limit: int = 10


async def handle_search_company(
    query: SearchCompanyQuery,
    provider: CompanyLookupProvider,
) -> list[CompanyInfo]:
    text = query.query.strip()
    if len(text) < 2:
        return []
    return await provider.search(text, query.limit)
