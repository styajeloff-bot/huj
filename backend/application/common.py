from typing import Any


def _isoformat(val: Any) -> str | None:
    if val is None:
        return None
    formatter = getattr(val, "isoformat", None)
    return formatter() if callable(formatter) else str(val)
