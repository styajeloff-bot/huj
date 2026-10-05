"""City admin queries."""
from application.queries.cities.list_cities import (
    ListCitiesQuery,
    handle_list_cities,
)

__all__ = [
    "ListCitiesQuery",
    "handle_list_cities",
]
