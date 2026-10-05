"""HTTP schemas for the citizenship reference."""
from pydantic import BaseModel


class CitizenshipItem(BaseModel):
    id: int
    code2: str
    code3: str
    citizenship_name: str


class CitizenshipListResponse(BaseModel):
    items: list[CitizenshipItem]
