"""Every citation the engines attach to a report must reach the audit view.

Five parts of a :class:`PerformanceReport` carry their own provenance: the per-channel
efficiency figures, the per-channel attribution credit, each budget shift, each A/B result
and each anomaly. The audit-first renderer used to print citations for only three of them,
so the attribution-journey and A/B-experiment sources were computed, serialized, and then
silently discarded at the last step. An audit view that shows a recommendation without the
evidence behind it is the one thing this product must not do, so this pins the whole set.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

from performance_marketing.domain.models import (
    AbResult,
    AbVerdict,
    Anomaly,
    AnomalyKind,
    AnomalyReport,
    AttributionModel,
    AttributionView,
    BudgetPlan,
    BudgetShift,
    Channel,
    ChannelAttribution,
    ChannelEfficiency,
    Citation,
    EfficiencyReport,
    Market,
    PerformanceReport,
    Severity,
    ShiftDirection,
    SourceType,
    Vertical,
)
from performance_marketing.domain.serialization import to_jsonable

_RENDERER = Path(__file__).resolve().parents[2] / "scripts" / "render_report_ui.py"


def _renderer() -> Any:
    """Import the dependency-free renderer script by path (it is not a package module)."""
    if "render_report_ui" in sys.modules:
        return sys.modules["render_report_ui"]
    spec = importlib.util.spec_from_file_location("render_report_ui", _RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["render_report_ui"] = module
    spec.loader.exec_module(module)
    return module


def _cite(source_id: str) -> tuple[Citation, ...]:
    return (
        Citation(
            source_id=source_id,
            source_type=SourceType.INTERNAL,
            title=f"Evidence {source_id}",
        ),
    )


def _report() -> PerformanceReport:
    """One report whose every citation-bearing part carries a distinct source."""
    efficiency = EfficiencyReport(
        market=Market.SG,
        vertical=Vertical.BANKING,
        channels=(
            ChannelEfficiency(
                channel=Channel.SEARCH,
                spend=1000.0,
                revenue=4000.0,
                conversions=100.0,
                roas=4.0,
                cac=10.0,
                citations=_cite("efficiency-search"),
            ),
        ),
        blended_roas=4.0,
        blended_cac=10.0,
    )
    attribution = AttributionView(
        model=AttributionModel.LINEAR,
        market=Market.SG,
        vertical=Vertical.BANKING,
        channels=(
            ChannelAttribution(
                channel=Channel.SEARCH,
                attributed_conversions=60.0,
                attributed_revenue=2400.0,
                credit_share=0.6,
                citations=_cite("journey-touchpoint-1"),
            ),
            ChannelAttribution(
                channel=Channel.SOCIAL,
                attributed_conversions=40.0,
                attributed_revenue=1600.0,
                credit_share=0.4,
                citations=_cite("journey-touchpoint-2"),
            ),
        ),
        total_conversions=100.0,
        total_revenue=4000.0,
        journeys_considered=3,
    )
    plan = BudgetPlan(
        market=Market.SG,
        vertical=Vertical.BANKING,
        shifts=(
            BudgetShift(
                channel=Channel.SEARCH,
                direction=ShiftDirection.INCREASE,
                current_budget=1000.0,
                proposed_budget=1200.0,
                delta=200.0,
                severity=Severity.HIGH,
                citations=_cite("budget-rule-1"),
            ),
            # A held channel is not rendered, so its citation is not expected on the page.
            BudgetShift(
                channel=Channel.DISPLAY,
                direction=ShiftDirection.HOLD,
                current_budget=500.0,
                proposed_budget=500.0,
                delta=0.0,
                citations=_cite("budget-rule-held"),
            ),
        ),
        total_budget=1500.0,
    )
    ab_results = (
        AbResult(
            test_id="exp-hero",
            metric="conversion_rate",
            control_rate=0.02,
            variant_rate=0.025,
            absolute_lift=0.005,
            relative_lift=0.25,
            z_score=2.4,
            p_value=0.016,
            significant=True,
            verdict=AbVerdict.SHIP,
            citations=_cite("experiment-hero"),
        ),
        AbResult(
            test_id="exp-copy",
            metric="conversion_rate",
            control_rate=0.02,
            variant_rate=0.021,
            absolute_lift=0.001,
            relative_lift=0.05,
            z_score=0.6,
            p_value=0.55,
            significant=False,
            verdict=AbVerdict.KEEP_RUNNING,
            citations=_cite("experiment-copy"),
        ),
    )
    anomalies = AnomalyReport(
        market=Market.SG,
        vertical=Vertical.BANKING,
        anomalies=(
            Anomaly(
                metric="cac",
                observed_date="2026-08-01",
                value=22.0,
                baseline=10.0,
                deviation=3.9,
                kind=AnomalyKind.SPIKE,
                severity=Severity.HIGH,
                citations=_cite("anomaly-cac"),
            ),
        ),
    )
    return PerformanceReport(
        id="report-test",
        account_id="acct-test",
        market=Market.SG,
        vertical=Vertical.BANKING,
        summary="Obviously fictional synthetic report.",
        attribution=attribution,
        efficiency=efficiency,
        budget_plan=plan,
        ab_results=ab_results,
        anomalies=anomalies,
        citations=tuple(
            c
            for group in (
                _cite("efficiency-search"),
                _cite("journey-touchpoint-1"),
                _cite("journey-touchpoint-2"),
                _cite("budget-rule-1"),
                _cite("experiment-hero"),
                _cite("experiment-copy"),
                _cite("anomaly-cac"),
            )
            for c in group
        ),
    )


def _rendered_source_ids(page: str) -> set[str]:
    return set(re.findall(r"data-citation='([^']*)'", page))


def test_every_rendered_section_shows_its_own_evidence() -> None:
    report = _report()
    page = _renderer().render_report(to_jsonable(report))
    shown = _rendered_source_ids(page)

    expected = {
        "efficiency-search",
        "journey-touchpoint-1",
        "journey-touchpoint-2",
        "budget-rule-1",
        "experiment-hero",
        "experiment-copy",
        "anomaly-cac",
    }
    assert expected <= shown, f"the audit view dropped {sorted(expected - shown)}"


def test_every_live_report_citation_reaches_the_page() -> None:
    """The report's own citation roll-up must be fully accounted for on the page."""
    report = _report()
    page = _renderer().render_report(to_jsonable(report))
    shown = _rendered_source_ids(page)

    live = {c.source_id for c in report.citations}
    assert live, "the fixture must carry citations for this check to mean anything"
    assert live <= shown, f"live citations never reached the served view: {sorted(live - shown)}"


def test_a_held_budget_shift_is_neither_rendered_nor_expected() -> None:
    """The one deliberate omission: a hold is not a recommendation, so it is not shown."""
    page = _renderer().render_report(to_jsonable(_report()))
    assert "budget-rule-held" not in _rendered_source_ids(page)
