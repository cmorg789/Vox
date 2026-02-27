"""Validator factories for use with ``Annotated[..., AfterValidator(...)]``.

These check values against the runtime ``limits`` singleton so that
admin-adjusted limits take effect without restarting the server.
"""

from __future__ import annotations


def _limits():
    """Lazy import to avoid circular dependency at module level."""
    from vox.config import config
    return config.limits


def str_limit(*, min_attr: str | None = None, max_attr: str | None = None):
    """Returns a callable for AfterValidator that checks string length against limits.<attr>."""
    def _validate(v: str | None) -> str | None:
        if v is None:
            return v
        lim = _limits()
        if min_attr and len(v) < getattr(lim, min_attr):
            raise ValueError(f"String should have at least {getattr(lim, min_attr)} character(s)")
        if max_attr and len(v) > getattr(lim, max_attr):
            raise ValueError(f"String should have at most {getattr(lim, max_attr)} character(s)")
        return v
    return _validate


def int_limit(*, ge: int | None = None, max_attr: str | None = None):
    """For numeric bounds -- ge is a fixed floor, max_attr is runtime-configurable ceiling."""
    def _validate(v: int | None) -> int | None:
        if v is None:
            return v
        lim = _limits()
        if ge is not None and v < ge:
            raise ValueError(f"Input should be greater than or equal to {ge}")
        if max_attr and v > getattr(lim, max_attr):
            raise ValueError(f"Input should be less than or equal to {getattr(lim, max_attr)}")
        return v
    return _validate


def check_mime(mime: str, allowlist: str) -> bool:
    """Check if a MIME type matches a comma-separated allowlist (supports type/* and */* wildcards)."""
    allowed = [s.strip() for s in allowlist.split(",") if s.strip()]
    for pattern in allowed:
        if pattern == "*/*":
            return True
        if pattern == mime:
            return True
        if pattern.endswith("/*") and mime.startswith(pattern[:-1]):
            return True
    return False


def list_limit(*, max_attr: str):
    """For list/array length constraints."""
    def _validate(v: list) -> list:
        lim = _limits()
        if v is not None and len(v) > getattr(lim, max_attr):
            raise ValueError(f"List should have at most {getattr(lim, max_attr)} item(s)")
        return v
    return _validate
