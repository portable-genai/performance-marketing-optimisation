"""GCP integration smoke (``-m integration``) — live cloud, opt-in.

These are deselected by default (``pytest -m 'not integration'``) and only run when live
Google Cloud credentials and the ``[gcp]`` extra are present. They exercise the managed
stack end to end: a BigQuery-backed metrics read, a Gemini narration and the Gen AI eval
gate. CI does not run these; they are a deploy-time check.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def test_gcp_report_smoke():
    from performance_marketing.config import Settings, build_container
    from performance_marketing.domain.models import Market, ReportRequest, Vertical
    from performance_marketing.domain.services import PerformanceReportService

    settings = Settings.load("config/settings.yaml")
    container = build_container(settings)
    service = PerformanceReportService(
        metrics=container.metrics,
        ad_platform=container.ad_platform,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
    )
    request = ReportRequest(
        account_id="acct-sg-banking", market=Market.SG, vertical=Vertical.BANKING
    )
    report = service.build_report(request, actor="integration-test", tenant="demo-bank")
    assert report.requires_human_review is True
