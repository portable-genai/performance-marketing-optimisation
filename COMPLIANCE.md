# COMPLIANCE: `performance-marketing-optimisation` Stats-based Performance Marketing and Attribution

This maps every General Principle (P-01..P-13) and dependency rule (R1..R8) to a concrete
control in **this** repo. Where a principle does not apply to `performance-marketing-optimisation`, it is marked **n/a** with
the reason. `performance-marketing-optimisation` measures over aggregate campaign metrics and no customer PII, so its
load-bearing controls are deterministic / replayable maths, provenance, maker-checker and audit.

> The account, metric and experiment data in `tests/`, `eval/` and the local seed is
> **fictional**. This build is a reference piece and is **not** intended for live use without
> your own legal, security and model-risk sign-off.

---

## General Principles

| # | Principle | How `performance-marketing-optimisation` implements it | Evidence |
|---|-----------|----------------------|----------|
| **P-01** | Managed-first, minimal surface | Only the managed services the pinned stack uses are enabled; the agent is hosted on Agent Runtime | `infra/terraform/apis.tf`, `agent/root_agent.py` |
| **P-02** | No vendor lock-in (ports and adapters) | Domain depends only on `Protocol` ports; a profile switch rebinds adapters with no domain change. The `local` family proves the same domain runs entirely off-cloud (deterministic stats and LLM, in-memory metrics, no Google Cloud SDK) | `ports/`, `config.py`, `adapters/local/*`, `adapters/onprem/*` |
| **P-03** | Data residency (in-country) | Region selected at deploy from a residency allowlist, with per-market overrides (JP / AU / SG), validated to fail fast; regional endpoints; `gcp.resourceLocations` Org Policy; VPC-SC perimeter | `config/settings.yaml` (`markets`), `infra/terraform/variables.tf`, `org_policy.tf`, `vpc_sc.tf` |
| **P-04** | Minimise data to the model | `performance-marketing-optimisation` sends aggregate campaign metrics and no per-customer PII; the model-boundary callback still guardrail-screens every prompt and response, and spans capture no content | `agent/callbacks.py`, `domain/report_service.py` |
| **P-05** | Grounding over fine-tuning | The narration and spend recommendations are grounded on the deterministically-computed report; no training on data | `domain/report_service.py`, `ports/generation.py` |
| **P-06** | Human-in-the-loop / maker-checker | Every `PerformanceReport` is `requires_human_review=True`; a human signs off before any spend is moved. The escalation is routed to the `human-review-console` maker-checker console via `review-kit` rather than terminating in a boolean (rule R8) | `domain/report_service.py`, `domain/models.py`, `ports/review_router.py`, `adapters/_review_payload.py` |
| **P-07** | Auditable and explainable by design | Every report writes a WORM `AuditEvent` with the decision and citations; the ADK after-agent callback audits again at the model boundary | `domain/report_service.py`, `adapters/gcp/cloud_logging_audit.py`, `agent/callbacks.py` |
| **P-08** | Eval-gated promotion | Offline eval gate scores attribution / significance accuracy and review safety; `model-quality-gate` at promotion | `eval/run_eval.py`, `ports/observability.py` (`EvaluationGatePort.gate`) |
| **P-09** | Defense in depth / zero trust | CMEK, least-privilege IAM, private endpoints, a distinct agent identity; the guardrail screens twice (domain pipeline and model-boundary callback) | `infra/terraform/kms.tf`, `iam.tf`, `agent/callbacks.py` |
| **P-10** | Provenance on every claim | Every consequential figure (attribution credit, ROAS / CAC, recommended shift, significance) carries a source-and-page `Citation`; the model only narrates computed numbers | `domain/models.py` (`Citation`), `domain/attribution_service.py` |
| **P-11** | Cost and latency control | A small triage-tier model handles routing / pre-checks; the reasoning model only narrates the already-computed report | `config.py` (`ModelSettings.triage`) |
| **P-12** | Reversibility / documented exit | The `local` adapters run the whole pipeline off-cloud today (the working proof), and the `onprem` placeholders satisfy the same Protocols as the fail-fast sovereign target; the contract test proves parity for both | `adapters/local/*`, `adapters/onprem/*`, `tests/contract/test_port_parity.py`, `docs/onprem-migration.md` |
| **P-13** | Fair, consented marketing (advertising compliance) | `performance-marketing-optimisation` produces internal measurement and spend recommendations, not published advertising; any output that becomes customer-facing must pass `marketing-compliance-gate` (rule R7). The agent does not draft customer-facing copy | `agent/root_agent.py` instruction, R7 below |

---

## Dependency rules

`performance-marketing-optimisation`'s mandatory dependencies are **`agent-guardrail-gateway`, `agent-registry`, `model-quality-gate` (gate), `agent-observability` and `campaign-planner`** (see `systems/`).
Each platform rule is satisfied by consuming the sibling service through a `platform` adapter
(with an on-prem stub), never by re-implementing the concern.

| Rule | Requirement | How `performance-marketing-optimisation` satisfies it | Evidence |
|------|-------------|---------------------|----------|
| **R1** | Customer PII handling: `agent-guardrail-gateway` + DLP redaction | `performance-marketing-optimisation` consumes the `agent-guardrail-gateway` for prompt-injection and unsafe-output screening (INPUT and OUTPUT, pipeline and model boundary). **PII redaction is n/a**: `performance-marketing-optimisation` measures over aggregate campaign metrics with no per-customer record (C2/C3/C4 n/a in the practices audit) | `ports/safety.py`, `domain/report_service.py`, `agent/callbacks.py` |
| **R2** | Audit to `agent-observability` | Every report writes an immutable WORM `AuditEvent`; the `platform` adapter posts to `agent-observability` `/v1/audit` | `adapters/gcp/cloud_logging_audit.py`, `adapters/platform/remote_audit.py` |
| **R3** | Governed RAG via `enterprise-knowledge-base` | **n/a**: `performance-marketing-optimisation` has no RAG step; it measures over BigQuery metrics and statistical models. `enterprise-knowledge-base` is not a dependency | metrics via `ports/metrics.py` |
| **R4** | Register in `agent-registry` | The A2A AgentCard is published at `/.well-known/agent-card.json` and resolvable via `agent-registry`; the governed MCP tool catalog scopes access least-privilege | `agent/agent_card.py`, `api/app.py`, `adapters/platform/remote_registry.py`, `adapters/gcp/mcp_tool_catalog.py` |
| **R5** | `model-quality-gate` promotion gate | `EvaluationGatePort.gate` checks the `model-quality-gate` thresholds before promotion; the offline gate guards merges | `ports/observability.py`, `adapters/platform/remote_evaluation.py`, `eval/run_eval.py` |
| **R6** | Validated by `architecture-validator` at intake | As a new project, `performance-marketing-optimisation` is validated by the `architecture-validator` intake validator externally. n/a in-repo | intake handled by `architecture-validator` externally |
| **R7** | Marketing compliance via `marketing-compliance-gate` | `performance-marketing-optimisation` produces internal measurement and spend recommendations, not published advertising. Any output that becomes customer-facing must pass `marketing-compliance-gate` (advertising / consumer-protection claim check) and screen via `agent-guardrail-gateway` | `agent/root_agent.py` instruction; `marketing-compliance-gate` governance |
| **R8** | Route consequential escalations to `human-review-console` | A `PerformanceReport` sets `requires_human_review=True`, so after it is audited it is routed to the `human-review-console` Human-Review & Maker-Checker Console through the shared `review-kit` client, never left as a per-repo boolean. The adapter redacts the subject / summary / citation snippets for universal identifiers before the wire (defensive; D4 carries no per-customer PII) and carries the object-level-authorization tenant verified at the build boundary (C2). Severity floors at medium and rises to dual-control on a HIGH+ budget-shift or anomaly signal. Routing is best-effort: a console outage never fails an already-audited report | `ports/review_router.py`, `adapters/_review_payload.py`, `adapters/{local,platform,onprem}/review_router.py`, `domain/report_service.py` |

---

## Why `performance-marketing-optimisation` has no per-customer PII surface (R1, C2..C4)

- **Aggregate inputs only.** A report is built from channel-level metrics, conversion journeys
  and experiment results, all aggregate. There is no customer identifier and no
  tenant-partitioned customer data. The practices audit records C2/C3/C4 as **n/a by design**.
- **The guardrail still runs, twice.** The `agent-guardrail-gateway` screens INPUT and OUTPUT inside the
  domain pipeline and again at the ADK model boundary, catching prompt injection and unsafe
  output even though there is no PII to redact.
- **Determinism where it counts (P-10).** Attribution credit, ROAS / CAC, the recommended bid /
  budget shift, A/B significance and anomaly detection are all computed by pure code; the model
  only narrates and recommends, so every figure is replayable and traceable.
- **Maker-checker on a consequential output (P-06).** A spend recommendation moves money, so it
  always requires human review before anyone acts on it.

---

## Appendix: regulator crosswalk (adopter-owned)

The `P-*` / `R*` catalog above is this build's internal control language; a regulated adopter
maps it onto its own supervisor's requirements. The rows below are a **reference mapping** for
the home markets (JP / AU / SG); a fork adds a column per additional regulator. This appendix
is *adopter-owned*: a template, not legal advice.

| `performance-marketing-optimisation` control | Reference regime | What a supervisor looks for |
|---|---|---|
| P-06 maker-checker; P-10 determinism | MAS FEAT (Accountability) | A qualified human disposes of every spend recommendation; the maths is replayable |
| P-07 WORM audit; P-10 provenance | MAS TRM (auditability); record-keeping | Immutable, reproducible records; every figure traceable |
| P-13 / R7 marketing compliance | SG ASAS; AU ACCC / ASIC; JP fair-trade advertising | Any customer-facing output passes an advertising / consumer-protection claim check |
| P-03 residency; P-12 exit | MAS Outsourcing / Cloud guidelines | In-country data residency and a demonstrable exit / portability plan |
| P-08 quality / model-risk gate | MAS FEAT; model-risk expectations | A promotion gate with attribution-accuracy / safety metrics and model documentation |

**To add another regulator**: copy this table, replace the reference column with that
supervisor's instrument and section numbers, and re-review the third column with local
counsel. The `performance-marketing-optimisation`-control column is stable across regulators; only the mapping changes. The
sibling **the cloud control-mapping toolkit control-mapping toolkit** and **`compliance-advisory`** generate and
maintain these crosswalks at scale.
