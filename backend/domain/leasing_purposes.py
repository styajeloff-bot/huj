"""Lossless purpose values shared by vehicle and equipment application lines."""
from __future__ import annotations


def selected_purposes(
    purposes: list[str] | None, legacy: str | None = None,
    other_comment: str | None = None,
) -> list[str]:
    """An explicit empty list clears selection; a missing list retains one legacy value."""
    values = purposes if purposes is not None else ([legacy] if legacy else [])
    return list(dict.fromkeys(
        value for raw in values
        if (value := ((other_comment or "").strip() if raw == "other" and other_comment is not None else raw.strip()))
    ))
