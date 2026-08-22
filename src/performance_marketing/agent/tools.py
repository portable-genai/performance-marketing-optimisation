"""ADK FunctionTools that expose the D4 domain services to the agent.

The tool is a thin, side-effect-honest wrapper: it builds the :class:`PerformanceReportService`
from a :class:`~performance_marketing.config.Container` (so every port is bound to the adapter
selected by the active profile), invokes the domain method, and returns a JSON-safe dict via
:func:`~performance_marketing.domain.serialization.to_jsonable`.

Design notes
------------
* The domain service owns orchestration and every consequential number (multi-touch
  attribution, ROAS / CAC efficiency, deterministic bid / budget optimisation, A/B
  significance, anomaly detection; SPEC §5). The tool adds **no** business logic: the model
  narrates and recommends over the already-computed, replayable maths; it never produces the
  number itself.
* ``google.adk`` is imported lazily inside :func:`build_function_tools` so this module imports
  cleanly under the on-prem / local / test profile with no ADK installed (SPEC §4). The plain
  Python tool callable is importable and unit-testable without ADK at all.
* The callable carries a precise type-hinted signature and docstring: ADK derives the tool's
  name, description and JSON parameter schema from them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import Container, Settings, build_container

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

_DEFAULT_ACTOR = "performance-marketing-optimisation-agent"
_DEFAULT_TENANT = "demo-bank"  # object-level authz (C2): the tenant the account must belong to


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def build_performance_report(
    account_id: str,
    market: str = "SG",
    vertical: str = "banking",
    attribution_model: str = "position_based",
    lookback_days: int = 30,
    actor: str = _DEFAULT_ACTOR,
    tenant: str = _DEFAULT_TENANT,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Build a cited performance report for an ad account.

    Bundles the deterministic analyses (multi-touch attribution, ROAS / CAC efficiency, bid /
    budget optimisation recommendations, A/B significance and anomaly alerts) plus a narrated
    summary. Always flagged for human review (maker-checker) before any spend shift; every
    figure carries a citation and is computed deterministically, never by the model.

    Args:
      account_id: The ad account to report on.
      market: Market code: "JP", "AU" or "SG".
      vertical: "banking" or "online_retail".
      attribution_model: "last_touch", "first_touch", "linear" or "position_based".
      lookback_days: Reporting lookback window in days.
      actor: Authenticated identity the request is made for.

    Returns:
      A JSON-safe ``PerformanceReport`` dict.
    """
    from ..api.deps import make_report_service
    from ..domain.models import AttributionModel, Market, ReportRequest, Vertical
    from ..domain.serialization import to_jsonable

    c = _container(settings)
    request = ReportRequest(
        account_id=account_id,
        market=Market(market),
        vertical=Vertical(vertical),
        attribution_model=AttributionModel(attribution_model),
        lookback_days=lookback_days,
    )
    return to_jsonable(make_report_service(c).build_report(request, actor=actor, tenant=tenant))


TOOL_FUNCTIONS = (build_performance_report,)


def governed_tool_names() -> frozenset[str]:
    """The tool names this agent exposes (mirrors the governed MCP catalog, rule R4)."""
    return frozenset(fn.__name__ for fn in TOOL_FUNCTIONS)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each domain-service callable as an ADK ``FunctionTool``.

    ADK introspects each function's signature and docstring to derive the tool name,
    description and parameter JSON schema. ``google.adk`` is imported here (lazily) so the
    module is import-safe without ADK installed (SPEC §4).
    """
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=fn) for fn in TOOL_FUNCTIONS]
