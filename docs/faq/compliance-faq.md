# Compliance FAQ

For compliance, marketing-governance, and model-risk teams assessing the repo's regulatory
posture. Cross-references: [`COMPLIANCE.md`](../../COMPLIANCE.md) (the full principle-to-
control map and the MAS / ACCC / ASIC / APRA / JP crosswalk appendix),
[`SPEC.md`](../../SPEC.md).

### Is this making spend or budget decisions autonomously?

No. It is a **decision-support** agent: every consequential output requires human review
(maker-checker, P-06). The five deterministic engines produce a documented, replayable
assessment (attribution split, ROAS / CAC vs target, a budget-neutral reallocation plan, an
A/B significance verdict, an anomaly scan); a qualified human disposes of any spend shift.
Every `PerformanceReport` sets `requires_human_review=True`, and the escalation is routed to
the **Hrz7** Human-Review and Maker-Checker Console via the shared `review-kit` client
(rule R8), never left as a per-repo boolean. Severity floors at medium and rises to
dual-control on a HIGH-plus budget-shift or anomaly signal. Mkt4 never touches an ad
platform's spend controls directly.

### How is customer PII handled?

There is none to handle, by design. Mkt4 measures over **aggregate** channel and campaign
metrics (spend, impressions, clicks, conversion counts, revenue, ROAS / CAC, budgets, A/B arm
totals). There is no customer-level record in the request or the warehouse, so there is
nothing to redact and no national-identifier pattern to select by jurisdiction. The practices
audit records C3 (redact-before-everything) and C4 (jurisdiction PII packs) as N-A, and
`COMPLIANCE.md` carries a written rationale for the absent PII surface. The runtime
guardrail / DLP itself is the sibling **Hrz1** gateway, which this repo consumes rather than
re-implements.

### How is the work auditable / reproducible?

Every report writes an immutable WORM `AuditEvent` with the decision and the citation set
(P-07). Every claim-bearing figure carries a source-and-page `Citation` (P-10), and the
orchestrator raises `MetricsEmptyError` rather than emit a degraded ungrounded report
(grounded-or-fail). The consequential maths is deterministic, so an auditor can recompute any
figure or verdict from the same inputs without the model. The enterprise WORM audit system is
**Hrz5**; the in-repo hash-chained store is the offline / local stand-in (see
[security-faq.md](security-faq.md) for its exact tamper-evidence limits).

### What is the model-risk story?

An offline eval gate (`eval/run_eval.py`, `--mode smoke|gate`) guards every merge locally;
promotion is deferred to the enterprise gate. A strict safety metric (`review_safety >= 0.99`,
tied to `requires_human_review`) gates the build (P-08); a PII-safety metric is N-A (no PII
surface). Each golden row independently states the expected review requirement, and the gate
runs a planted bypass through `assert_each_can_go_red` before trusting a green score. The
enterprise promotion gate and
red-team harness are the sibling **Hrz4** system (bundle `mkt4-performance`); this repo's gate
mirrors its thresholds. A fork must rebuild the golden set for its own bundle, or the gate
measures the wrong thing.

### Which regulators does this map to?

`COMPLIANCE.md` maps the internal P-01..P-13 principles and R1..R8 dependency rules to
concrete code (an Evidence column naming real files), plus an **adopter-owned regulator
crosswalk appendix** covering the shipped home markets: MAS (Singapore, FEAT / TRM /
outsourcing), Australia (ACCC / ASIC / APRA), and Japan (fair-trade advertising), with SG
ASAS for advertising standards. To add another regulator, copy the appendix table and swap
the reference column; the Mkt4-control column is stable across regulators. At scale, the
sibling **Rsk2 control-mapping toolkit** and **Rsk1 compliance assistant** generate and
maintain these crosswalks rather than hand-maintaining the table.

### Who checks that customer-facing marketing copy is compliant?

Not this repo. Mkt4 drafts **no** customer-facing copy: the LLM only narrates internal,
already-computed figures and drafts internal spend-shift wording for a human reviewer. Any
output that becomes customer-facing must pass the sibling **Mkt6** `marketing-compliance-gate`
advertising / consumer-protection claim check (rule R7). That boundary is deliberate: the
measurement domain and the claim-check domain are separate systems.

### Is data residency enforced?

Yes, at deploy time (P-03 / P-09): a single in-country APAC region per deployment (JP
`asia-northeast1`, AU `australia-southeast1`, SG `asia-southeast1`, default
`asia-southeast1`), validated to fail fast, with regional endpoints, a `gcp.resourceLocations`
Org Policy allowlist, CMEK, a VPC-SC perimeter, and WORM logging (retention validated at
about seven years). The residency-violation CI gate is the sibling **Rsk4 residency
validator**; the exit / concentration-risk plan is **Rsk5**. This repo enforces residency in
its own `infra/terraform/` and is one of the systems those tools reason about. CI and
`make tf-validate` check format and validate the configuration without credentials; hosted
enforcement still needs deployment evidence.

### Can we run it against real spend data today?

Not without your own legal, security, and model-risk sign-off. Every fixture and seed account
is obviously-fictional (suffixed FICTIONAL, URLs at `example.test`), and the "not intended for
live use without your own sign-off" note lives in `COMPLIANCE.md`. The adoption checklist
(`docs/ADOPTING.md`) lists the steps (replace reference data, own the targets, wire your IdP,
rebuild the eval golden set) that must precede any live-data use.
