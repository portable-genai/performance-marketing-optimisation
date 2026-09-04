"""Remote-platform evaluation adapter : thin HTTP client to model-quality-gate.

At promotion this vertical's quality is checked against the shared **model-quality-gate AI Quality /
model-risk** service (``model-quality-gate``). This adapter implements
:class:`EvaluationGatePort` against model-quality-gate's hardened contract:

* ``evaluate`` -> ``POST /v1/evaluations {target, dataset_id, bundle}`` -> EvalReport.
* ``gate``     -> ``POST /v1/gate {target, dataset_id, bundle}`` -> ``{passed}``.

**Sourced from the shared ``agent-eval-kit`` commons.** The HTTP contract
is ``agent_eval_kit.gate_client.PromotionGateClient``; this adapter configures it (the
registered ``mkt4-performance`` bundle, the reasoning model, and this repo's S2S auth
headers) and re-raises its errors as :class:`RemoteEvaluationError`.

The client's :class:`EvalReport` is returned UNCHANGED. Rebuilding it field by field into a
locally declared report carrying only ``dataset``, ``results`` and ``n_examples`` is a lossy
identity function, because the domain type IS the commons type: it drops the run id, dataset
version, dataset digest, evaluator, schema version, artifact refs and attestation flag, and it
drops them immediately after the client has refused any response that lacked them. Promotion
evidence a model-risk reviewer cannot retrieve later is not evidence.
"""

from __future__ import annotations

from agent_eval_kit.gate_client import GateClientError, PromotionGateClient

from ...config import Settings
from ...domain.errors import PerformanceMarketingError
from ...domain.models import EvalReport
from ...envread import setting_or_default
from . import _s2s

_DEFAULT_URL = "http://localhost:8084"

#: The registered model-quality-gate metric bundle for this vertical (model-quality-gate owns the
#: metrics + bars).
_BUNDLE = "mkt4-performance"
#: Prompt/agent version tag; bump when the prompt corpus changes, or source it from a registry.
_PROMPT_VERSION = "v1"


class RemoteEvaluationError(PerformanceMarketingError):
    """Raised when the model-quality-gate quality service returns a non-2xx response."""


class RemoteEvaluationAdapter:
    """HTTP client for the model-quality-gate ``model-quality-gate`` service (via
    PromotionGateClient).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = PromotionGateClient(
            setting_or_default("QUALITY_GATE_URL", _DEFAULT_URL),
            bundle=_BUNDLE,
            model=settings.models.reasoning,
            prompt_version=_PROMPT_VERSION,
            auth_headers=lambda: _s2s.headers(),
        )

    def evaluate(self, dataset_path: str) -> EvalReport:
        """Score ``dataset_path`` via model-quality-gate and return the report, evidence intact."""
        try:
            return self._client.evaluate(dataset_path)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc

    def gate(self, target: str) -> bool:
        """Promotion gate: True iff model-quality-gate reports ``target`` passes."""
        try:
            return self._client.gate(target)
        except GateClientError as exc:
            raise RemoteEvaluationError(str(exc)) from exc
