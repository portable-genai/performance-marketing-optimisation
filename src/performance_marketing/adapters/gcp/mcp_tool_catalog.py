"""MCP tool-catalog adapter (ToolCatalogPort) — the governed tool surface for D4.

Backs the domain ``ToolCatalogPort`` by exposing D4's governed, least-privilege
capabilities as :class:`ToolSpec` objects: ``performance_report``, ``budget_optimisation``
and ``ab_significance``. These are the tools the agent (or a peer agent) may invoke, each
with an explicit JSON input schema so access is scoped and auditable (least privilege).

Interop: the catalog speaks **MCP 2025-11-25**. In an ADK deployment these specs are
surfaced to the agent through an ``McpToolset`` connected to an MCP server fronting the
domain services; here the adapter only *declares* the governed catalog (declarative, no live
MCP connection required to list). The ``mcp`` package is imported LAZILY and only when an
actual MCP wire object is requested.
"""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...domain.models import ToolSpec

# MCP protocol revision this catalog conforms to.
MCP_PROTOCOL_VERSION = "2025-11-25"

# Shared schema fragment: market / vertical scoping reused across tools.
_SCOPE_SCHEMA: dict[str, Any] = {
    "market": {
        "type": "string",
        "enum": ["JP", "AU", "SG"],
        "description": "Restrict to a single market.",
    },
    "vertical": {
        "type": "string",
        "enum": ["banking", "online_retail"],
        "description": "Restrict to a single vertical.",
    },
}


def _build_catalog() -> dict[str, ToolSpec]:
    """Declare the governed tools with explicit, least-privilege input schemas."""
    return {
        "performance_report": ToolSpec(
            name="performance_report",
            description=(
                "Build a cited performance report (attribution, ROAS / CAC, budget plan, A/B "
                "significance, anomalies) for an account. Output requires human review."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Account id."},
                    "attribution_model": {
                        "type": "string",
                        "enum": ["last_touch", "first_touch", "linear", "position_based"],
                        "default": "position_based",
                    },
                    "lookback_days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 365,
                        "default": 30,
                    },
                    **_SCOPE_SCHEMA,
                },
                "required": ["account_id"],
                "additionalProperties": False,
            },
        ),
        "budget_optimisation": ToolSpec(
            name="budget_optimisation",
            description=(
                "Propose a deterministic, budget-neutral spend reallocation for an account. "
                "Output requires human review (maker-checker)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string", "description": "Account id."},
                    **_SCOPE_SCHEMA,
                },
                "required": ["account_id"],
                "additionalProperties": False,
            },
        ),
        "ab_significance": ToolSpec(
            name="ab_significance",
            description=(
                "Compute the two-proportion significance and ship / stop / keep-running "
                "verdict for an A/B experiment."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "test_id": {"type": "string", "description": "Experiment id."},
                    **_SCOPE_SCHEMA,
                },
                "required": ["test_id"],
                "additionalProperties": False,
            },
        ),
    }


class McpToolCatalogAdapter:
    """Declarative MCP 2025-11-25 catalog of D4's governed tools."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._catalog: dict[str, ToolSpec] = _build_catalog()

    # ------------------------------------------------------------------ #
    # ToolCatalogPort
    # ------------------------------------------------------------------ #
    def list_tools(self) -> list[ToolSpec]:
        return list(self._catalog.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._catalog.get(name)

    # ------------------------------------------------------------------ #
    # MCP wire helpers (lazy ``mcp`` import — only when actually used)
    # ------------------------------------------------------------------ #
    def as_mcp_tools(self) -> list[Any]:
        """Render the catalog as MCP ``Tool`` objects (MCP 2025-11-25 schema)."""
        from mcp import types as mcp_types  # noqa: PLC0415 — lazy

        # verify: https://modelcontextprotocol.io/specification/2025-11-25
        return [
            mcp_types.Tool(name=s.name, description=s.description, inputSchema=s.input_schema)
            for s in self._catalog.values()
        ]
