"""Local tool-catalog adapter (ToolCatalogPort) — in-process MCP tool catalog.

The ``local`` profile's stand-in for the governed **MCP** tool catalog: a small,
deterministic in-process set of least-privilege tool specs. SDK-free and unconditional
(there is no emulator for the tool catalog).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ToolSpec


class LocalToolCatalogAdapter:
    """In-process catalog of the governed tools exposed to the agent."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tools: dict[str, ToolSpec] = {
            "performance_report": ToolSpec(
                name="performance_report",
                description="Build a cited performance report for an account.",
                input_schema={
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}},
                },
            ),
            "budget_optimisation": ToolSpec(
                name="budget_optimisation",
                description="Propose a budget-neutral spend reallocation (requires review).",
                input_schema={
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}},
                },
            ),
        }

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)
