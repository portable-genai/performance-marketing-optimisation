# `performance-marketing-optimisation` - Performance Marketing and Attribution (`performance-marketing-optimisation`)

**Industries:** Retail & e-commerce, Banking, Travel & hospitality, Gaming, D2C / subscription, Telecom

Stats-based performance marketing and attribution, built **ports-and-adapters** on the
Gemini Enterprise Agent Platform. The deterministic engines are the heart of the system:
**multi-touch attribution**, **ROAS / CAC**, **bid / budget optimisation**, **A/B
significance** and **anomaly detection** are all pure, replayable statistics that an analyst
(or an auditor) can re-run to the identical answer. The **LLM only narrates** the result and
drafts the spend-shift recommendation; it never decides a number, a verdict or a budget move.

`performance-marketing-optimisation` is **generic and APAC**:

- **Two verticals as config + seed**: `banking` and `online_retail` are first-class
  configurable verticals. No bank-only logic is baked into the domain; banking is one
  vertical, online retail is another, each with its own seed data and ROAS / CAC targets.
- **Three markets as config + seed**: Japan (`asia-northeast1`), Australia
  (`australia-southeast1`) and Singapore (`asia-southeast1`). Residency region, locales
  (ja + en) and per-market targets come from the per-market profiles, never a hard-coded
  branch. Adding a market is a config + seed change, not a code change.

Every figure that leaves the system carries a `Citation`; every performance report sets
`requires_human_review=True` (maker-checker); the audit is WORM-style; the contract test
asserts the `local` and `onprem` adapter families satisfy every port Protocol.

## Architecture (ports and adapters)

```
                +-----------------------------------------------+
                |                  domain (pure)                |
   CLI  ─────▶  |  PerformanceReportService  +  5 engines:      |  ◀───── API (FastAPI)
   mkt-perf     |   attribution · efficiency · optimisation ·   |        :8103
                |   significance · anomaly                      |
   UI (Next.js) |  models · Citation · Vertical/Market enums    |
        ─────▶  |  PerformanceReport (requires_human_review)    |
                +------------------------▲----------------------+
                                         │ Protocols (ports)
        MetricsPort · AdPlatformPort · LlmPort · GuardrailPort · AuditSinkPort ·
        ObservabilityTracerPort · EvaluationGatePort · AgentRegistryPort · ToolCatalogPort ·
        IdentityPort
                                         │
        ┌────────────────┬──────────────┴───────────────┬────────────────┐
     gcp (lazy)        local (default)               platform           onprem
     BigQuery,         SDK-free, deterministic,      thin HTTP clients   fail-fast
     Vertex AI,        seedable, offline; the        to `agent-guardrail-gateway`-`agent-observability` shared     NotImplementedError
     Gemini, Model     WORKING stack used by CI      platform services   migration target
     Armor, Cloud      and tests                                         (exit 2)
     Logging/Trace
```

Switching the entire managed stack to on-prem is a one-line change of `profile`
(`MKT_PERF_PROFILE=onprem`); nothing in `src/performance_marketing/domain` changes.

## The deterministic engines

| Engine | What it computes (pure stdlib, unit-tested) |
| --- | --- |
| `AttributionService` | Multi-touch credit split across channels (last/first/linear/40-20-40 position-based) |
| `EfficiencyService` | Per-channel + blended ROAS / CAC vs the per-market + per-vertical target |
| `OptimisationService` | Budget-neutral reallocation from under- to over-performers, bounded per step |
| `SignificanceService` | Two-proportion z-test, p-value (stdlib `erf`), ship / stop / keep-running verdict |
| `AnomalyService` | Robust-z (median + MAD) spike / drop detection on a metric series |

## Profiles

- **`local`** (default, dev/test/CI): a WORKING offline stack - SDK-free, deterministic,
  seedable. No `google-cloud-*` required.
- **`gcp`**: the managed stack (BigQuery, Vertex AI forecasting, Gemini, Model Armor, Cloud
  Logging WORM, Cloud Trace, Gen AI evaluation). All Google imports are lazy.
- **`platform`**: thin HTTP clients delegating to the shared `agent-guardrail-gateway`-`agent-observability` services. The `model-quality-gate`
  promotion-gate client is a real HTTP client (`POST /v1/evaluations` + `POST /v1/gate`,
  metric set chosen by the registered bundle `mkt4-performance`), not a stub.
- **`onprem`**: fail-fast `NotImplementedError` stubs satisfying the same Protocols
  (exit-portability proof).

## Quick start (offline, no cloud)

```sh
make install                 # 3.14 venv + [dev] only (NO google-cloud-*)
make gate                    # ruff + mypy + pytest + eval, all on the local profile
MKT_PERF_PROFILE=local .venv/bin/mkt-perf report acct-sg-banking -m SG -v banking
MKT_PERF_PROFILE=local .venv/bin/mkt-perf report acct-au-online_retail -m AU -v online_retail
```

The API runs on port **8103**; the thin Next.js console is in `ui/`. See `DEMO.md` for the
local (offline) demo and the GCP demo, region + vertical selectable.

## Identity and embedding

Identity is **server-verified**: every API route depends on a `Principal` resolved by the
`IdentityPort` for the active profile, and the audit actor is taken from that verified
`Principal`, never from the request body. In `local` the identity is a seeded dev persona
selected by the `X-Dev-Persona` header (`GET /v1/personas` lists them, the first is the
default, an unknown id is a 401); in `gcp`/`platform` the backend verifies the IAP-injected
assertion; in `onprem` the placeholder fails fast. The UI drops into a host app same-origin
(reverse proxy + `NEXT_PUBLIC_EMBED=1`) or runs standalone, with CSP `frame-ancestors` and a
per-tenant CORS allowlist (never `"*"`). Full client integration guide:
[`docs/embedding-and-identity.md`](docs/embedding-and-identity.md).

## The hard gate

Green before any change lands, in a fresh `[dev]`-only venv (no `google-cloud-*`):

```sh
ruff check src tests
ruff format --check src tests
mypy src
pytest -m 'not integration' -q
python eval/run_eval.py            # exit 0
```

All figures are **obviously-fictional synthetic data** for both verticals across all three
markets.
