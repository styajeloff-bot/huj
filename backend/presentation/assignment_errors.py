"""Stable coded error payloads for application assignment endpoints."""

from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from application.errors import ServiceError, domain_to_http
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotOwnedError,
    DealerAssignmentNotAllowedError,
    DealerGroupNotFoundError,
    DealerNotFoundError,
    DomainError,
    EmployeeAssignmentNotAllowedError,
)

_ERROR_CODES: dict[type[Exception], str] = {
    ApplicationNotFoundError: "APPLICATION_NOT_FOUND",
    ApplicationNotOwnedError: "APPLICATION_ACCESS_DENIED",
    DealerGroupNotFoundError: "DEALER_GROUP_NOT_FOUND",
    DealerNotFoundError: "DEALER_NOT_FOUND",
    DealerAssignmentNotAllowedError: "DEALER_ASSIGNMENT_NOT_ALLOWED",
    EmployeeAssignmentNotAllowedError: "EMPLOYEE_ASSIGNMENT_NOT_ALLOWED",
}


def assignment_error_response(
    exc: ServiceError | DomainError,
) -> JSONResponse:
    """Return the task-specific ``detail: {code, message}`` contract."""
    service_error = domain_to_http(exc) if isinstance(exc, DomainError) else exc
    code = _ERROR_CODES.get(type(exc))
    if code is None:
        if service_error.status_code == 403:
            code = "APPLICATION_ACCESS_DENIED"
        elif service_error.status_code == 404:
            code = "ASSIGNMENT_RESOURCE_NOT_FOUND"
        else:
            code = "ASSIGNMENT_INVALID"
    return JSONResponse(
        status_code=service_error.status_code,
        content=jsonable_encoder(
            {
                "detail": {
                    "code": code,
                    "message": str(service_error),
                }
            }
        ),
    )


__all__ = ["assignment_error_response"]
