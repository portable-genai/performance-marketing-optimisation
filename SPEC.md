# SPEC - `performance-marketing-optimisation` Performance Marketing and Attribution

## Purpose

Turn a marketing-performance metrics warehouse into a cited, auditable, maker-checker-gated
**performance report**: multi-touch attribution, ROAS / CAC efficiency, a proposed
budget-neutral reallocation, A/B significance verdicts and metric anomalies. Generic across
the **banking** and **online retail** verticals and the **JP / AU / SG** markets.

## Non-goals

- The system never moves a budget automatically. It proposes; a human disposes.
- The LLM never computes a figure, a verdict or a recommended shift. Those are deterministic.
- No bank-only logic in the domain. Banking is one configured vertical; online retail another.

## Domain objects

`Account`, `BidStrategy`, `RoasTarget`, `AttributionView`, `BudgetShift`, `AbTest`, plus the
engine result aggregates (`EfficiencyReport`, `BudgetPlan`, `AbResult`, `AnomalyReport`) and
the top-level `PerformanceReport`. `Vertical` and `Market` are enums; `Citation` carries
provenance; every market's residency region / locales come from `MARKET_PROFILES` (config +
seed).

## Deterministic engines (the heart)

1. **Multi-touch attribution** - credit split by last / first / linear / 40-20-40
   position-based model; credit conserved across channels.
2. **ROAS / CAC** - per-channel + blended, compared against the per-market + per-vertical
   target (CAC ceiling for banking, ROAS floor for retail).
3. **Bid / budget optimisation** - budget-neutral reallocation from under- to over-performers,
   ROAS-weighted, bounded by a max per-channel step.
4. **A/B significance** - pooled two-proportion z-test, two-sided p-value via stdlib `erf`,
   ship / stop / keep-running verdict at a configurable alpha, underpowered guard.
5. **Anomaly detection** - robust-z (median + MAD) spike / drop detection on a metric series.

Each engine is pure, stdlib-only, deterministic (same inputs -> same output), seedable and
unit-tested. Tunables are dataclass fields, not magic numbers.

## Ports

`MetricsPort`, `AdPlatformPort` (data feeds), `LlmPort` (narration only), `GuardrailPort`
(`agent-guardrail-gateway`), `AuditSinkPort` + `ObservabilityTracerPort` (`agent-observability`), `EvaluationGatePort` (`model-quality-gate`),
`AgentRegistryPort` + `ToolCatalogPort` (`agent-registry`). Every port is `@runtime_checkable`.

## GCP stack (headline)

BigQuery (metrics warehouse) + Vertex AI forecasting (AdPlatformPort), Gemini (narration),
Model Armor (guardrail), Cloud Logging WORM (audit), Cloud Trace (tracing), Gen AI evaluation
(`model-quality-gate`), A2A / MCP (governance). All Google imports are lazy.

## Profiles

`local` (default, SDK-free working offline stack; CI / test), `gcp` (managed), `platform`
(shared `agent-guardrail-gateway`-`agent-observability` clients), `onprem` (fail-fast migration target, exit 2).

The `platform` `model-quality-gate` promotion-gate client is a real HTTP client (not a stub): `POST
/v1/evaluations` scores the golden set and `POST /v1/gate` returns the decision, with the
metric set selected by the registered bundle name `mkt4-performance`.

## Guarantees

Provenance on every figure; `requires_human_review=True` on every report; WORM audit; region
validation against the per-market allow-list; contract test proves `local` + `onprem` satisfy
every port. Obviously-fictional synthetic data for both verticals across all three markets.

## The hard gate

`ruff check src tests` + `ruff format --check src tests` + `mypy src` +
`pytest -m 'not integration' -q` + `python eval/run_eval.py` (exit 0), in a fresh `[dev]`-only
venv with no `google-cloud-*`. The Next.js console must `npm run build` clean.
