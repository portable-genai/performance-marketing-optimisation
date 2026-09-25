"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool (owner decision, 2026-09-23). Both come
from response headers the kit emits (``install_answer_provenance`` in ``api/app.py``) for
whatever the model adapters NOTED as they called. Before a request is answered the pill shows
``generator_model`` from ``/healthz``, so that value must be the model the bound adapter calls,
never one a configuration flag names while the adapter calls another.

This service has no online search tool, so nothing in it notes a search. The route is still
proved to carry ``X-Search-Used`` the day an adapter does, by binding one that notes it.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance
from tests.conftest import LOOPBACK_PEER, _settings
from tests.fixtures import fake_genai

from performance_marketing import config
from performance_marketing.adapters.gcp.gemini_llm import GeminiLLMAdapter
from performance_marketing.adapters.local.llm import LocalDeterministicLLMAdapter
from performance_marketing.api import deps
from performance_marketing.api.app import app
from performance_marketing.config import Container, ModelSettings
from performance_marketing.domain.models import LlmMessage, LlmRequest, LlmResponse

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
REPO_ROOT = Path(__file__).resolve().parents[2]

_REPORT_BODY: dict[str, Any] = {
    "account_id": "acct-sg-banking",
    "market": "SG",
    "vertical": "banking",
}


def _client(monkeypatch: pytest.MonkeyPatch, container: Container) -> TestClient:
    monkeypatch.setattr(deps, "get_container", lambda: container)
    return TestClient(app, client=LOOPBACK_PEER)


def _report(client: TestClient) -> dict[str, str]:
    response = client.post("/v1/report", json=_REPORT_BODY)
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_a_local_report_names_the_stub_that_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under ``local`` the pill says the offline stub answered, the same name ``/healthz`` gives.

    Anything else would be the confusion the pill exists to remove: a laptop run naming a
    Gemini model for a narration that never left the machine.
    """
    settings = _settings("local")
    headers = _report(_client(monkeypatch, Container(settings)))
    assert headers[ANSWERED_BY] == settings.generator_model == "deterministic-offline-stub"
    assert SEARCH_USED not in headers, "no search tool exists here, so none may be claimed"


def test_a_route_that_calls_no_model_names_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing noted, nothing sent: the pill never invents a model nothing called."""
    headers = dict(_client(monkeypatch, Container(_settings("local"))).get("/healthz").headers)
    assert ANSWERED_BY not in headers
    assert SEARCH_USED not in headers


class _SearchingLlm(LocalDeterministicLLMAdapter):
    """The real offline narrator, plus what an adapter that attached a search tool would note."""

    def generate(self, request: LlmRequest) -> LlmResponse:
        provenance.note_model("fake-searching-model")
        provenance.note_search()
        return super().generate(request)


def test_the_route_carries_the_search_flag_and_every_model_that_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings("local")
    container = Container(settings)
    container.__dict__["llm"] = _SearchingLlm(settings)  # the cached_property's slot
    client = _client(monkeypatch, container)
    headers = _report(client)
    assert headers[ANSWERED_BY] == "fake-searching-model, deterministic-offline-stub"
    assert headers[SEARCH_USED] == "true"
    # The next request is a fresh record: an answer never leaks into a later response.
    container.__dict__["llm"] = LocalDeterministicLLMAdapter(settings)
    headers = _report(client)
    assert headers[ANSWERED_BY] == "deterministic-offline-stub"
    assert SEARCH_USED not in headers


def test_the_console_can_read_both_headers_across_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console calls this service directly, so a browser shows it only exposed headers.

    Standalone, the console's origin is not the service's, and a cross-origin response hides
    every header not named in ``Access-Control-Expose-Headers``: the pills would sit on the
    configured model forever with every other assertion here green. The kit's middleware lists
    both; this proves the list reaches a model-backed response through the real app.
    """
    response = _client(monkeypatch, Container(_settings("local"))).post(
        "/v1/report", json=_REPORT_BODY, headers={"Origin": "http://localhost:3000"}
    )
    assert response.status_code == 200, response.text
    listed = ",".join(response.headers.get_list("access-control-expose-headers")).lower()
    assert {ANSWERED_BY, SEARCH_USED} <= {name.strip() for name in listed.split(",")}


def _gemini(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[GeminiLLMAdapter, fake_genai.RecordingClient]:
    fake_genai.install(monkeypatch)
    adapter = GeminiLLMAdapter(_settings("gcp"))
    client = fake_genai.RecordingClient()
    adapter._client = client
    return adapter, client


def test_the_gemini_adapter_notes_the_model_it_called(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _gemini(monkeypatch)
    request = LlmRequest(messages=(LlmMessage(role="user", content="x"),), model="pinned-model")
    with provenance.scope() as record:
        adapter.generate(request)
        adapter.classify("text", ["a", "b"])
    assert [call["model"] for call in client.calls] == ["pinned-model", adapter._models.triage]
    assert record.models == ["pinned-model", adapter._models.triage]
    assert record.search_used is False, "no search tool is attached, so none may be noted"


def test_a_refused_call_names_no_model(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter, client = _gemini(monkeypatch)

    def _refuse(**_: Any) -> Any:
        raise RuntimeError("refused")

    monkeypatch.setattr(client, "generate_content", _refuse)
    with provenance.scope() as record, pytest.raises(RuntimeError):
        adapter.generate(LlmRequest(messages=(LlmMessage(role="user", content="x"),)))
    assert record.models == []


def test_generator_model_is_the_model_the_gemini_adapter_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the pill says before an answer must be what the adapter then calls."""
    adapter, client = _gemini(monkeypatch)
    adapter.generate(LlmRequest(messages=(LlmMessage(role="user", content="x"),)))
    assert client.calls[0]["model"] == _settings("gcp").generator_model


def test_no_flag_swaps_the_model_the_pill_names() -> None:
    """The latent false banner: a flag that moved the label but not the model that answered.

    The resolver once named ``models.hard_reasoning`` when ``models.use_hard_reasoning`` was
    set, while the Gemini adapter called ``request.model or models.reasoning`` and never read
    the flag. The flag is gone; a stray one on a settings object must change nothing.
    """
    models = SimpleNamespace(
        reasoning="the-model-the-adapter-calls",
        hard_reasoning="a-model-nobody-calls",
        use_hard_reasoning=True,
    )
    named = config._model_from_settings(SimpleNamespace(models=models), "models.reasoning")
    assert named == "the-model-the-adapter-calls"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    fields = set(ModelSettings.__dataclass_fields__)
    assert "use_hard_reasoning" not in fields and "hard_reasoning" not in fields
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
