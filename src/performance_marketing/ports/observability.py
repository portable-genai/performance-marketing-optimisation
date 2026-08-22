"""Observability ports — the A5 (audit/trace) and A4 (eval gate) concerns.

Primary GCP adapters: a **Cloud Logging locked WORM bucket** for immutable audit, **Cloud
Trace via OpenTelemetry** for the reasoning-loop traces, and the **Gen AI evaluation
service** plus the A4 promotion gate for model risk.

``ObservabilityTracerPort`` and ``EvaluationGatePort`` are RE-EXPORTED from the commons, not
declared here. A Protocol copied into N repositories is N Protocols: sixteen repos had each
hand-copied this module and by the time anyone compared them they disagreed, one having
dropped the eval port entirely and two having dropped its ``gate`` method, which is the half
that can refuse a promotion. There is now one definition of each, and only one to fix.

``AuditSinkPort`` stays declared here on purpose: it is typed in this repo's own vocabulary
(:class:`~performance_marketing.domain.models.AuditEvent`), so it is not a shared shape.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from agent_eval_kit import EvaluationGatePort as EvaluationGatePort
from hex_service_kit.observability import ObservabilityTracerPort as ObservabilityTracerPort
from hex_service_kit.observability import TokenUsage as TokenUsage

from ..domain.models import AuditEvent


@runtime_checkable
class AuditSinkPort(Protocol):
    def record(self, event: AuditEvent) -> None:
        """Write an immutable audit record (WORM)."""
        ...


__all__ = [
    "AuditSinkPort",
    "EvaluationGatePort",
    "ObservabilityTracerPort",
    "TokenUsage",
]
