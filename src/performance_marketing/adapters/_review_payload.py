"""Shared conversion from an escalated performance report to an ``review-kit`` Review payload.

Lives in the adapter layer (not the pure domain) because it depends on the kit. D4 is generic
marketing over aggregate channel metrics, so the report carries no per-customer PII by design; even
so the subject descriptor, summary and citation snippets are scrubbed for universal identifiers
(email / phone) before they leave the process (R1 / P-04 boundary), a defensive belt so a stray
identifier that slipped into a source title or snippet never reaches human-review-console over the
wire; human-review-console redacts again before its own audit write (defense in depth). The maker
(the agent that originated the report) and the tenant (the object-level-authorization owner verified
at the build boundary, C2) are asserted here and trusted by human-review-console because this is an
authenticated S2S caller (per-hop OBO is the deferred next layer).
"""

from __future__ import annotations

import re

from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.models import PerformanceReport, Severity

# Cap the citations carried on the wire: enough to let a reviewer trace the report without copying
# the entire evidence set into the review console.
_MAX_CITATIONS = 8

# Universal identifier patterns (email / phone). D4 handles no national ids, so the defensive
# scrub is the universal set only: the review console is a shared sink and the payload must never
# carry a raw contact identifier regardless of which market configured this producer.
_UNIVERSAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")),
)

# Ordered weakest -> strongest so ``max`` picks the report's most severe signal.
_SEVERITY_ORDER: tuple[Severity, ...] = (
    Severity.LOW,
    Severity.MEDIUM,
    Severity.HIGH,
    Severity.CRITICAL,
)


def _redact(text: str) -> str:
    """Mask universal contact identifiers before the wire, then collapse whitespace."""
    redacted = text
    for info_type, pattern in _UNIVERSAL_PATTERNS:
        redacted = pattern.sub(f"[{info_type}]", redacted)
    return re.sub(r"\s+", " ", redacted).strip()


def _report_severity(report: PerformanceReport) -> Severity:
    """The report's strongest signal from its material budget shifts and anomalies.

    Defaults to MEDIUM: a performance report always warrants human review, so the floor is the
    medium band even when no individual shift or anomaly is itself HIGH+.
    """
    present: list[Severity] = [Severity.MEDIUM]
    if report.budget_plan is not None:
        present.extend(s.severity for s in report.budget_plan.material_shifts)
    if report.anomalies is not None:
        present.extend(a.severity for a in report.anomalies.anomalies)
    return max(present, key=_SEVERITY_ORDER.index)


def _kit_citations(report: PerformanceReport) -> tuple[KitCitation, ...]:
    seen: set[str] = set()
    out: list[KitCitation] = []
    for c in report.citations:
        if c.source_id in seen:
            continue
        seen.add(c.source_id)
        out.append(
            KitCitation(source_id=c.source_id, title=_redact(c.title), snippet=_redact(c.snippet))
        )
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def report_to_review(report: PerformanceReport, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits to human-review-console when a performance report
    escalates.
    """
    descriptor = (
        f"Performance report for account {report.account_id} "
        f"(market={report.market.value}, vertical={report.vertical.value})"
    )
    shifts = len(report.budget_plan.material_shifts) if report.budget_plan is not None else 0
    anomalies = len(report.anomalies.anomalies) if report.anomalies is not None else 0
    summary = (
        f"material_shifts={shifts}; anomalies={anomalies}; "
        f"ab_results={len(report.ab_results)}; citations={len(report.citations)}"
    )
    severity = _report_severity(report)
    # Dual control when the strongest signal is HIGH+; a routine medium report needs one checker.
    dual = severity in (Severity.HIGH, Severity.CRITICAL)
    return Review(
        action="performance_report:build",
        subject=_redact(descriptor),
        maker=maker,
        tenant=tenant,
        summary=_redact(summary),
        severity=severity.value,
        required_approvals=2 if dual else 1,
        sod_group="performance-maker-checker",
        case_ref=report.id,
        citations=_kit_citations(report),
    )
