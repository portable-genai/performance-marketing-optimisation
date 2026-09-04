"""Span ATTRIBUTES carry structure, never content, and this is the test that can tell.

The pipeline tests wire the real ``LocalNoopTracerAdapter``, whose ``span`` is a ``nullcontext``: it
observes nothing, so a span that started carrying the advertiser account key, the account's brand
name or the drafted summary would keep every existing test green. A trace backend is not the WORM
audit trail. It has no redaction stage, a wider read audience and no retention rule written against
a regulator's requirement, so an attribute is OUTSIDE the boundary the guardrail and the
redact-before-wire router hold: the sibling test
``test_payload_is_redacted_and_carries_tenant_and_severity`` proves the human-review-console payload
masks contact identifiers, and none of that machinery runs on a span.

The recording tracer here keeps ``dict(attributes)`` and drives the real request path,
``PerformanceReportService.build_report``, over the local seeded accounts. ``account_id`` is
the very value the guardrail screens on the way in, which makes it the obvious thing for a
call site to attach to the span, so it is asserted by name.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext

import pytest

from performance_marketing.config import Container
from performance_marketing.domain.models import (
    Market,
    ReportRequest,
    TokenUsage,
    Vertical,
)
from performance_marketing.domain.services import PerformanceReportService

ACCOUNT_ID = "acct-sg-banking"
ACTOR = "analyst@bank.example"
TENANT = "demo-bank"

#: The complete attribute key set an marketing-compliance-gate span may carry, per span name.
#: Widening one of
#: these is a decision about what leaves the trust boundary, so it is made here rather
#: than at a call site.
_ALLOWED = {
    "report.build": {"market"},
}


class _AttributeRecordingTracer:
    """Keeps (name, attributes) per span; the local adapter records nothing at all."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    def span(self, name: str, **attributes: str) -> AbstractContextManager[None]:
        self.spans.append((name, dict(attributes)))
        return nullcontext()

    def record_token_usage(self, usage: TokenUsage, model: str) -> None:
        return None


@pytest.fixture
def tracer() -> _AttributeRecordingTracer:
    return _AttributeRecordingTracer()


def _build_report(container: Container, tracer: _AttributeRecordingTracer):
    service = PerformanceReportService(
        metrics=container.metrics,
        ad_platform=container.ad_platform,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=tracer,
        audit=container.audit,
        review_router=container.review_router,
    )
    request = ReportRequest(account_id=ACCOUNT_ID, market=Market.SG, vertical=Vertical.BANKING)
    return service.build_report(request, actor=ACTOR, tenant=TENANT)


def test_the_request_path_opens_exactly_the_known_spans(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    _build_report(local_container, tracer)
    names = {name for name, _ in tracer.spans}
    assert names == set(_ALLOWED), (
        "the set of spans this request path opens changed; a new span site is a "
        "trust-boundary decision, so record it in _ALLOWED here deliberately"
    )


def test_every_span_carries_allowlisted_keys_only(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    _build_report(local_container, tracer)
    assert tracer.spans, "the request path opened no span at all"
    for name, attributes in tracer.spans:
        assert name in _ALLOWED, f"unexpected span {name!r}; add it here deliberately"
        assert set(attributes) == _ALLOWED[name], (
            f"span {name!r} attribute keys changed; widening the set is a trust-boundary "
            "decision, so update _ALLOWED here deliberately"
        )


def test_no_span_attribute_carries_the_account_key_or_its_brand(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    """The screened account key and the seeded brand names stay out of the trace."""
    _build_report(local_container, tracer)
    emitted = " ".join(value for _, attributes in tracer.spans for value in attributes.values())
    assert ACCOUNT_ID not in emitted, "the advertiser account key reached a span attribute"
    assert "FICTIONAL" not in emitted, (
        "every seeded account, brand and metric snippet is stamped FICTIONAL; seeing one "
        "in a span attribute means seeded content reached the trace"
    )


def test_no_span_attribute_carries_the_drafted_summary(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    """The narrated summary is model output about spend; it belongs in the audit, not a span."""
    report = _build_report(local_container, tracer)
    emitted = " ".join(value for _, attributes in tracer.spans for value in attributes.values())
    assert report.summary, "the pipeline drafted no summary, so this proves nothing"
    assert report.summary not in emitted, "the drafted summary reached a span attribute"


def test_every_attribute_value_is_a_string(
    local_container: Container, tracer: _AttributeRecordingTracer
) -> None:
    """The port declares str values; a structured object smuggles content past a grep."""
    _build_report(local_container, tracer)
    for name, attributes in tracer.spans:
        for key, value in attributes.items():
            assert isinstance(value, str), f"span {name!r} attribute {key!r} is not a str"


def test_the_recorder_satisfies_the_tracer_port() -> None:
    """The guard is only evidence if the service accepts the recorder as its tracer."""
    from performance_marketing.ports.observability import ObservabilityTracerPort

    assert isinstance(_AttributeRecordingTracer(), ObservabilityTracerPort)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
