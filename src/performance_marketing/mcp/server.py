"""Serve the governed tool catalog Mkt6 already declares, over MCP 2026-07-28.

The catalog declared three governed tools and served none of them: there was no MCP server
process anywhere in the fleet. This supplies the callables that answer the existing catalog and
declares nothing new. `hex_service_kit.mcpserve.bind` refuses a mismatch in either direction at
start-up.

**All three tools are sections of one report, and that is stated rather than hidden.** The
report service computes attribution, the budget plan and the A/B results together from one
account's metrics, so `budget_optimisation` and `ab_significance` return those sections rather
than recomputing them by another route. A second path to a budget number is a second answer to
the question "what should we spend", which is the kind of duplication this catalog exists to
avoid.

`ab_significance` declares a `test_id`, and the report carries every A/B result for the account,
so the handler selects the named test from that set. An id that matches nothing returns nothing:
"this test" and "every test" are different answers, and a caller must not receive the second
while believing it asked the first.

MCP stdio verifies no end user, so the caller is recorded as a SERVICE caller and no tenant is
asserted.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit import mcpserve

from ..config import build_container
from ..domain.models import AttributionModel, Market, ReportRequest, Vertical

#: The tools this module answers, as data, so a test can hold it against the catalog.
HANDLER_NAMES: tuple[str, ...] = ("performance_report", "budget_optimisation", "ab_significance")


def _request(arguments: dict[str, Any]) -> ReportRequest:
    raw_model = str(arguments.get("attribution_model", "") or "")
    try:
        model = AttributionModel(raw_model)
    except ValueError:
        model = next(iter(AttributionModel))
    return ReportRequest(
        account_id=str(arguments.get("account_id", "") or ""),
        market=Market(str(arguments.get("market", ""))),
        vertical=Vertical(str(arguments.get("vertical", ""))),
        attribution_model=model,
        lookback_days=int(arguments.get("lookback_days") or 30),
    )


def build_handlers(actor: str) -> dict[str, mcpserve.Handler]:
    """Bind each declared tool to the report service that already performs it."""

    def _report(arguments: dict[str, Any]) -> Any:
        from ..api.app import make_report_service

        return make_report_service().build_report(_request(arguments), actor=actor, tenant="")

    def performance_report(**arguments: Any) -> Any:
        return _report(arguments)

    def budget_optimisation(**arguments: Any) -> Any:
        return _report(arguments).budget_plan

    def ab_significance(**arguments: Any) -> Any:
        results = _report(arguments).ab_results
        test_id = str(arguments.get("test_id", "") or "")
        if not test_id:
            return results
        named = [r for r in results if str(getattr(r, "test_id", "")) == test_id]
        # An unmatched id returns nothing rather than the whole set: "this test" and "every
        # test" are different answers and a caller must not get the second believing the first.
        return named

    return {
        "performance_report": performance_report,
        "budget_optimisation": budget_optimisation,
        "ab_significance": ab_significance,
    }


def build_server(actor: str, *, with_audit_tools: bool = True) -> Any:
    """Build the MCP server for Mkt6's catalog, refusing on any catalog/handler mismatch."""
    container = build_container()
    return mcpserve.build_server(
        name="performance-marketing-optimisation",
        version=str(getattr(container.settings, "version", "") or "0.0.1"),
        catalog=container.tool_catalog,
        handlers=build_handlers(actor),
        audit_store=getattr(container, "audit", None) if with_audit_tools else None,
    )
