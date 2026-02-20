"""SDK exception hierarchy."""

from __future__ import annotations

from typing import Any

import httpx

from vox_sdk.models.errors import ErrorCode, ErrorResponse


class VoxHTTPError(Exception):
    """Raised when the Vox API returns a non-2xx response."""

    def __init__(
        self,
        status: int,
        error: ErrorResponse | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.response = response
        code = error.code.value if error else "UNKNOWN"
        msg = error.message if error else f"HTTP {status}"
        super().__init__(f"[{status}] {code}: {msg}")

    @classmethod
    def from_response(cls, response: httpx.Response) -> VoxHTTPError:
        """Build from an httpx response, attempting to parse the error body."""
        error: ErrorResponse | None = None
        try:
            body = response.json()
            if "error" in body:
                error = ErrorResponse.model_validate(body["error"])
        except Exception:
            pass
        return cls(status=response.status_code, error=error, response=response)

    @property
    def code(self) -> ErrorCode | None:
        return self.error.code if self.error else None

    @property
    def retry_after_ms(self) -> int | None:
        if self.error:
            return self.error.retry_after_ms
        return None


# Close codes that allow resume
_RESUMABLE_CODES = {4007, 4008}
# Close codes that allow reconnect (new identify)
_RECONNECTABLE_CODES = {4000, 4001, 4002, 4006, 4007, 4008, 4009, 4010, 4011}


class VoxNetworkError(Exception):
    """Raised when a transport-level error occurs (connection refused, timeout, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class VoxGatewayError(Exception):
    """Raised when the gateway connection is closed unexpectedly."""

    def __init__(self, code: int, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"Gateway closed [{code}]: {reason}")

    @property
    def can_resume(self) -> bool:
        """Whether the client should attempt to resume with its session."""
        return self.code in _RESUMABLE_CODES

    @property
    def can_reconnect(self) -> bool:
        """Whether the client should reconnect with a fresh identify."""
        return self.code in _RECONNECTABLE_CODES
