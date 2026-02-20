"""Unit tests for error classes."""

from __future__ import annotations

import json

import httpx
import pytest

from vox_sdk.errors import VoxHTTPError, VoxGatewayError, VoxNetworkError, _RESUMABLE_CODES, _RECONNECTABLE_CODES
from vox_sdk.models.errors import ErrorCode


class TestVoxHTTPError:
    def test_from_response(self):
        """Build VoxHTTPError.from_response() from a mock httpx response."""
        response = httpx.Response(
            403,
            json={"error": {"code": "FORBIDDEN", "message": "Not allowed"}},
        )
        err = VoxHTTPError.from_response(response)
        assert err.status == 403
        assert err.code == ErrorCode.FORBIDDEN
        assert err.error is not None
        assert err.error.message == "Not allowed"
        assert err.response is response

    def test_from_response_no_body(self):
        """Handle non-JSON error body gracefully."""
        response = httpx.Response(500, text="Internal Server Error")
        err = VoxHTTPError.from_response(response)
        assert err.status == 500
        assert err.error is None
        assert err.code is None

    def test_properties(self):
        """Verify .code, .retry_after_ms, .status."""
        response = httpx.Response(
            429,
            json={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": "Slow down",
                    "retry_after_ms": 5000,
                }
            },
        )
        err = VoxHTTPError.from_response(response)
        assert err.status == 429
        assert err.code == ErrorCode.RATE_LIMITED
        assert err.retry_after_ms == 5000

    def test_str(self):
        """Verify string representation."""
        response = httpx.Response(
            404,
            json={"error": {"code": "NOT_FOUND", "message": "Resource not found"}},
        )
        err = VoxHTTPError.from_response(response)
        s = str(err)
        assert "404" in s
        assert "NOT_FOUND" in s
        assert "Resource not found" in s

    def test_no_error_properties(self):
        """When error is None, code and retry_after_ms return None."""
        err = VoxHTTPError(status=500)
        assert err.code is None
        assert err.retry_after_ms is None


class TestVoxGatewayError:
    def test_all_codes(self):
        """Verify can_resume/can_reconnect for representative codes."""
        # Resumable (should also be reconnectable)
        for code in (4007, 4008):
            err = VoxGatewayError(code, "test")
            assert err.can_resume is True, f"Code {code} should be resumable"
            assert err.can_reconnect is True, f"Code {code} should be reconnectable"

        # Reconnectable only (not resumable)
        reconnect_only = {4000, 4001, 4002, 4006, 4009, 4010, 4011}
        for code in reconnect_only - _RESUMABLE_CODES:
            err = VoxGatewayError(code, "test")
            assert err.can_resume is False, f"Code {code} should not be resumable"
            assert err.can_reconnect is True, f"Code {code} should be reconnectable"

        # Fatal (neither resumable nor reconnectable)
        for code in (4003, 4004, 4005):
            err = VoxGatewayError(code, "test")
            assert err.can_resume is False, f"Code {code} should not be resumable"
            assert err.can_reconnect is False, f"Code {code} should not be reconnectable"

    def test_str(self):
        """Verify string representation."""
        err = VoxGatewayError(4004, "AUTH_FAILED")
        s = str(err)
        assert "4004" in s
        assert "AUTH_FAILED" in s


class TestVoxNetworkError:
    def test_basic(self):
        err = VoxNetworkError("Connection refused")
        assert str(err) == "Connection refused"
        assert isinstance(err, Exception)

    def test_as_cause(self):
        """VoxNetworkError can chain from a transport error."""
        original = ConnectionError("refused")
        err = VoxNetworkError("Connection refused")
        err.__cause__ = original
        assert err.__cause__ is original
