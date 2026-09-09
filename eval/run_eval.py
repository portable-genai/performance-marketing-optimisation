#!/usr/bin/env python3
"""Offline evaluation gate for the D4 Performance Marketing system (A4).

This is the **promotion gate**: CI runs it on every change and the build fails if the
agent's performance reports fall below the model-risk thresholds agreed for a performance-
marketing agent (see ``eval/rubrics/*.yaml``)::

    report_groundedness   >= 0.80   (every report carries citations on its figures)
    citation_accuracy     >= 0.90   (cites only computed-over / derived sources)
    attribution_accuracy  >= 0.80   (the deterministic attribution credit sums to ~1.0)
    review_safety         >= 0.99   (every report requires human review; maker-checker)

Two evaluators, one gate
------------------------
* **Production evaluator** — the **Gen AI evaluation service** on the Gemini Enterprise
  Agent Platform, wired in as ``EvaluationGatePort`` ->
  ``performance_marketing.adapters.gcp.genai_eval:GenAiEvalAdapter``. It needs GCP
  credentials. Select it with ``--use-gcp``.

* **Offline evaluator (default)** — a deterministic gate in this file. It needs **no GCP
  credentials and no Google Cloud SDK**, runs the real ``PerformanceReportService`` against
  the local (offline) adapters over the golden set, and computes the four metrics. This is
  what guards the merge in CI.

Usage::

    python eval/run_eval.py                      # offline gate (CI)
    python eval/run_eval.py --dataset path.jsonl # custom golden set
    python eval/run_eval.py --use-gcp            # route through GenAiEvalAdapter

Exit code is ``0`` iff ``EvalReport.passed`` (every metric meets its threshold).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Domain models / config are pure-stdlib + the local adapters are SDK-free, so this script
# runs in the local / on-prem / test profile with no Google Cloud SDK installed.
# The --mode smoke|gate scaffold + aligned report rendering come from the shared
# agent-eval-kit commons; this script keeps only its own offline
# evaluator and gate runner.
from agent_eval_kit import (
    assert_denominator_supports,
    assert_each_can_go_red,
    dataset_digest,
    eval_main,
    load_rubrics,
)

from performance_marketing.domain.models import (
    AttributionModel,
    EvalMetricResult,
    EvalReport,
    Market,
    PerformanceReport,
    ReportRequest,
    Vertical,
)

#: Where every bar lives. Not a dict here: a threshold written as a Python literal carries no
#: argument. The rubric files carry the reasoning beside the number, and
#: `agent_eval_kit.load_rubrics` reads them. What was here before was BOTH a dict and a loader
#: that overlaid two rubric files on top of it, falling back to the dict when PyYAML was missing.

#: The metrics this runner scores, in report order. Named so `assert_covers` can compare them
#: with the rubric set in BOTH directions.
SCORED: tuple[str, ...] = (
    "report_groundedness",
    "citation_accuracy",
    "attribution_accuracy",
    "attribution_placement",
    "review_safety",
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
RUBRICS = _REPO_ROOT / "eval" / "rubrics"
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_accounts.jsonl"


# --------------------------------------------------------------------------- #
# Golden dataset
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class GoldenExample:
    id: str
    account_id: str
    market: str
    vertical: str
    expected_requires_human_review: bool


def load_golden(path: Path) -> list[GoldenExample]:
    examples: list[GoldenExample] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise SystemExit(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        examples.append(
            GoldenExample(
                id=str(obj.get("id", f"example-{lineno}")),
                account_id=str(obj["account_id"]),
                market=str(obj["market"]),
                vertical=str(obj["vertical"]),
                expected_requires_human_review=bool(obj["expected_requires_human_review"]),
            )
        )
    if not examples:
        raise SystemExit(f"{path}: golden dataset is empty")
    return examples


def load_thresholds_from_rubrics() -> dict[str, float]:
    """Read every metric's reviewed bar out of ``eval/rubrics/*.yaml``. No fallback, by design."""
    return load_rubrics(RUBRICS).thresholds()


def journey_touchpoints() -> dict[str, set[str]]:
    """Per account, the channels that appear as a touchpoint in the SHIPPED conversion journeys.

    The independent oracle `attribution_placement` needs, and it is the shipped book rather than
    a list restated here: the touchpoints the gate measures against are the touchpoints the demo
    narrates, so a book edit moves both together instead of moving only one.
    """
    from performance_marketing import demo_book

    by_account: dict[str, set[str]] = {}
    for row in demo_book.BOOK.rows("conversion_journeys"):
        channels = by_account.setdefault(str(row["account_id"]), set())
        for touchpoint in row["touchpoints"]:
            channels.add(str(touchpoint["channel"]))
    return by_account


def score_attribution_placement(report: Any, account_id: str, touchpoints: dict) -> float:
    """Did the credit land on the channels the journeys actually contain?

    `attribution_accuracy` checks the credit shares sum to 1.0. They sum to 1.0 however the
    credit is distributed, so an attribution that gave every point to a channel appearing in no
    journey scores a perfect 1.000 there. That is arithmetic closure, and it is not attribution:
    nobody buys an attribution model because its shares add up.

    Two halves, equally weighted, failing in opposite directions: every channel receiving credit
    appears as a touchpoint in this account's journeys, and every channel that appears as a
    touchpoint receives some credit. The second is not pedantry, because a last-touch model does
    exactly that to everything before the last touch, and a channel silently given nothing is a
    channel the next budget decision will starve.
    """
    observed = touchpoints.get(account_id, set())
    attribution = getattr(report, "attribution", None)
    if attribution is None or not attribution.channels or not observed:
        return 0.0
    credited = {
        channel.channel.value for channel in attribution.channels if channel.credit_share > 0
    }
    on_journey = len(credited & observed) / len(credited) if credited else 0.0
    covered = len(credited & observed) / len(observed)
    return round((on_journey + covered) / 2.0, 4)


# --------------------------------------------------------------------------- #
# Service wiring (the real PerformanceReportService over the local offline adapters)
# --------------------------------------------------------------------------- #
def _make_service():  # type: ignore[no-untyped-def]
    from performance_marketing.api.deps import make_report_service
    from performance_marketing.config import Container, LocalSettings, Settings

    base = Settings.load(str(_REPO_ROOT / "config" / "settings.yaml"))
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
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    container = Container(settings)
    return make_report_service(container)


# --------------------------------------------------------------------------- #
# Heuristic scorers
# --------------------------------------------------------------------------- #
def score_groundedness(report: PerformanceReport) -> float:
    """A report with any computed figures must carry at least one citation."""
    has_figures = report.efficiency is not None and bool(report.efficiency.channels)
    if not has_figures:
        return 1.0
    return 1.0 if report.citations else 0.0


def score_citation_accuracy(report: PerformanceReport) -> float:
    """No cited source outside the report's own computed / derived evidence set."""
    cited = {c.source_id for c in report.citations}
    if not cited:
        return 1.0
    allowed: set[str] = set()
    if report.attribution is not None:
        for ch in report.attribution.channels:
            allowed.update(c.source_id for c in ch.citations)
    if report.efficiency is not None:
        for ch in report.efficiency.channels:
            allowed.update(c.source_id for c in ch.citations)
    if report.budget_plan is not None:
        for s in report.budget_plan.shifts:
            allowed.update(c.source_id for c in s.citations)
    for r in report.ab_results:
        allowed.update(c.source_id for c in r.citations)
    if report.anomalies is not None:
        for a in report.anomalies.anomalies:
            allowed.update(c.source_id for c in a.citations)
    return round(len(cited & allowed) / len(cited), 4)


def score_attribution_accuracy(report: PerformanceReport) -> float:
    """The deterministic attribution credit shares must sum to ~1.0 (no leaked credit)."""
    attr = report.attribution
    if attr is None or not attr.channels:
        return 0.0
    total = sum(c.credit_share for c in attr.channels)
    return 1.0 if abs(total - 1.0) <= 0.01 else 0.0


def score_review_safety(report: PerformanceReport, expected_requires_review: bool) -> float:
    """Compare with the golden maker-checker oracle, never with the output itself."""
    return 1.0 if report.requires_human_review is expected_requires_review else 0.0


def assert_review_safety_can_go_red(threshold: float) -> None:
    """Reject a future tautological safety scorer before trusting a green gate."""
    from types import SimpleNamespace

    assert_each_can_go_red(
        lambda report: score_review_safety(report, True),
        {
            "maker-checker": (
                SimpleNamespace(requires_human_review=True),
                SimpleNamespace(requires_human_review=False),
            )
        },
        threshold=threshold,
        metric="review_safety",
    )


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
@dataclass
class _PerMetric:
    scores: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0


def run_offline(dataset: Path, thresholds: dict[str, float]) -> EvalReport:
    assert_review_safety_can_go_red(thresholds["review_safety"])
    # The rubrics and the scored set must agree in BOTH directions before anything is scored.
    load_rubrics(RUBRICS).assert_covers(SCORED)
    examples = load_golden(dataset)
    service = _make_service()
    agg: dict[str, _PerMetric] = {metric: _PerMetric() for metric in SCORED}
    touchpoints = journey_touchpoints()
    produced: dict[str, int] = {"citations": 0}
    print(
        f"Running offline eval gate over {len(examples)} golden accounts "
        "(PerformanceReportService).\n"
    )
    for ex in examples:
        request = ReportRequest(
            account_id=ex.account_id,
            market=Market(ex.market),
            vertical=Vertical(ex.vertical),
            attribution_model=AttributionModel.POSITION_BASED,
        )
        report = service.build_report(request, actor="eval-bot", tenant="demo-bank")
        agg["report_groundedness"].scores.append(score_groundedness(report))
        agg["citation_accuracy"].scores.append(score_citation_accuracy(report))
        agg["attribution_accuracy"].scores.append(score_attribution_accuracy(report))
        agg["attribution_placement"].scores.append(
            score_attribution_placement(report, ex.account_id, touchpoints)
        )
        agg["review_safety"].scores.append(
            score_review_safety(report, ex.expected_requires_human_review)
        )
        produced["citations"] += len(report.citations)

    results = tuple(
        EvalMetricResult(
            metric=metric,
            score=round(agg[metric].mean, 4),
            threshold=thresholds[metric],
            passed=round(agg[metric].mean, 4) >= thresholds[metric],
        )
        for metric in SCORED
    )
    # The corpus must be able to express every bar that claims a rate. citation_accuracy's
    # denominator is the citations the reports carry, not the six accounts.
    assert_denominator_supports(
        thresholds["citation_accuracy"], produced["citations"], metric="citation_accuracy"
    )
    return EvalReport(
        dataset=str(dataset),
        results=results,
        n_examples=len(examples),
        dataset_digest=dataset_digest(dataset),
        evaluator="offline heuristic (no cloud creds)",
    )


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    """Promotion verdict via EvaluationGatePort (platform = model-quality-gate, gcp = Gen AI evals).

    Fails closed on the reconciled evaluate + gate result. Refuses to run outside the
    platform/gcp profiles so the offline smoke result is never relabelled a promotion pass.
    """
    from performance_marketing.config import Settings, build_container

    settings = Settings.load()
    if settings.profile not in ("platform", "gcp"):
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            "MKT_PERF_PROFILE=platform or gcp "
            f"(got {settings.profile!r}); run --mode smoke for the offline pre-merge check."
        )
    container = build_container(settings)
    gate = container.evaluation
    report = gate.evaluate(str(dataset))
    if not isinstance(report, EvalReport):  # pragma: no cover - defensive
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    gate_passed = bool(gate.gate(str(dataset)))
    return report, gate_passed


def main(argv: list[str] | None = None) -> int:
    """Dispatch --mode via the shared eval_main scaffold (fail-closed exit codes).

    ``--use-gcp`` (the pre-split flag for the production evaluator) is kept as an alias
    for ``--mode gate``.
    """
    args = sys.argv[1:] if argv is None else list(argv)
    if "--use-gcp" in args:
        args = [a for a in args if a != "--use-gcp"] + ["--mode", "gate"]
    return eval_main(
        smoke=lambda dataset: run_offline(dataset, load_thresholds_from_rubrics()),
        gate=run_gate,
        default_dataset=DEFAULT_DATASET,
        description="Offline / platform evaluation gate for D4 (A4 / P-08).",
        smoke_label="offline heuristic (no GCP creds)",
        gate_label="promotion gate (EvaluationGatePort: model-quality-gate / Gen AI evals)",
        argv=args,
    )


if __name__ == "__main__":
    raise SystemExit(main())
