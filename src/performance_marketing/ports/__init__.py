"""Ports — the abstract interfaces (the hexagon boundary).

Every port is a ``typing.Protocol`` (``@runtime_checkable``) so adapters need only
structural conformance and the contract test can verify any adapter family (GCP,
remote-platform, on-prem placeholder, or local) satisfies the same contract.
"""

from .generation import LlmPort
from .governance import AgentRegistryPort, ToolCatalogPort
from .identity import EndUserAuthUnavailableError, IdentityPort
from .metrics import AdPlatformPort, MetricsPort
from .observability import (
    AuditSinkPort,
    EvaluationGatePort,
    ObservabilityTracerPort,
    TokenUsage,
)
from .review_router import ReviewRouterPort
from .safety import GuardrailPort

__all__ = [
    "MetricsPort",
    "AdPlatformPort",
    "LlmPort",
    "GuardrailPort",
    "AuditSinkPort",
    "ObservabilityTracerPort",
    "EvaluationGatePort",
    "TokenUsage",
    "AgentRegistryPort",
    "ToolCatalogPort",
    "IdentityPort",
    "EndUserAuthUnavailableError",
    "ReviewRouterPort",
]
