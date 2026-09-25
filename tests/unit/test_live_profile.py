"""The ``live`` laptop profile: ``local`` with the shared local model answering the llm port.

Offline: every model call here goes to a fake transport handed to the kit client, so the
suite needs no model server. What is proved is the adapter's mapping (messages, schema,
temperature, model id, failures) and that the profile builds and keeps the laptop posture.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

import pytest
from hex_service_kit.localmodel import (
    DEFAULT_LOCAL_MODEL,
    LocalModelClient,
    LocalModelSettings,
)
from tests.conftest import _settings

from performance_marketing.adapters.live.llm import LocalModelLLMAdapter
from performance_marketing.adapters.local.identity import LocalPersonaIdentityAdapter
from performance_marketing.config import Container, Settings
from performance_marketing.domain.errors import ModelOutputError, ModelUnavailableError
from performance_marketing.domain.models import (
    LlmMessage,
    LlmRequest,
    Market,
    ReportRequest,
    Vertical,
)
from performance_marketing.domain.services import PerformanceReportService

_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}


def _answer(content: str, model: str = "served-model-id") -> bytes:
    return json.dumps(
        {"model": model, "choices": [{"message": {"role": "assistant", "content": content}}]}
    ).encode()


class _FakeTransport:
    """Answers each chat call with the next scripted reply and records every request body."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, url: str, body: bytes | None, timeout: float) -> bytes:
        assert body is not None
        self.bodies.append(json.loads(body))
        return _answer(self._replies.pop(0))


def _adapter(transport: Callable[[str, bytes | None, float], bytes]) -> LocalModelLLMAdapter:
    client = LocalModelClient(LocalModelSettings(), transport=transport)
    return LocalModelLLMAdapter(_settings("live"), client=client)


def test_a_fenced_invalid_first_answer_is_retried_and_the_valid_one_returned() -> None:
    transport = _FakeTransport('```json\n{"headline": "no summary"}\n```', '{"summary": "ok"}')
    request = LlmRequest(
        messages=(LlmMessage(role="user", content="narrate"),),
        system_instruction="be terse",
        temperature=0.3,
        max_output_tokens=321,
        response_schema=_SCHEMA,
    )

    response = _adapter(transport).generate(request)

    assert json.loads(response.text) == {"summary": "ok"}
    assert response.raw == {"summary": "ok"}
    assert response.model == "served-model-id", "the model id is the one that answered"
    assert len(transport.bodies) == 2, "the invalid first answer must be retried once"
    first = transport.bodies[0]
    assert first["temperature"] == 0.3, "the request's temperature passes through unchanged"
    assert first["max_tokens"] == 321
    assert first["messages"][0]["role"] == "system"
    assert "be terse" in first["messages"][0]["content"]
    assert '"summary"' in first["messages"][0]["content"], "the schema is stated in the prompt"
    assert first["messages"][1] == {"role": "user", "content": "narrate"}
    retry = transport.bodies[1]["messages"]
    assert "summary" in retry[-1]["content"], "the missing field is fed back to the model"


def test_a_request_without_a_schema_is_a_plain_completion() -> None:
    transport = _FakeTransport("plain prose")
    request = LlmRequest(messages=(LlmMessage(role="user", content="hello"),))

    response = _adapter(transport).generate(request)

    assert response.text == "plain prose"
    assert response.raw is None
    assert transport.bodies[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert "temperature" not in transport.bodies[0], "a free call sends no temperature at all"


def test_a_server_that_does_not_answer_is_model_unavailable() -> None:
    def refused(url: str, body: bytes | None, timeout: float) -> bytes:
        raise OSError("connection refused")

    request = LlmRequest(messages=(LlmMessage(role="user", content="x"),))
    with pytest.raises(ModelUnavailableError, match="mlx_vlm.server"):
        _adapter(refused).generate(request)


def test_an_answer_that_never_validates_is_a_model_output_error() -> None:
    transport = _FakeTransport("not json", "still not", "never")
    request = LlmRequest(messages=(LlmMessage(role="user", content="x"),), response_schema=_SCHEMA)
    with pytest.raises(ModelOutputError):
        _adapter(transport).generate(request)
    assert len(transport.bodies) == 3


def test_classify_matches_the_reply_to_a_label() -> None:
    transport = _FakeTransport(" Spike. ")
    assert _adapter(transport).classify("text", ["drop", "spike"]) == "spike"
    assert transport.bodies[0]["temperature"] == 0.0


def test_the_container_builds_every_port_under_live() -> None:
    settings = _settings("live")
    container = Container(settings)
    for port in settings.adapters:
        assert getattr(container, port) is not None, port
    assert isinstance(container.llm, LocalModelLLMAdapter)
    assert isinstance(container.identity, LocalPersonaIdentityAdapter)


def test_live_keeps_the_laptop_posture_and_names_the_local_model() -> None:
    settings = _settings("live")
    assert settings.laptop is True
    assert settings.bind_profile == "local", "live serves seeded personas, so it binds loopback"
    assert settings.runtime == "local"
    assert settings.generator_model == DEFAULT_LOCAL_MODEL
    unchosen = dataclasses.replace(settings, profile_explicit=False)
    assert unchosen.laptop is False


def test_a_live_report_is_narrated_by_the_local_model() -> None:
    settings = _settings("live")
    container = Container(settings)
    transport = _FakeTransport('{"summary": "Search carried the quarter.", "used_source_ids": []}')
    container.__dict__["llm"] = _adapter(transport)
    service = PerformanceReportService(
        metrics=container.metrics,
        ad_platform=container.ad_platform,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        review_router=container.review_router,
    )

    report = service.build_report(
        ReportRequest(account_id="acct-sg-banking", market=Market.SG, vertical=Vertical.BANKING),
        actor="test",
        tenant="demo-bank",
    )

    assert "Search carried the quarter." in report.summary
    assert report.requires_human_review is True


def test_the_settings_loader_accepts_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MKT_PERF_PROFILE", "live")
    settings = Settings.load("config/settings.yaml")
    assert settings.profile == "live"
    assert settings.profile_explicit is True
