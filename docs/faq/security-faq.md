# Security FAQ

For an application-security team reviewing this repo before adopting it as a base. Answers
reflect the current code. Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`COMPLIANCE.md`](../../COMPLIANCE.md),
[`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### How is a request authenticated? Can a client spoof its identity?

No. Identity is resolved **server-side** from the transport context by an `IdentityPort`
adapter (`api/security.py`), never from the request body. The request schemas
(`api/schemas.py`) carry no `actor` field, and any client-asserted actor or ACL is
discarded. The audit actor and the entitlement principals both come from the verified
`Principal`. Per profile: `local` = seeded dev personas (no IdP / AD / LDAP, offline only),
`gcp` / `platform` = the IAP-injected signed assertion verified server-side, `onprem` = a
fail-fast client-IdP placeholder. There is no OIDC login flow in this repo to harden (C8 is
N-A): a secure deployment is fronted by IAP, so there is no password or code exchange here.
`test_api_identity.py` proves an unknown persona is 401 and the recorded actor is the
verified subject.

### How is object-level authorization (multi-tenant isolation) enforced?

An `Account` carries a `tenant` tag, and
`build_report(request, *, actor, tenant)` gates it **fail-closed**: an account owned by a
different tenant raises `AuthorizationError` (the API maps it to 403) before any report is
built, narrated or audited. The requested `account_id` alone never grants access; the route
and the agent tool pass the verified principal's tenant, not a value from the body. Proven
RED-before by `test_cross_tenant_account_is_denied` (domain) and
`test_cross_tenant_persona_is_403` (HTTP), with same-tenant complements so the gate is not
over-broad. Exposure was bounded to begin with (aggregate channel metrics, no per-customer
records), but the isolation contract is now enforced rather than assumed.

### Is there customer PII to protect in this repo?

No, by design. `performance-marketing-optimisation` measures over **aggregate** channel and campaign metrics (spend,
impressions, clicks, conversion counts, revenue, ROAS / CAC, budgets, A/B arm totals). There
is no customer-level record in the request or the warehouse, so there is nothing to redact
and no national-identifier pattern to select by jurisdiction. The practices audit records
C3 (redact-before-everything) and C4 (jurisdiction PII packs) as N-A for this reason, and
the pipeline has, and needs, no redaction step. See
[compliance-faq.md](compliance-faq.md).

### What about the service-to-service calls in the `platform` profile?

The one real outbound call today is the `model-quality-gate` eval client, re-based on the shared
`PromotionGateClient` from `hex-service-kit`: it requires an `https://` base URL outside
loopback (rejected at construction by the fail-closed base-URL guard) and attaches an S2S
bearer credential. The remaining platform delegates (guardrail, audit, registry) are phase
stubs at this build; wire and review them before you rely on the `platform` profile in
anger. The receiving platform services own their own verification.

### What HTTP security headers are set? (Be honest about gaps.)

Partial today, and tracked as such (audit check C6 = PARTIAL). Both the API middleware
(`api/app.py`) and the UI (`ui/next.config.mjs`) emit CSP `frame-ancestors` plus
`X-Frame-Options` (anti-clickjacking). **Not yet set:** `X-Content-Type-Options: nosniff`,
`Referrer-Policy`, HSTS on the API, and a full UI CSP (`default-src 'self'` with a scoped
`connect-src`). A fork hardening for production should close these; they are a documented
gap, not a silent one.

### Is the demo / dev server safe? Does anything bind 0.0.0.0 by default?

Under the `local` profile the API and `make run-api` bind **loopback (127.0.0.1)** by
default (`API_HOST ?= 127.0.0.1` in the Makefile). CORS is an explicit
`MKT_PERF_CORS_ORIGINS` allowlist and is **never** `*`; the localhost dev-origin fallback is
restricted to the `local` profile, so a secure deploy that forgets to set the allowlist
trusts nothing cross-origin (fail-closed, C5). The offline demo server
(`scripts/demo_server.py`) is presenter-controlled and clearly dev-only.

### How tamper-evident is the audit trail? What are its limits?

The `local` audit store (`LocalAppendOnlyAuditAdapter`) wraps the shared
`hex_service_kit.audit.HashChainedAuditLog`: a SHA-256 hash chain
over canonical JSON, SQLite `UPDATE` / `DELETE` triggers enforcing append-only, a
`verify_chain()` integrity check, and JSONL export / restore. Proven by
`tests/unit/test_audit_chain.py`. The module states its honest limits: a bare chain carries
no secret, so it cannot by itself detect a full rewrite or tail truncation; in production the
`gcp` profile writes to a locked WORM bucket, which provides non-rewritability. This repo
does **not** replace the platform audit system (`agent-observability`); see
[features-faq.md](features-faq.md) for the boundary.

### Supply chain: are dependencies pinned and scanned?

Yes (D1 / D2). Committed lockfiles
(`requirements-dev.lock`, `requirements-gcp.lock`, uv pip compile, py3.12) are installed in
CI and the Docker build; the shared commons are pinned by git tag with exact SHAs in the
locks; the base image is digest-pinned; GitHub Actions are SHA-pinned; `.github/dependabot.yml`
proposes bumps; and a CI job runs `pip-audit` (on the lockfiles) plus `npm audit` (on the
UI) as hard gates. `ruff` is pinned exactly so the formatter never drifts from CI.

### Where are secrets? Are any committed?

No secret values are in the repo. `config/settings.yaml` stores only the **names** of env
vars and non-secret ids (`grep -riE "secret|token|password|api_key" config/` finds no
literal secret material), and values are read at construction time. Every fixture and seed
account is obviously-fictional (suffixed FICTIONAL, URLs point at `example.test`).

### What is explicitly out of scope / a residual risk?

- The security-header baseline is partial (nosniff, Referrer-Policy, HSTS, full UI CSP still
  to add).
- The `platform` delegates other than the `model-quality-gate` eval client are phase stubs.
- The hash chain needs the WORM bucket (or an external anchor) to resist truncation.
- The `onprem` adapters are fail-fast placeholders, not a built sovereign stack.
- This is a reference build: run your own pen-test, threat model, and model-risk review
  before any live-data deployment.
