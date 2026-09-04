# Adopting this repo as your base

This repository is a **common base** for building a performance-marketing-optimisation measurement and
attribution agent: deterministic multi-touch attribution, ROAS / CAC efficiency, budget
reallocation, A/B significance, and anomaly detection over a metrics warehouse, with the LLM
confined to narrating already-computed figures. It ships a reusable hexagonal core (a
pure-stdlib domain, typed ports, swappable adapter profiles, a green offline gate) plus a
fully worked banking / online-retail vertical across the JP / AU / SG markets that you can
keep, retarget, or learn from.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical
rebrand** (one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding a port / sub-service), the
> [`faq/`](faq/) directory.

---

## 1. What you keep vs what you rewrite

The domain is layered so the boundary is explicit:

| Layer | Where | For a new vertical / domain |
|---|---|---|
| **Vertical-neutral machinery** | The stable `domain/kernel.py` import surface, `domain/serialization.py`, and the generic ports (`llm`, `guardrail`, `audit`, `tracer`, `evaluation`, `identity`, `agent_registry`, `review_router`) | keep untouched |
| **Targets / tunables (your numbers)** | `RoasTarget` seed values (config plus seed via the ad-platform adapter); the engine statistical tunables (see note below) | change by config / seed |
| **Vertical (measurement artifacts)** | The vertical section of `domain/models.py` (`PerformanceReport`, `AttributionView`, ...), the five `*_service.py` engines' domain assumptions, the narration in `report_service.py`, the local seed fixtures, the eval golden set, the UI report views | retarget or rewrite |

Two explicit adopter boundaries are tracked in [`docs/practices-audit.md`](practices-audit.md):

- `domain/kernel.py` is the stable neutral import surface and deliberately exports no
  performance aggregate.
- Engine values (`alpha`, sample size, anomaly thresholds, optimisation caps and attribution
  weights) live under validated `config/settings.yaml:policy`. `RoasTarget` values remain
  config plus seed. Treat every shipped value as a reference default requiring adopter approval.

If your product is another *measurement* domain, most of the ports and the deterministic
engine mechanics transfer directly; you retarget the numbers and rewrite the artifact models
and the narration.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): the vertical-neutral section of `domain/models.py`,
  `domain/serialization.py`, `ports/`, `tests/contract/`, the eval harness
  (`eval/run_eval.py` mechanics), CI workflows, and the hexagon wiring (`config.py`
  `Container`).
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the local seed
  fixtures, `adapters/onprem/*`, UI theming / branding, the golden eval dataset
  (`eval/datasets/`), and the `COMPLIANCE.md` regulator-crosswalk rows.

Track upstream via git tags; rebase your adopter-owned
changes onto each release rather than merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name, CLI entry point, `MKT_PERF_` env prefix,
and resource ids across the tree in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_perf_agent --cli acme-perf \
    --env-prefix ACME --resource acme-perf-attribution --dry-run

# Apply:
python scripts/rename_fork.py --package acme_perf_agent --cli acme-perf \
    --env-prefix ACME --resource acme-perf-attribution --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make gate
```

The distribution name defaults to the resource stem (this repo's distribution and resource
stem are both `performance-marketing-optimisation`); pass `--dist` to override. Add `--include-docs`
to sweep Markdown prose too. The script deliberately does NOT touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency.** Set `MKT_PERF_PROFILE` and the market, and pin the Terraform
   `region` / tfvars to your in-country region. The build ships JP (`asia-northeast1`), AU
   (`australia-southeast1`) and SG (`asia-southeast1`, the default), validated to fail fast.
   See [`docs/runbook.md`](runbook.md).
2. **Identity / IdP.** `local` uses seeded dev personas (no IdP, offline). `gcp` / `platform`
   verify the IAP-injected assertion (auth configured ON the service). `onprem` is a fail-fast
   client-IdP placeholder you implement for a sovereign deployment. There is no OIDC login
   flow in this repo to wire. See
   [`docs/embedding-and-identity.md`](embedding-and-identity.md).
3. **ROAS / CAC targets and statistical tunables.** Own the per-market / per-vertical
   `RoasTarget` values (config plus seed) with your marketing-finance function, and review the
   engine tunables (`alpha`, `z_threshold`, `max_step_fraction`, attribution weights). The
   defaults are a reference, not your policy.
4. **Reference data is fictional.** Every seed account and brand is obviously-fake (suffixed
   FICTIONAL, URLs at `example.test`). Replace the seed (`adapters/local/_seed.py`) and the
   fixtures with your own synthetic data. **Do not run against live spend data without your
   own legal, security and model-risk sign-off.**
5. **Eval golden set.** Rebuild `eval/datasets/golden_accounts.jsonl` and the rubrics for your
   bundle: a fork inherits a green gate that measures the WRONG thing until you do. The gate
   structure is generic; the golden cases are yours. Preserve the independent
   `expected_requires_human_review` oracle and planted-red proof when changing the gate.
6. **No PII pack needed.** `performance-marketing-optimisation` has no customer-PII surface (aggregate metrics only), so there
   is no redaction step and no jurisdiction pattern pack to configure (audit C3 / C4 = N-A).
   If your fork introduces customer-level data, that changes, and you must add redaction and a
   PII-safety metric before going live.
7. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root, healthcheck),
   `infra/terraform/` (Org Policy, CMEK, VPC-SC, WORM), and the loopback-by-default API bind
   before you expose anything. CI and `make tf-validate` check format and configuration
   without credentials; run a reviewed plan and residency drills before deployment.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches*
are owned by sibling platform services; integrate rather than rebuild them (see
[`docs/faq/features-faq.md`](faq/features-faq.md) for the full map): the guardrail gateway
(`agent-guardrail-gateway`), the agent registry (`agent-registry`), the AI-quality / eval gate (`model-quality-gate`),
observability plus WORM audit (`agent-observability`), the human-review / maker-checker console (`human-review-console`,
via `review-kit`), and the advertising / consumer-protection claim check (`marketing-compliance-gate`). The
`platform` profile's adapters are already thin HTTP clients to those services. Note `enterprise-knowledge-base`
(governed RAG) is deliberately NOT a dependency: `performance-marketing-optimisation` has no retrieval step (R3 is N-A).

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Set region plus Terraform tfvars to your in-country region.
- [ ] Chose your identity posture per profile (seeded personas / IAP / onprem placeholder).
- [ ] Owned the ROAS / CAC targets and reviewed the engine tunables with your function.
- [ ] Replaced the seed accounts and every synthetic fixture.
- [ ] Rebuilt the eval golden set plus rubrics for your bundle; added a planted-failure case.
- [ ] Confirmed no customer-PII surface (or added redaction plus a PII-safety metric if you did).
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address); added TF validate to CI.
- [ ] Decided which sibling platform services you integrate vs stub.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
