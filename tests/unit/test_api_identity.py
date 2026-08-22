"""API-boundary identity tests: the verified Principal supplies the audit actor.

Proves the server-side identity seam end to end through the FastAPI ``/v1/report`` route:

* an unknown ``X-Dev-Persona`` is rejected with 401 (never silently treated as anonymous),
* with no persona header the default persona's subject is the recorded audit actor, and
* a selected persona's subject is the recorded audit actor.

``deps.get_container`` is ``lru_cache``-d, so we monkeypatch it to return a container backed
by an in-memory local stack (rather than mutating env), and read the actor back from the
local append-only audit adapter.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import LOOPBACK_PEER

from performance_marketing.api import app as app_module
from performance_marketing.api import deps
from performance_marketing.config import Container, LocalSettings, Settings

_CONFIG_PATH = "config/settings.yaml"


def _local_container() -> Container:
    base = Settings.load(_CONFIG_PATH)
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        models=base.models,
        bigquery=base.bigquery,
        forecast=base.forecast,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(audit_path=":memory:"),
        markets=base.markets,
        adapters=base.adapters,
    )
    return Container(settings)


@pytest.fixture
def client_and_container(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Container]:
    container = _local_container()
    # Both the API deps factory and the security dependency read the container through
    # deps.get_container; monkeypatch it so every call shares this in-memory instance.
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app_module.app, client=LOOPBACK_PEER), container


def _report_body() -> dict[str, str]:
    return {"account_id": "acct-sg-banking", "market": "SG", "vertical": "banking"}


def test_cross_tenant_persona_is_403(
    client_and_container: tuple[TestClient, Container],
) -> None:
    """C2 through the HTTP seam: the other-bank persona requesting a demo-bank account is 403,
    a fail-closed object-authorization denial, not a leak of another tenant's report.
    """
    client, _ = client_and_container
    resp = client.post("/v1/report", json=_report_body(), headers={"X-Dev-Persona": "other-tenant"})
    assert resp.status_code == 403


def test_same_tenant_persona_is_200(
    client_and_container: tuple[TestClient, Container],
) -> None:
    """The complement: a demo-bank persona reads a demo-bank account normally."""
    client, _ = client_and_container
    resp = client.post("/v1/report", json=_report_body(), headers={"X-Dev-Persona": "analyst"})
    assert resp.status_code == 200


def test_unknown_persona_is_401(client_and_container: tuple[TestClient, Container]) -> None:
    client, _ = client_and_container
    resp = client.post(
        "/v1/report", json=_report_body(), headers={"X-Dev-Persona": "does-not-exist"}
    )
    assert resp.status_code == 401


def test_default_persona_is_audit_actor(
    client_and_container: tuple[TestClient, Container],
) -> None:
    client, container = client_and_container
    resp = client.post("/v1/report", json=_report_body())
    assert resp.status_code == 200
    actors = {e["actor"] for e in container.audit.read_all()}
    assert "demo.analyst@bank.example" in actors  # the default (first) persona's subject


def test_selected_persona_is_audit_actor(
    client_and_container: tuple[TestClient, Container],
) -> None:
    client, container = client_and_container
    resp = client.post("/v1/report", json=_report_body(), headers={"X-Dev-Persona": "auditor"})
    assert resp.status_code == 200
    actors = {e["actor"] for e in container.audit.read_all()}
    assert "demo.auditor@bank.example" in actors


def test_personas_route_lists_seeded_personas(
    client_and_container: tuple[TestClient, Container],
) -> None:
    client, _ = client_and_container
    resp = client.get("/v1/personas")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"analyst", "approver", "auditor", "other-tenant"} <= ids
