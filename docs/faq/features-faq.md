# Features FAQ

For product, compliance, and delivery teams: what this agent does, what is deterministic vs
LLM, and, importantly, where its responsibilities **stop** and a sibling catalog system takes
over. Cross-references: [`README.md`](../../README.md), [`DEMO.md`](../../DEMO.md),
[`ARCHITECTURE.md`](../../ARCHITECTURE.md).

### What does `performance-marketing-optimisation` actually produce?

A cited **performance report** for a marketing account in a given market and vertical. From
the account's channel metrics and conversion journeys it produces: a multi-touch attribution
credit split, per-channel and blended ROAS / CAC against the per-market and per-vertical
target, a budget-neutral reallocation plan, an A/B significance verdict, and an anomaly scan
over a metric series. Every consequential figure carries a source-and-page `Citation`, the
report is written to a WORM audit trail, and it always sets `requires_human_review=True` so a
human signs off before any spend is moved.

### What is deterministic vs done by the LLM?

The consequential math is **deterministic and replayable** (pure stdlib, unit-tested): the
five engines are `AttributionService` (last / first / linear / position-based 40-20-40 credit
split, credit conserved), `EfficiencyService` (ROAS / CAC), `OptimisationService`
(budget-neutral reallocation, bounded per step), `SignificanceService` (two-proportion
z-test, p-value via stdlib `math.erf`, no SciPy), and `AnomalyService` (robust-z / MAD spike
and drop detection). The LLM only **narrates** the already-computed report and **drafts** the
spend-shift wording; it never decides a number, a verdict or a budget move. An analyst or an
auditor can recompute every figure without the model. This is the "deterministic domain
service" pattern.

### Is anything auto-executed against ad spend?

No. Every `PerformanceReport` sets `requires_human_review=True` (maker-checker, P-06); the
agent proposes a spend shift and a qualified human disposes. The escalation is routed to the
`human-review-console` via the shared `review-kit` client (rule
R8), never left as a per-repo boolean; severity floors at medium and rises to dual-control on
a HIGH-plus budget-shift or anomaly signal. `performance-marketing-optimisation` never touches an ad platform's spend controls
directly.

### Which capabilities does this repo own vs integrate from the catalog?

This is one system in a catalog of composable GRC systems. It **owns** the performance
measurement and attribution domain logic and its outputs. It **integrates** (via the
`platform` profile's thin HTTP adapters) several cross-cutting concerns owned by sibling
systems; do not rebuild these in a fork:

| Concern | Owned by (catalog id / repo) | `performance-marketing-optimisation`'s role |
|---|---|---|
| Runtime guardrail: prompt-injection / jailbreak defense, unsafe-output screen | `agent-guardrail-gateway` | consumes it on every report (input and output, pipeline and model boundary) |
| Agent registry, versioning, identity, entitlements | `agent-registry` | publishes its A2A AgentCard at `/.well-known/agent-card.json` for discovery |
| AI-quality / eval / model-risk promotion gate | `model-quality-gate` | its eval metrics gate promotion (bundle `mkt4-performance`); the offline gate mirrors it |
| Observability + immutable WORM audit | `agent-observability` | writes audit events to it; traces spans through it |
| Human-review / maker-checker console | `human-review-console` (via `review-kit`) | routes every `requires_human_review` report to it (R8) |
| Advertising / consumer-protection claim check on customer-facing copy | `marketing-compliance-gate` | any output that becomes customer-facing must pass it (R7); `performance-marketing-optimisation` drafts no customer-facing copy |

So the guardrail, audit sink, eval platform and review console are *dependencies*, not
features of this repo. Note `enterprise-knowledge-base` (governed RAG / knowledge base) is **not** a dependency:
`performance-marketing-optimisation` has no retrieval step, it measures over BigQuery metrics and statistical models (R3 is
n/a).

### Why is there no per-customer PII in the outputs?

By design. `performance-marketing-optimisation` measures over **aggregate** channel and campaign metrics (spend, impressions,
clicks, conversion counts, revenue, ROAS / CAC, budgets, A/B arm totals). There is no
customer-level record in the request or the warehouse, so there is nothing to redact and no
national-identifier pattern to select by jurisdiction. The practices audit records C3 / C4 as
N-A for this reason. See [compliance-faq.md](compliance-faq.md).

### Is it bank-only? Can I use it for retail or another vertical?

It is generic and APAC. `banking` and `online_retail` are first-class configurable verticals,
and Japan (`asia-northeast1`), Australia (`australia-southeast1`) and Singapore
(`asia-southeast1`) are configurable markets; residency region, locales and ROAS / CAC targets
come from the per-market profiles as config plus seed, never a hard-coded branch. Adding a
market or a vertical is a config plus seed change, not a code change. To adapt the engines for
a different measurement domain, see [`docs/ADOPTING.md`](../ADOPTING.md).

### How do I see it working?

`make demo` runs the offline report flow under `MKT_PERF_PROFILE=local` (the real
`PerformanceReportService`, no cloud and no API key) and renders a static audit-first HTML
view into `scripts/out`; `make demo-server` is a live, presenter-controlled offline server.
`DEMO.md` documents both, region and vertical selectable. Everything runs on
obviously-fictional synthetic data for both verticals across all three markets.
