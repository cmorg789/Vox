"""SDK integration tests for moderation endpoints."""

import pytest

from .conftest import make_sdk_client, register

pytestmark = pytest.mark.anyio


class TestModeration:
    async def test_report_lifecycle(self, app, db):
        """Create report -> list -> get detail -> resolve -> verify status."""
        admin = await make_sdk_client(app)
        target = await make_sdk_client(app)
        try:
            await register(admin, "admin", "password123")
            target_reg = await register(target, "target", "password123")

            # Create a report (any authenticated user can report)
            report = await admin.moderation.create_report(
                target_reg.user_id, "spam", description="Spamming in chat"
            )
            assert report.report_id > 0

            # List reports (admin has VIEW_REPORTS via ADMINISTRATOR)
            reports = await admin.moderation.list_reports()
            assert any(r.report_id == report.report_id for r in reports.items)

            # Get detail
            detail = await admin.moderation.get_report(report.report_id)
            assert detail.report_id == report.report_id
            assert detail.reported_user_id == target_reg.user_id
            assert detail.reason == "spam"
            assert detail.description == "Spamming in chat"
            assert detail.status == "open"

            # Resolve the report
            await admin.moderation.resolve_report(report.report_id, "warn")

            # Verify status changed
            detail = await admin.moderation.get_report(report.report_id)
            assert detail.status == "resolved"
            assert detail.action == "warn"
        finally:
            await admin.close()
            await target.close()

    async def test_audit_log(self, app, db):
        """Perform an action (ban), then query audit log for the entry."""
        admin = await make_sdk_client(app)
        target = await make_sdk_client(app)
        try:
            await register(admin, "admin", "password123")
            target_reg = await register(target, "target", "password123")

            await admin.members.ban(target_reg.user_id, reason="audit test")

            log = await admin.moderation.audit_log()
            assert any(
                e.event_type == "member.ban" and e.target_id == target_reg.user_id
                for e in log.entries
            )
        finally:
            await admin.close()
            await target.close()
