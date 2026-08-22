"""Contract tests for the platform eval adapter (RemoteEvaluationAdapter -> Hrz4).

These pin the wire contract of the Hrz4 AI-quality / model-risk gate, without a live
service, using ``respx`` to intercept the ``httpx`` calls:

* ``POST /v1/evaluations`` carries a **structured target**, a top-level ``dataset_id`` that
  equals ``target.dataset_id``, and selects metrics ONLY by the ``bundle`` name — never a
  metric-name list. Its ``{"results": [...]}`` body is parsed into an :class:`EvalReport`.
* ``POST /v1/gate`` (a POST, not a GET) returns a full promotion decision.
* A non-2xx response raises :class:`RemoteEvaluationError`.

The RESPONSE fixtures model the hardened ``agent-eval-kit`` contract, which is far stricter
than a naked aggregate boolean. The client RE-DERIVES every verdict from the
evidence and raises on any contradiction, on the plain evaluations path as well as inside
``gate``: an evaluation response needs durable identifiers (``run_id``, ``dataset_version``,
``dataset_digest``, ``evaluator``, ``schema_version``), a non-empty ``artifact_refs``, an
``attested`` flag, a positive ``n_examples``, and per-metric rows whose ``passed`` equals
``score >= threshold``; a gate response needs all of that inside ``eval_report``, plus a
``redteam_report`` whose aggregate matches its rows and whose every row's ``passed`` and
``blocked`` agree, durable ``model_card_ref`` and ``mrm_evidence_ref``, and a top-level
``passed`` equal to (eval passed AND attested AND red-team passed).

The refusal tests are the point, not an inconvenience: a promotion certified
by a naked ``{"passed": true}`` is a promotion certified by nothing. Every value is
obviously fictional.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

from performance_marketing.adapters.platform.remote_evaluation import (
    RemoteEvaluationAdapter,
    RemoteEvaluationError,
)
from performance_marketing.config import Settings
from performance_marketing.domain.models import EvalReport

_BASE = "https://hrz4.test"
_CONFIG_PATH = "config/settings.yaml"
_DATASET = "eval/data/golden.jsonl"
_DIGEST = "sha256:feedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedfacefeedface"

#: A MIXED result set: citation_accuracy misses its bar, so the report FAILS. Every row is
#: internally consistent, because the client re-derives each verdict from score/threshold.
_MIXED_RESULTS = [
    {"metric": "report_groundedness", "score": 0.91, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.72, "threshold": 0.90, "passed": False},
]

_PASSING_RESULTS = [
    {"metric": "report_groundedness", "score": 0.91, "threshold": 0.80, "passed": True},
    {"metric": "citation_accuracy", "score": 0.95, "threshold": 0.90, "passed": True},
]


def _evidence(**overrides: Any) -> dict[str, Any]:
    """Durable evaluation evidence in the full hardened shape, obviously fictional."""
    body: dict[str, Any] = {
        "results": _PASSING_RESULTS,
        "n_examples": 12,
        "run_id": "run-fictional-0001",
        "dataset_version": "golden@2026-08-01",
        "dataset_digest": _DIGEST,
        "evaluator": "hrz4-ai-quality (FICTIONAL)",
        "schema_version": "v1",
        "artifact_refs": ["gs://fictional-hrz4-evidence/run-fictional-0001/report.json"],
        "attested": True,
    }
    body.update(overrides)
    return body


def _gate_body(**overrides: Any) -> dict[str, Any]:
    """The complete GateDecision the promotion gate now demands."""
    body: dict[str, Any] = {
        "passed": True,
        "eval_report": _evidence(),
        "redteam_report": {
            "passed": True,
            "results": [
                {"case": "prompt-injection-01", "passed": True, "blocked": True},
                {"case": "budget-exfil-01", "passed": True, "blocked": True},
            ],
        },
        "model_card_ref": "gs://fictional-hrz4-evidence/model-cards/mkt4-performance.md",
        "mrm_evidence_ref": "gs://fictional-hrz4-evidence/mrm/mkt4-performance-2026-08.json",
    }
    body.update(overrides)
    return body


@pytest.fixture
def settings() -> Settings:
    return Settings.load(_CONFIG_PATH)


@pytest.fixture
def adapter(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> RemoteEvaluationAdapter:
    monkeypatch.setenv("HRZ_QUALITY_URL", _BASE)
    return RemoteEvaluationAdapter(settings)


@respx.mock
def test_evaluate_posts_structured_bundle_request(
    adapter: RemoteEvaluationAdapter, settings: Settings
) -> None:
    route = respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(results=_MIXED_RESULTS, passed=False))
    )

    report = adapter.evaluate(_DATASET)

    assert route.called
    body = json.loads(route.calls.last.request.content)
    target = body["target"]

    # Structured target, with the pinned model + prompt version.
    assert target["model"] == settings.models.reasoning
    assert target["prompt_version"] == "v1"
    assert target["system"] == ""

    # dataset_id is the basename without .jsonl, and the top-level id MUST match target's.
    assert target["dataset_id"] == "golden"
    assert body["dataset_id"] == target["dataset_id"]

    # Metrics are selected ONLY by bundle name — never a metric-name list anywhere.
    assert body["bundle"] == "mkt4-performance"
    assert "metrics" not in body
    assert "metrics" not in target
    assert not any(isinstance(value, list) for value in target.values())

    # The results[] body is parsed into an EvalReport.
    assert isinstance(report, EvalReport)
    assert report.dataset == _DATASET
    assert report.n_examples == 12
    assert [r.metric for r in report.results] == ["report_groundedness", "citation_accuracy"]
    assert report.results[0].passed is True
    assert report.results[1].passed is False
    assert report.passed is False  # one metric under threshold => report fails


@respx.mock
def test_evaluate_carries_the_durable_evidence_through_the_adapter(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """The attested evidence the client validated must SURVIVE the adapter.

    An adapter that rebuilds a local EvalReport from three fields (dataset, results,
    n_examples) is a lossy identity function: it drops exactly the run id, dataset
    digest, evaluator, artifact refs and attestation flag that make a score reproducible and
    auditable, and it drops them AFTER the client has gone to the trouble of refusing any
    response that lacks them. A promotion whose evidence cannot be retrieved later is a
    promotion certified by nothing, so this asserts each field individually rather than
    trusting the parse.
    """
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(200, json=_evidence()))

    report = adapter.evaluate(_DATASET)

    assert report.run_id == "run-fictional-0001"
    assert report.dataset_version == "golden@2026-08-01"
    assert report.dataset_digest == _DIGEST
    assert report.evaluator == "hrz4-ai-quality (FICTIONAL)"
    assert report.schema_version == "v1"
    assert report.artifact_refs == ("gs://fictional-hrz4-evidence/run-fictional-0001/report.json",)
    assert report.attested is True


@respx.mock
def test_evaluate_REFUSES_metric_rows_with_no_examples_behind_them(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """``all(())`` is vacuously true; a report that scored nothing must not parse."""
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(n_examples=0))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_evaluate_REFUSES_a_verdict_that_contradicts_its_score(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A row claiming PASS below its own threshold is evidence of a broken evaluator."""
    rows = [{"metric": "report_groundedness", "score": 0.10, "threshold": 0.80, "passed": True}]
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(results=rows))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_evaluate_REFUSES_evidence_with_no_durable_identifiers(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """Without a run id or an artifact ref the score is unreproducible and unauditable."""
    respx.post(f"{_BASE}/v1/evaluations").mock(
        return_value=httpx.Response(200, json=_evidence(run_id="", artifact_refs=[]))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)


@respx.mock
def test_gate_posts_to_gate_endpoint_and_returns_bool(
    adapter: RemoteEvaluationAdapter, settings: Settings
) -> None:
    route = respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=_gate_body()))

    passed = adapter.gate(_DATASET)

    assert passed is True
    assert route.called
    request = route.calls.last.request
    assert request.method == "POST"  # a POST, never a GET

    body = json.loads(request.content)
    assert body["bundle"] == "mkt4-performance"
    assert body["dataset_id"] == body["target"]["dataset_id"] == "golden"
    assert "metrics" not in body


@respx.mock
def test_gate_returns_false_through_consistent_failing_evidence(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A FAIL is reached through a failing metric row, never a contradictory body."""
    body = _gate_body(passed=False, eval_report=_evidence(results=_MIXED_RESULTS))
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    assert adapter.gate(_DATASET) is False


@respx.mock
def test_gate_REFUSES_a_naked_boolean_with_no_evidence(adapter: RemoteEvaluationAdapter) -> None:
    """The unhardened response shape. Accepting it is how a promotion gets certified by
    nothing, so the refusal is the contract."""
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json={"passed": True}))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_REFUSES_an_unattested_report_even_when_every_metric_passes(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """A laptop evaluator can score the same corpus; that is not release authority."""
    respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(eval_report=_evidence(attested=False)))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_REFUSES_a_redteam_aggregate_that_contradicts_its_rows(
    adapter: RemoteEvaluationAdapter,
) -> None:
    body = _gate_body(
        redteam_report={
            "passed": True,
            "results": [{"case": "prompt-injection-01", "passed": False, "blocked": False}],
        }
    )
    respx.post(f"{_BASE}/v1/gate").mock(return_value=httpx.Response(200, json=body))
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_gate_REFUSES_a_decision_with_no_model_card_or_mrm_reference(
    adapter: RemoteEvaluationAdapter,
) -> None:
    """Promotion evidence a model-risk reviewer cannot later retrieve is not evidence."""
    respx.post(f"{_BASE}/v1/gate").mock(
        return_value=httpx.Response(200, json=_gate_body(model_card_ref="", mrm_evidence_ref=""))
    )
    with pytest.raises(RemoteEvaluationError):
        adapter.gate(_DATASET)


@respx.mock
def test_non_2xx_raises_remote_evaluation_error(adapter: RemoteEvaluationAdapter) -> None:
    respx.post(f"{_BASE}/v1/evaluations").mock(return_value=httpx.Response(500))

    with pytest.raises(RemoteEvaluationError):
        adapter.evaluate(_DATASET)
