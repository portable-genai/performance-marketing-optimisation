"""Import-safety + wiring tests for the D4 ADK agent layer.

The local / on-prem / test profile installs **no Google Cloud SDK**, so importing the agent
wiring modules (and building the AgentCard, and calling the plain tool callable) must never pull
in ``google.adk`` / ``google-cloud-*``. The agent-card endpoint is also exercised end-to-end
against the local SDK-free stack via a monkeypatched in-memory container.
"""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from performance_marketing.api import deps
from performance_marketing.api.app import app
from performance_marketing.config import Container, Settings

_EXPECTED_SKILLS = {"build_performance_report"}


# --------------------------------------------------------------------------- #
# Import safety (no ADK installed)
# --------------------------------------------------------------------------- #
def test_agent_package_imports_without_adk() -> None:
    module = importlib.import_module("performance_marketing.agent")
    assert module.build_root_agent is not None
    assert module.build_agent_card is not None
    assert "google.adk" not in sys.modules


def test_agent_root_imports_without_adk() -> None:
    module = importlib.import_module("performance_marketing.agent.root_agent")
    assert repr(module.root_agent)  # touching the lazy proxy must not build the agent
    assert "google.adk" not in sys.modules


def test_mcp_toolset_is_none_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    ra = importlib.import_module("performance_marketing.agent.root_agent")

    monkeypatch.delenv(ra.MCP_SERVER_URL_ENV, raising=False)
    assert ra._build_mcp_toolset() is None
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The AgentCard is pure domain (no ADK)
# --------------------------------------------------------------------------- #
def test_agent_card_is_pure(local_settings: Settings) -> None:
    from performance_marketing.agent.agent_card import build_agent_card

    card = build_agent_card(local_settings)
    assert card.name == "performance-marketing-optimisation"
    assert {s.id for s in card.skills} == _EXPECTED_SKILLS


def test_governed_tools_match_card_skills() -> None:
    """Least privilege (R4): the tool surface and the advertised skills stay in step."""
    from performance_marketing.agent import tools
    from performance_marketing.agent.agent_card import SKILLS

    assert tools.governed_tool_names() == {s.id for s in SKILLS}


# --------------------------------------------------------------------------- #
# The plain tool callable runs offline against the local stack (no ADK)
# --------------------------------------------------------------------------- #
def test_build_performance_report_tool_offline(local_settings: Settings) -> None:
    from performance_marketing.agent.tools import build_performance_report

    result = build_performance_report(
        "acct-sg-banking",
        market="SG",
        vertical="banking",
        actor="analyst@brand.example",
        settings=local_settings,
    )
    assert result["requires_human_review"] is True
    assert result["citations"], "a report must carry citations"
    assert "google.adk" not in sys.modules


# --------------------------------------------------------------------------- #
# The agent-card endpoint end-to-end (local stack)
# --------------------------------------------------------------------------- #
@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, local_settings: Settings) -> TestClient:
    container = Container(local_settings)
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def test_agent_card_endpoint(client: TestClient) -> None:
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "performance-marketing-optimisation"
    assert {s["id"] for s in body["skills"]} == _EXPECTED_SKILLS


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
