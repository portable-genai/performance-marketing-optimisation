"""A2A AgentCard for the D4 Performance Marketing agent (A3 Registry & Governance).

This builds the agent's discovery card (the same minimal A2A shape the ``agent-registry``
service stores and serves, SPEC §6). It is published at ``/.well-known/agent-card.json``;
:func:`agent_card_document` returns the JSON-safe body the API layer serves there, and the
``platform`` registry adapter registers the same card in agent-registry (rule R4).

The card advertises the skill D4 produces (build_performance_report), mirroring the ADK
FunctionTool so a peer agent or the registry sees one consistent capability surface.

This module is pure (domain models only) and imports without ADK or any Google Cloud SDK
installed (SPEC §4).
"""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..domain.models import AgentCard, AgentSkill

SKILLS: tuple[AgentSkill, ...] = (
    AgentSkill(
        id="build_performance_report",
        name="Performance report",
        description=(
            "Build a cited performance report for an ad account in a market (JP / AU / SG) and "
            "vertical (banking / online retail): multi-touch attribution, ROAS / CAC "
            "efficiency, deterministic bid / budget optimisation, A/B significance and anomaly "
            "alerts, plus a narrated summary. Always flagged for human review (P-06) before any "
            "spend shift."
        ),
    ),
)

_DESCRIPTION = (
    "Performance-marketing and attribution agent for a bank or online retailer. Measures and "
    "optimises paid and owned channels with replayable maths (multi-touch attribution, "
    "ROAS / CAC, deterministic bid and budget optimisation, A/B significance, anomaly alerts) "
    "and narrates recommended spend shifts, generic across banking and online retail and the "
    "JP / AU / SG markets. Built ports-and-adapters on the Gemini Enterprise Agent Platform. "
    "The model narrates and recommends; every consequential figure is computed deterministically "
    "and carries a citation."
)


def build_agent_card(settings: Settings) -> AgentCard:
    """Construct the A2A :class:`AgentCard` for this agent."""
    return AgentCard(
        name="performance-marketing-optimisation",
        description=_DESCRIPTION,
        url=_resolve_url(settings),
        version="0.1.0",
        skills=SKILLS,
        provider="performance-marketing-optimisation",
    )


def agent_card_document(settings: Settings) -> dict[str, Any]:
    """Return the JSON-safe body to serve at ``/.well-known/agent-card.json``."""
    from ..domain.serialization import to_jsonable

    return to_jsonable(build_agent_card(settings))


def _resolve_url(settings: Settings) -> str:
    """Best-effort public URL for the card, region-pinned to the active market."""
    resource = settings.agent_engine.resource_name
    if resource:
        return f"https://aiplatform.googleapis.com/v1/{resource}"
    return "https://performance-marketing-optimisation.mkt.internal/a2a"
