"""Sampling is decided per call site: pinned where output is compared, free where it is prose.

History. This file began as "the grounded request must not sample by default". The
organization front page claims the consequential math is deterministic and replayable and that
the model never produces the number. That was measured in `cdd-sow-research`, and there it was
FALSE: on 2026-08-26 two runs of one identical case, minutes apart, returned different scores
and confidences, because the shared request builder defaulted to `temperature=0.2`. The answer
then was to pin 0.0 on the request type, so every call site that omitted it inherited the pin.

What changed (owner decision, 2026-09-23). Pinning everything also pinned prose that nothing
compares, and some models (Opus 5, Fable 5) reject the parameter outright. So the type's
default is now `None`, which sends NO temperature at all, and each call site says what it
needs: `0.0` where the output is extracted, classified, scored or compared against a
deterministic check; free for drafting, summarising, narration, explanation and judges.

In this service the numbers are never the model's: the deterministic engines fix them before
the model is called. So the one domain call site (the report narration) is free, and the only
pinned calls are the adapters' single-label `classify`. The ADK agent converses and narrates
over tool results, so it sends no temperature either.

**Temperature 0 is not a promise of determinism, and nothing here asserts one.** A hosted model
can still vary across batching and model revisions. It is the strongest thing a caller controls
where a comparison has to be a measurement rather than a sample.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from tests.conftest import _settings
from tests.fixtures import fake_genai

from performance_marketing.adapters.local.llm import LocalDeterministicLLMAdapter
from performance_marketing.api import deps
from performance_marketing.config import Container
from performance_marketing.domain.models import (
    LlmMessage,
    LlmRequest,
    LlmResponse,
    Market,
    ReportRequest,
    Vertical,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "performance_marketing"


class _Recording(LocalDeterministicLLMAdapter):
    """The real offline narrator, recording every request the service hands it."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.requests: list[LlmRequest] = []

    def generate(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        return super().generate(request)


def test_the_request_type_leaves_sampling_to_the_call_site() -> None:
    """The default sends nothing, so a call site that omits it is free, never 1.0."""
    assert LlmRequest.__dataclass_fields__["temperature"].default is None


def test_the_report_narration_is_free() -> None:
    """The narration runs over numbers the engines already fixed; nothing compares the prose."""
    settings = _settings("local")
    container = Container(settings)
    recorder = _Recording(settings)
    container.__dict__["llm"] = recorder  # the cached_property's slot
    service = deps.make_report_service(container)
    service.build_report(
        ReportRequest(account_id="acct-sg-banking", market=Market.SG, vertical=Vertical.BANKING),
        actor="test",
        tenant="demo-bank",
    )
    assert recorder.requests, "the report never reached the model port"
    assert [r.temperature for r in recorder.requests] == [None] * len(recorder.requests)


def _gemini_config(monkeypatch: pytest.MonkeyPatch, request: LlmRequest) -> dict[str, object]:
    from performance_marketing.adapters.gcp.gemini_llm import GeminiLLMAdapter

    fake_genai.install(monkeypatch)
    adapter = GeminiLLMAdapter(_settings("gcp"))
    client = fake_genai.RecordingClient()
    adapter._client = client
    adapter.generate(request)
    config: dict[str, object] = client.calls[0]["config"]
    return config


def test_the_gemini_adapter_omits_temperature_when_free(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _gemini_config(monkeypatch, LlmRequest(messages=(LlmMessage("user", "x"),)))
    assert "temperature" not in config, "free must mean absent: some models reject the parameter"


def test_the_gemini_adapter_keeps_a_pinned_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    request = LlmRequest(messages=(LlmMessage("user", "x"),), temperature=0.0)
    assert _gemini_config(monkeypatch, request)["temperature"] == 0.0


def test_gemini_classification_is_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """A label is compared against a fixed set, so the triage call does not sample."""
    from performance_marketing.adapters.gcp.gemini_llm import GeminiLLMAdapter

    fake_genai.install(monkeypatch)
    adapter = GeminiLLMAdapter(_settings("gcp"))
    client = fake_genai.RecordingClient(reply="b")
    adapter._client = client
    assert adapter.classify("text", ["a", "b"]) == "b"
    assert client.calls[0]["config"]["temperature"] == 0.0


def test_the_agent_sends_no_temperature() -> None:
    """The ADK agent converses over tool results; its generation config must not pin or sample.

    Read from the source because building the agent needs the ADK, which the gate never has.
    """
    tree = ast.parse((SRC / "agent" / "root_agent.py").read_text(encoding="utf-8"))
    configs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "GenerateContentConfig"
    ]
    assert configs, "the agent's generation config moved; re-point this check at it"
    for node in configs:
        assert "temperature" not in {kw.arg for kw in node.keywords}
