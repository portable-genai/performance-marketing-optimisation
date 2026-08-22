# Architecture - Mkt4 Performance Marketing and Attribution

Mkt4 is a **ports-and-adapters (hexagonal)** system. The domain is pure Python (standard
library only); every external capability is a `typing.Protocol` (a port) with interchangeable
adapter families. Switching the entire managed stack to on-prem is a one-line change of
`profile`; the domain never changes.

## Layers

```
src/performance_marketing/
  domain/            pure domain - NO google/adk/fastapi imports
    models.py        Vertical/Market enums, Citation, the 6 core objects
                     (Account, BidStrategy, RoasTarget, AttributionView, BudgetShift,
                     AbTest) + engine result types + PerformanceReport aggregate
    attribution_service.py    engine 1 - multi-touch attribution
    efficiency_service.py     engine 2 - ROAS / CAC
    optimisation_service.py   engine 3 - bid / budget reallocation
    significance_service.py   engine 4 - A/B two-proportion z-test
    anomaly_service.py        engine 5 - robust-z spike / drop detection
    report_service.py         the orchestrator (composes engines + ports)
    serialization.py / errors.py
  ports/             the hexagon boundary (@runtime_checkable Protocols)
    metrics.py       MetricsPort + AdPlatformPort
    generation.py · safety.py · observability.py · governance.py · identity.py
  adapters/
    gcp/             managed stack, lazy Google imports (BigQuery, Vertex, Gemini,
                     Model Armor, Cloud Logging/Trace, Gen AI eval, A2A, MCP)
    local/           SDK-free, deterministic, seedable - the WORKING offline stack
    platform/        thin HTTP clients to the shared Hrz1-Hrz5 platform services
    onprem/          fail-fast NotImplementedError migration target
  config.py          Settings + Container (DI by dotted path, per profile)
  api/               FastAPI (import-safe, port 8103)
  cli/               Typer CLI (mkt-perf, import-safe)
```

## The deterministic core (the heart)

Every consequential figure is computed by a pure engine, unit-tested and replayable:

- **Attribution** distributes conversion + revenue credit across channels by a chosen model
  (last / first / linear / 40-20-40 position-based); credit is conserved (shares sum to 1).
- **Efficiency** computes per-channel and blended ROAS / CAC and compares each against the
  per-market + per-vertical `RoasTarget` (banking uses a CAC ceiling, retail a ROAS floor).
- **Optimisation** proposes a budget-neutral reallocation from under- to over-performers,
  weighted by ROAS and bounded by a max per-channel step.
- **Significance** runs a pooled two-proportion z-test, computing the p-value with the stdlib
  error function (no SciPy), and returns a ship / stop / keep-running verdict.
- **Anomaly** flags spikes / drops with a robust z-score (median + MAD), resistant to the
  outliers it is screening.

The **LLM only narrates** the computed result and drafts the spend-shift rationale. It never
decides a number, a verdict or a budget move.

## Cross-cutting guarantees

- **Provenance**: every figure carries a `Citation` traceable to its warehouse / experiment
  source; `to_jsonable` serialises the whole report for the API, audit and renderer.
- **Maker-checker**: `PerformanceReport.requires_human_review` is always `True`; the budget
  plan is proposed, never executed.
- **Guardrail**: input and output are screened (Hrz1); a blocked request never yields a partial
  report.
- **Audit**: every interaction is recorded WORM-style (Hrz5); blocked / escalated runs surface
  at a higher severity.
- **Residency**: the GCP adapters resolve the region from the active market and validate it
  against the per-market allow-list, so data never leaves the configured boundary.

## Profiles and the DI container

`config/settings.yaml` binds each port to a dotted `module:Class` per profile. The
`Container` builds adapters lazily on first access, so a `local` / `onprem` run never imports
`google-*`. The contract test constructs every `local` and `onprem` adapter with no GCP SDK
installed and asserts each satisfies its port Protocol.

## The Hrz4 eval gate

`eval/run_eval.py` runs the real `PerformanceReportService` over the local stack against a
golden set of accounts and scores four metrics (report groundedness, citation accuracy,
attribution accuracy, review safety) against the thresholds in `eval/rubrics/*.yaml`. CI runs
it on every change; a non-zero exit blocks promotion. The GCP `EvaluationGatePort`
(Gen AI evaluation service) mirrors the same metric names and thresholds.

In the `platform` profile the `EvaluationGatePort` is a real thin HTTP client to Hrz4's
hardened contract, not a stub: `POST /v1/evaluations` scores the golden dataset (parsing
`results[]` into the domain `EvalReport`) and `POST /v1/gate` returns the promotion decision.
Both calls send a structured `target` plus a top-level `dataset_id` and select the metric set
only by the registered bundle name `mkt4-performance`, so Hrz4 owns bundle membership and the
client never sends a metric-name list.
