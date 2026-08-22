"""PerformanceReportService — the performance-marketing-optimisation orchestrator.

Owns the full report pipeline and calls only ports plus the deterministic engines. The
deterministic engines (attribution, efficiency, optimisation, significance, anomaly) decide
everything consequential; the LLM only narrates the already-computed result and drafts the
spend-shift rationale. Every consequential output is maker-checker gated: the performance
report always requires human review before any budget shift is executed.

Pipeline (each step wrapped in ``tracer.span``; audited at the end):

    tracer.span("report.build"):
      guardrail.screen(INPUT)                       [blocked -> audit BLOCKED + raise]
      -> ad_platform.account(account_id)             (bid strategies + ROAS/CAC target)
      -> metrics.channel_metrics / journeys / series (BigQuery feeds)
                                                     [all empty -> MetricsEmptyError]
      -> attribution.attribute(journeys, model)      (multi-touch credit split)
      -> efficiency.compute(metrics, target)         (ROAS / CAC vs target)
      -> optimisation.plan(efficiency, budgets)      (budget-neutral reallocation)
      -> significance.evaluate(each experiment)      (two-proportion z-test)
      -> anomaly.detect(metric series)               (robust-z spikes / drops)
      -> llm.generate(summary narrative)             (narration only, over computed result)
      -> assemble PerformanceReport (requires_human_review=True)
      -> guardrail.screen(OUTPUT)                    [blocked -> audit BLOCKED + raise]
      -> audit.record

Defensive throughout: an ad-platform / experiments call that degrades is tolerated, but a
blocked input and a report with no metrics are hard errors so a report is never built on
screened-out or absent data.

Pure domain code: no Google Cloud / ADK / FastAPI imports.
"""

from __future__ import annotations

import contextlib
import json
from contextlib import nullcontext
from typing import Any

from .anomaly_service import AnomalyService
from .attribution_service import AttributionService
from .efficiency_service import EfficiencyService
from .errors import AuthorizationError, GuardrailBlockedError, MetricsEmptyError
from .models import (
    AbResult,
    Account,
    AnomalyReport,
    AttributionView,
    AuditEvent,
    BudgetPlan,
    Citation,
    Decision,
    Direction,
    EfficiencyReport,
    GuardrailVerdict,
    LlmMessage,
    LlmRequest,
    PerformanceReport,
    ReportRequest,
)
from .optimisation_service import OptimisationService, budgets_from_strategies
from .significance_service import SignificanceService

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "used_source_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary"],
}


class PerformanceReportService:
    """Build a cited performance report for an account. Constructor takes explicit ports."""

    def __init__(
        self,
        metrics: Any,
        ad_platform: Any,
        llm: Any,
        guardrail: Any,
        tracer: Any,
        audit: Any,
        attribution: AttributionService | None = None,
        efficiency: EfficiencyService | None = None,
        optimisation: OptimisationService | None = None,
        significance: SignificanceService | None = None,
        anomaly: AnomalyService | None = None,
        review_router: Any = None,
    ) -> None:
        self._metrics = metrics
        self._ad_platform = ad_platform
        self._llm = llm
        self._guardrail = guardrail
        self._tracer = tracer
        self._audit = audit
        # Optional (rule R8): when bound, an escalated report is routed to the Hrz7 maker-checker
        # console after it is audited. Left unset the report still audits ESCALATED, it just is
        # not forwarded to a console.
        self._review_router = review_router
        self._attribution = attribution or AttributionService()
        self._efficiency = efficiency or EfficiencyService()
        self._optimisation = optimisation or OptimisationService()
        self._significance = significance or SignificanceService()
        self._anomaly = anomaly or AnomalyService()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def build_report(self, request: ReportRequest, *, actor: str, tenant: str) -> PerformanceReport:
        with self._span("report.build", market=request.market.value):
            self._guard(request.account_id, Direction.INPUT, actor)

            account = self._ad_platform.account(
                request.account_id, request.market, request.vertical
            )

            # Object-level authorization, fail-closed (C2): an account that belongs to a
            # tenant other than the verified principal's is DENIED before any report is
            # built, ranked, narrated or audited. The requested account_id alone never
            # grants access; the verified tenant must own the account.
            if account.tenant and account.tenant != tenant:
                raise AuthorizationError(
                    f"principal tenant {tenant!r} is not authorized for account "
                    f"{account.id!r} in tenant {account.tenant!r}"
                )
            channel_metrics = self._metrics.channel_metrics(
                request.account_id, request.market, request.vertical, request.lookback_days
            )
            journeys = self._metrics.conversion_journeys(
                request.account_id, request.market, request.vertical, request.lookback_days
            )
            series = self._metrics.metric_series(
                request.account_id, request.market, request.vertical, request.lookback_days
            )
            if not channel_metrics and not journeys:
                raise MetricsEmptyError(
                    "no channel metrics or journeys for the account; a report must be grounded"
                )

            attribution = self._attribution.attribute(
                journeys, request.attribution_model, request.market, request.vertical
            )
            efficiency = self._efficiency.compute(
                channel_metrics, request.market, request.vertical, account.roas_target
            )
            budget_plan = self._optimisation.plan(
                efficiency,
                budgets_from_strategies(account.bid_strategies),
                request.market,
                request.vertical,
            )
            ab_results = self._evaluate_experiments(account)
            anomalies = self._anomaly.detect(series, request.market, request.vertical)

            summary = self._narrate(request, efficiency, budget_plan, actor)
            citations = self._collect_citations(
                attribution, efficiency, budget_plan, ab_results, anomalies
            )
            report = PerformanceReport(
                id=f"report-{request.market.value}-{request.vertical.value}-{request.account_id}",
                account_id=request.account_id,
                market=request.market,
                vertical=request.vertical,
                summary=summary,
                attribution=attribution,
                efficiency=efficiency,
                budget_plan=budget_plan,
                ab_results=ab_results,
                anomalies=anomalies,
                citations=citations,
                requires_human_review=True,
            )
            self._guard(summary, Direction.OUTPUT, actor)
            self._record(report, actor)
            # Route the escalation to Hrz7 (rule R8). A performance report always requires human
            # review, so it is handed to the maker-checker console rather than terminating in a
            # boolean; the adapter redacts before the wire and carries the verified tenant (C2).
            # Best-effort: a console outage must not fail an already-assembled, already-audited
            # report (the audit ESCALATED record is the durable escalation of record, and the
            # outbox path retries).
            if self._review_router is not None and report.requires_human_review:
                with contextlib.suppress(Exception):
                    self._review_router.route(report, maker=actor, tenant=tenant)
            return report

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _evaluate_experiments(self, account: Account) -> tuple[AbResult, ...]:
        try:
            experiments = self._ad_platform.experiments(
                account.id, account.market, account.vertical
            )
        except Exception:  # noqa: BLE001 - experiments are best-effort enrichment
            return ()
        return tuple(self._significance.evaluate(t) for t in experiments)

    @staticmethod
    def _collect_citations(
        attribution: AttributionView,
        efficiency: EfficiencyReport,
        budget_plan: BudgetPlan,
        ab_results: tuple[AbResult, ...],
        anomalies: AnomalyReport,
    ) -> tuple[Citation, ...]:
        raw: list[Citation] = []
        for attr_ch in attribution.channels:
            raw.extend(attr_ch.citations)
        for eff_ch in efficiency.channels:
            raw.extend(eff_ch.citations)
        for shift in budget_plan.shifts:
            raw.extend(shift.citations)
        for result in ab_results:
            raw.extend(result.citations)
        for anomaly in anomalies.anomalies:
            raw.extend(anomaly.citations)
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for cit in raw:
            key = (cit.source_id, cit.page)
            if key not in seen:
                seen.add(key)
                out.append(cit)
        return tuple(out)

    # ------------------------------------------------------------------ #
    # LLM narration (narration only; never decides the numbers)
    # ------------------------------------------------------------------ #
    def _narrate(
        self,
        request: ReportRequest,
        efficiency: EfficiencyReport,
        budget_plan: BudgetPlan,
        actor: str,
    ) -> str:
        evidence = self._render_evidence(efficiency, budget_plan)
        prompt = (
            f"Write a concise performance-marketing-optimisation summary for account "
            f"'{request.account_id}' in market {request.market.value}, vertical "
            f"{request.vertical.value}. Use ONLY the computed figures below; cite the source "
            f"ids you used.\n\nFIGURES:\n{evidence}"
        )
        response = self._llm.generate(
            LlmRequest(
                messages=(LlmMessage(role="user", content=prompt),),
                response_schema=_SUMMARY_SCHEMA,
            )
        )
        return self._extract_summary(response.text, request)

    @staticmethod
    def _render_evidence(efficiency: EfficiencyReport, budget_plan: BudgetPlan) -> str:
        lines: list[str] = [
            f"blended ROAS {efficiency.blended_roas:.2f}, blended CAC {efficiency.blended_cac:.2f}"
        ]
        for c in efficiency.channels:
            ids = " ".join(f"[{cit.source_id} p.{cit.page or 1}]" for cit in c.citations)
            lines.append(
                f"{ids} {c.channel.value}: spend {c.spend:.2f}, ROAS {c.roas:.2f}, CAC {c.cac:.2f}"
            )
        for s in budget_plan.material_shifts:
            lines.append(
                f"shift {s.channel.value}: {s.direction.value} {s.delta:+.2f} "
                f"({s.current_budget:.2f} -> {s.proposed_budget:.2f})"
            )
        return "\n".join(lines) or "(no figures)"

    @staticmethod
    def _extract_summary(text: str, request: ReportRequest) -> str:
        try:
            obj = json.loads(text)
            summary = obj.get("summary", "")
            if isinstance(summary, str) and summary:
                return summary
        except (json.JSONDecodeError, AttributeError):
            pass
        return (
            f"Performance report for {request.account_id} in {request.market.value} "
            f"({request.vertical.value})."
        )

    # ------------------------------------------------------------------ #
    # Cross-cutting: guardrail, tracing, audit
    # ------------------------------------------------------------------ #
    def _guard(self, text: str, direction: Direction, actor: str) -> None:
        verdict: GuardrailVerdict = self._guardrail.screen(text, direction)
        if not verdict.allowed:
            self._audit.record(
                AuditEvent(
                    action="performance_report",
                    actor=actor,
                    decision=Decision.BLOCKED,
                    prompt=text if direction is Direction.INPUT else "",
                    response=text if direction is Direction.OUTPUT else "",
                    metadata={"reason": verdict.reason, "direction": direction.value},
                )
            )
            raise GuardrailBlockedError(verdict.reason or "guardrail blocked the request")

    def _span(self, name: str, **attrs: str) -> Any:
        try:
            return self._tracer.span(name, **attrs)
        except Exception:  # noqa: BLE001 - tracing must never break the pipeline
            return nullcontext()

    def _record(self, report: PerformanceReport, actor: str) -> None:
        self._audit.record(
            AuditEvent(
                action="performance_report",
                actor=actor,
                decision=Decision.ESCALATED if report.requires_human_review else Decision.ALLOWED,
                response=report.summary,
                citations=report.citations,
                metadata={
                    "market": report.market.value,
                    "vertical": report.vertical.value,
                    "account_id": report.account_id,
                },
            )
        )
