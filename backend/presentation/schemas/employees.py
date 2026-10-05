"""Pydantic schemas for the Employees API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmployeeOut(BaseModel):
    """Employee representation returned by API endpoints."""

    user_id: str
    name: str | None
    phone: str
    additional_phone: str | None = None
    company_id: str
    company_name: str
    role: str
    sub_role: str | None = None
    position_id: str | None = None
    position_name: str | None = None
    can_view_applications: bool
    can_create_applications: bool
    can_create_employees: bool = False
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    can_edit: bool = True

    model_config = ConfigDict(populate_by_name=True)


EmployeeRole = Literal[
    "dealer", "distributor", "client", "leasing_company", "carcraft_employee"
]


class EmployeeListObject(BaseModel):
    id: UUID
    name: str


class EmployeeListOut(BaseModel):
    user_id: UUID
    name: str | None
    phone: str
    additional_phone: str | None = None
    company_id: UUID | None
    company_name: str | None
    role: str
    sub_role: str | None = None
    position_id: UUID | None = None
    position_name: str | None = None
    can_view_applications: bool
    can_create_applications: bool
    can_create_employees: bool = False
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    can_edit: bool = True

    company_role: str | None
    row_type: Literal["company", "system"]
    user_company_id: UUID | None
    brands: list[EmployeeListObject] = Field(default_factory=list)
    warehouses: list[EmployeeListObject] = Field(default_factory=list)
    distributors: list[EmployeeListObject] = Field(default_factory=list)


class EmployeeFilterOptionsResponse(BaseModel):
    companies: list[EmployeeListObject]
    dealers: list[EmployeeListObject]
    distributors: list[EmployeeListObject]
    brands: list[EmployeeListObject]
    warehouses: list[EmployeeListObject]


class EmployeesListResponse(BaseModel):
    """Paginated list of employees."""

    items: list[EmployeeListOut]
    total: int
    page: int
    per_page: int


class CreateEmployeeRequest(BaseModel):
    """Payload to create or link an employee to a company."""

    name: str = Field(..., min_length=1, description="ФИО сотрудника")
    phone: str = Field(..., min_length=1, description="Номер телефона сотрудника")
    additional_phone: str | None = Field(
        default=None, description="Дополнительный номер телефона сотрудника"
    )
    company_id: UUID = Field(..., description="ID компании")
    role: Literal["client", "dealer", "distributor", "leasing_company"] = Field(
        ..., description="Бизнес-роль сотрудника в компании"
    )
    position_id: UUID | None = Field(
        default=None, description="ID должности из справочника (dealer / distributor)"
    )
    can_view_applications: bool = Field(
        default=True, description="Право на просмотр заявок"
    )
    can_create_applications: bool = Field(
        default=False, description="Право на создание заявок"
    )
    can_create_employees: bool = Field(
        default=False, description="Право создавать и настраивать сотрудников"
    )
    is_active: bool = Field(default=True, description="Флаг активности связи")


class UpdateEmployeeRequest(BaseModel):
    """Payload to update an employee in a company."""

    name: str | None = Field(default=None, description="ФИО сотрудника")
    phone: str | None = Field(default=None, description="Номер телефона сотрудника")
    additional_phone: str | None = Field(
        default=None, description="Дополнительный номер телефона сотрудника"
    )
    role: Literal["client", "dealer", "distributor", "leasing_company"] = Field(
        ..., description="Бизнес-роль сотрудника в компании"
    )
    position_id: UUID | None = Field(
        default=None, description="ID должности из справочника"
    )
    can_view_applications: bool = Field(
        default=True, description="Право на просмотр заявок"
    )
    can_create_applications: bool = Field(
        default=False, description="Право на создание заявок"
    )
    can_create_employees: bool = Field(
        default=False, description="Право создавать и настраивать сотрудников"
    )
    is_active: bool = Field(default=True, description="Флаг активности связи")


class DeactivateEmployeeResponse(BaseModel):
    """Response returned upon soft-deactivation of an employee."""

    success: bool = True
    message: str = "Сотрудник деактивирован"


class AccessRuleItem(BaseModel):
    """Individual object-level access rule item."""

    id: UUID | None = None
    access_object: str = Field(
        ...,
        description="Тип объекта: warehouse, brand, dealer, dealer_warehouse, application_creator",
    )
    access_type: str = Field(
        ...,
        description="Режим доступа: all, selected, except_selected, none",
    )
    object_id: str | None = Field(
        default=None, description="ID объекта (NULL для all и none)"
    )
    object_name: str | None = Field(default=None, description="Наименование объекта")
    is_active: bool = True

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def normalize_rule_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "access_object" not in data and "object_type" in data:
                data["access_object"] = data["object_type"]
            if "access_type" not in data and "access_mode" in data:
                data["access_type"] = data["access_mode"]
            elif "access_type" not in data and "mode" in data:
                data["access_type"] = data["mode"]
        return data


class SectionAccessItem(BaseModel):
    """Section visibility item."""

    section_code: str = Field(..., description="Код раздела личного кабинета")
    can_view: bool = Field(..., description="Видимость/доступ к разделу")

    model_config = ConfigDict(extra="ignore")


class EmployeeAccessSettingsOut(BaseModel):
    """Employee personal access settings response."""

    user_company_id: UUID
    user_id: UUID | None = None
    company_id: UUID | None = None
    can_create_employees: bool = False
    additional_phone: str | None = None
    rules: list[AccessRuleItem] = Field(default_factory=list)
    access_rules: list[AccessRuleItem] = Field(default_factory=list)
    sections: dict[str, bool] = Field(default_factory=dict)
    section_access: list[SectionAccessItem] = Field(default_factory=list)
    available_objects: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    available_sections: list[str] = Field(default_factory=list)
    granter_can_create_employees: bool = False
    can_edit: bool = True

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="after")
    def sync_aliases(self) -> EmployeeAccessSettingsOut:
        if not self.access_rules and self.rules:
            self.access_rules = list(self.rules)
        elif not self.rules and self.access_rules:
            self.rules = list(self.access_rules)

        if not self.section_access and self.sections:
            self.section_access = [
                SectionAccessItem(section_code=code, can_view=val)
                for code, val in self.sections.items()
            ]
        elif not self.sections and self.section_access:
            self.sections = {
                item.section_code: item.can_view for item in self.section_access
            }

        return self


class UpdateEmployeeAccessSettingsRequest(BaseModel):
    """Payload to update an employee's personal access settings."""

    additional_phone: str | None = None
    can_create_employees: bool = False
    rules: list[AccessRuleItem] = Field(default_factory=list)
    access_rules: list[AccessRuleItem] | None = None
    sections: dict[str, bool] = Field(default_factory=dict)
    section_access: list[SectionAccessItem] | None = None

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "rules" not in data and "access_rules" in data:
                data["rules"] = data["access_rules"]
            if (
                "sections" not in data or not data["sections"]
            ) and "section_access" in data:
                sa = data["section_access"]
                if isinstance(sa, list):
                    data["sections"] = {
                        item["section_code"]
                        if isinstance(item, dict)
                        else item.section_code: item.get("can_view", False)
                        if isinstance(item, dict)
                        else getattr(item, "can_view", False)
                        for item in sa
                        if (isinstance(item, dict) and "section_code" in item)
                        or hasattr(item, "section_code")
                    }
        return data


class LookupItem(BaseModel):
    """Search/lookup item returned for selectors."""

    id: str
    name: str
    address: str | None = None
    description: str | None = None
    phone: str | None = None
    inn: str | None = None
    company_id: str | None = None
    company_name: str | None = None

    model_config = ConfigDict(extra="ignore")


class LookupResponse(BaseModel):
    """Lookup search response."""

    items: list[LookupItem] = Field(default_factory=list)
    total: int = 0

    model_config = ConfigDict(extra="ignore")


EmployeeLookupItem = LookupItem
EmployeeLookupResponse = LookupResponse
