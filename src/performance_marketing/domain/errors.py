"""Domain exceptions for the Performance Marketing system (D4).

Pure-Python exception hierarchy raised by the orchestration services. The domain layer
never imports Google Cloud, ADK, or any framework: these errors let callers (API, CLI,
the agent runtime adapter) react to domain-level failures without coupling to any vendor
SDK error type.
"""

from __future__ import annotations


class PerformanceMarketingError(Exception):
    """Base class for all domain-level errors raised by D4 services."""


class GuardrailBlockedError(PerformanceMarketingError):
    """Raised when the A1 guardrail blocks an input or output.

    A blocked unsafe request must never yield a partial report: the orchestrator raises
    this rather than assembling a report from screened-out content.
    """


class MetricsEmptyError(PerformanceMarketingError):
    """Raised when the metrics warehouse returns no data for the account / window.

    A performance report must be grounded in measured spend / conversions; an empty
    metrics result is a hard error so a report is never built on no data.
    """


class AuthorizationError(PerformanceMarketingError):
    """Raised when object-level authorization fails (C2), fail-closed.

    If the requested account carries a tenant that does not match the verified principal's
    tenant, the request is denied before any report is built, ranked or audited: a
    demo-bank operator must never read an other-bank account's report by guessing its id.
    Exposure here is bounded (aggregate channel metrics, no per-customer PII), but the
    tenant-isolation contract is still enforced rather than assumed.
    """


class UnknownAccountError(PerformanceMarketingError):
    """Raised when the requested account id has no configured / seeded data."""


class UnsupportedMarketError(PerformanceMarketingError):
    """Raised when a requested market has no configured residency region / profile."""


class UnsupportedVerticalError(PerformanceMarketingError):
    """Raised when a requested vertical has no configured seed / targets."""
