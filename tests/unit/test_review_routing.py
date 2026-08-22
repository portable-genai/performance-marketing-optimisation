"""R8 routing: an escalated performance report is routed to Hrz7 via the shared review-kit.

Every performance report requires human review (P-06), so rule R8 says it MUST be handed to the
Hrz7 maker-checker console rather than left as a boolean. These tests prove the producer half of
that loop end-to-end against the offline local router (an in-memory outbox), that the verified
tenant (C2) is carried on the wire, and the redact-before-wire boundary so no stray contact
identifier reaches the console. Fictional data only.
"""

from __future__ import annotations

import pytest

from performance_marketing.adapters._review_payload import report_to_review
from performance_marketing.adapters.local.review_router import LocalReviewRouter
from performance_marketing.config import Container, Settings
from performance_marketing.domain.models import (
    BudgetPlan,
    BudgetShift,
    Channel,
    Citation,
    Market,
    PerformanceReport,
    ReportRequest,
    Severity,
    ShiftDirection,
    SourceType,
    Vertical,
)
from performance_marketing.domain.services import PerformanceReportService

ACTOR = "lead@marketing.test"
TENANT = "demo-bank"


def _service(container: Container, router: LocalReviewRouter | None) -> PerformanceReportService:
    return PerformanceReportService(
        metrics=container.metrics,
        ad_platform=container.ad_platform,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        review_router=router,
    )


def test_build_report_routes_escalated_report_to_outbox(local_container: Container):
    """A completed report enqueues exactly one review carrying the verified tenant (R8 / C2)."""
    router = LocalReviewRouter(Settings())
    service = _service(local_container, router)
    assert not router.outbox.pending()

    request = ReportRequest(
        account_id="acct-sg-banking", market=Market.SG, vertical=Vertical.BANKING
    )
    report = service.build_report(request, actor=ACTOR, tenant=TENANT)
    assert report.requires_human_review

    pending = router.outbox.pending()
    assert len(pending) == 1, "the escalated report must be routed to Hrz7 exactly once"
    review = pending[0].review
    assert review.action == "performance_report:build"
    assert review.case_ref == report.id
    assert review.maker == ACTOR
    assert review.tenant == TENANT, "the wire payload must carry the verified tenant, not the body"


def _high_severity_report_with_pii() -> PerformanceReport:
    # A citation snippet carrying a synthetic contact email: it must be masked before the wire.
    cite = Citation(
        source_id="metric-1",
        source_type=SourceType.METRICS,
        title="Search channel export",
        snippet="Owner contact analyst@example.test flagged the spend spike.",
    )
    shift = BudgetShift(
        channel=Channel.SEARCH,
        direction=ShiftDirection.DECREASE,
        current_budget=1000.0,
        proposed_budget=600.0,
        delta=-400.0,
        severity=Severity.HIGH,
        citations=(cite,),
    )
    plan = BudgetPlan(
        market=Market.SG, vertical=Vertical.BANKING, shifts=(shift,), total_budget=1000.0
    )
    return PerformanceReport(
        id="report-SG-banking-acct-sg-banking",
        account_id="acct-sg-banking",
        market=Market.SG,
        vertical=Vertical.BANKING,
        summary="Contact analyst@example.test regarding the material search cut.",
        budget_plan=plan,
        citations=(cite,),
    )


def test_payload_is_redacted_and_carries_tenant_and_severity():
    """The wire payload masks identifiers, carries the tenant, and maps the signal (R1 / R8)."""
    review = report_to_review(_high_severity_report_with_pii(), maker=ACTOR, tenant=TENANT)

    assert review.tenant == TENANT
    assert review.severity == "high"
    assert review.required_approvals == 2, "a HIGH-signal report warrants dual control"
    # No raw contact identifier survives into the payload the console receives.
    assert "analyst@example.test" not in review.summary
    for citation in review.citations:
        assert "analyst@example.test" not in citation.snippet
    assert any(c.title == "Search channel export" for c in review.citations)


def test_medium_report_needs_single_checker():
    """With no HIGH+ signal the report floors at medium severity and single-control (R8)."""
    report = PerformanceReport(
        id="report-SG-banking-acct-sg-banking",
        account_id="acct-sg-banking",
        market=Market.SG,
        vertical=Vertical.BANKING,
        summary="Routine report.",
    )
    review = report_to_review(report, maker=ACTOR, tenant=TENANT)
    assert review.severity == "medium"
    assert review.required_approvals == 1


def test_no_router_still_builds_report(local_container: Container):
    """Routing is optional: with no router bound, a report is still built and review-gated."""
    service = _service(local_container, None)
    request = ReportRequest(
        account_id="acct-sg-banking", market=Market.SG, vertical=Vertical.BANKING
    )
    report = service.build_report(request, actor=ACTOR, tenant=TENANT)
    assert report.requires_human_review


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
