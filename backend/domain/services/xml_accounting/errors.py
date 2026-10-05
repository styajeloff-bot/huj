"""Exceptions raised by the XML accounting report parser."""
from __future__ import annotations


class XMLAccountingError(Exception):
    """Base class for XML accounting parser errors."""


class UnsupportedReportError(XMLAccountingError):
    """Raised when report KND/OKUD is not in the supported list."""


class XMLValidationError(XMLAccountingError):
    """Raised when XML structure is invalid."""


class MissingRequiredFieldError(XMLAccountingError):
    """Raised when a required field (INN, year, etc.) is missing."""


class NoDataExtractedError(XMLAccountingError):
    """Raised when the parser could not extract any rows from the XML."""
