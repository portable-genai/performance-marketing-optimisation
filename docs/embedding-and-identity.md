# Embedding and Identity: client integration guide (D4 performance-marketing-optimisation)

This guide shows how an enterprise client runs the D4 Performance Marketing and Attribution
agent and, when desired, embeds its UI inside an existing web application with secure single
sign-on (SSO) so users never see a second login. It is grounded in what this repository
implements today.

The agent ships as two cooperating pieces:

- **Backend**: a FastAPI service (default port `8103`) exposing the report endpoint
  (`POST /v1/report`), health (`GET /healthz`), and the seeded persona list
  (`GET /v1/personas`).
- **UI**: a thin Next.js console (default port `3000`) that calls the backend and renders the
  cited performance report. `NEXT_PUBLIC_EMBED=1` drops the app-level chrome
  (`ui/app/layout.tsx`); the UI base path, API base, and framing policy are build-time env
  vars (`ui/next.config.mjs`, `ui/lib/api.ts`).

The single invariant, preserved across every shape: **the server never trusts a
client-asserted actor or ACL.** `get_principal` (`src/performance_marketing/api/security.py`)
builds a `RequestContext` from inbound headers only, asks the active `IdentityPort` adapter to
resolve a verified `Principal`, and a failure is a hard 401. Each route receives
`actor=principal.actor` from that verified `Principal`; there is no request-body `actor` field
a caller could set.

---

## 1. The three deployment shapes

Pick the cheapest shape the host can actually satisfy.

| # | Shape | Use when the host... | Host work | Isolation | Identity |
|---|-------|----------------------|-----------|-----------|----------|
| 1 | **Embedded, same-origin reverse-proxy iframe** | controls its own edge (nginx / Next.js rewrites) and can federate its IdP into Cloud IAP (WIF). | Two proxy routes (`/agent/*`, `/agent/api/*`) plus one `<iframe src="/agent/">`. | iframe = hard CSS / JS isolation; same-origin (first-party, no CORS, no third-party cookies). | IAP-verified `x-goog-iap-jwt-assertion`; the proxy forwards the header. |
| 2 | **Standalone behind Cloud IAP** | has no host app, or wants a separate console at its own URL. | DNS + HTTPS LB + IAP. | Top-level app (not framed); `frame-ancestors 'self'`. | IAP-verified assertion; IAP + WIF gives SSO. |
| 3 | **Local dev, no auth** | is evaluating offline, no IdP. | None. | N/A (offline). | Seeded personas via `X-Dev-Persona` (`adapters/local/identity.py`). |

**Host-fit summary.** Controls-edge and GCP-aligned -> shape 1. No host app -> shape 2. Offline
eval -> shape 3.

---

## 2. Shape 3: run locally, no auth

Local mode (`MKT_PERF_PROFILE=local`, which must be named deliberately) runs the entire
pipeline offline:
deterministic seeded metrics, deterministic engines, a deterministic LLM, and **no IdP, AD, or
LDAP**. Identity is resolved from a small set of seeded dev personas
(`adapters/local/identity.py`) selected by an `X-Dev-Persona` request header, with the first
persona as the default.

```bash
# Backend (repo root)
export MKT_PERF_PROFILE=local
make run-api                      # uvicorn on http://localhost:8103

# UI (in ./ui)
# no .env.local needed: NEXT_PUBLIC_API_BASE already defaults to http://localhost:8103
npm install && npm run dev        # http://localhost:3000
```

The UI fetches `GET /healthz`, and when `profile === "local"` it fetches `GET /v1/personas` and
sends the chosen id as `X-Dev-Persona`. The seeded personas deliberately span different
entitlements and tenants (including a cross-tenant persona) so per-user and per-tenant
authorization is demoable offline:

| Persona id | Subject | Tenant | Entitlement principals |
|-----------|---------|--------|------------------------|
| `analyst` | `demo.analyst@bank.example` | `demo-bank` | `group:perf-analyst`, `group:marketing` |
| `approver` | `demo.approver@bank.example` | `demo-bank` | `group:perf-analyst`, `group:marketing`, `group:perf-lead` |
| `auditor` | `demo.auditor@bank.example` | `demo-bank` | `group:audit` |
| `other-tenant` | `user@other-tenant.example` | `other-bank` | `group:perf-analyst` |

```bash
curl -s http://localhost:8103/v1/personas | jq .

# Default persona (no header): the audit actor is demo.analyst@bank.example
curl -s -X POST http://localhost:8103/v1/report \
  -H 'Content-Type: application/json' \
  -d '{"account_id":"acct-sg-banking","market":"SG","vertical":"banking"}' | jq .

# Selected persona: the audit actor becomes demo.auditor@bank.example
curl -s -X POST http://localhost:8103/v1/report \
  -H 'Content-Type: application/json' -H 'X-Dev-Persona: auditor' \
  -d '{"account_id":"acct-sg-banking","market":"SG","vertical":"banking"}' | jq .

# Unknown persona: rejected with 401 (never silently anonymous)
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8103/v1/report \
  -H 'Content-Type: application/json' -H 'X-Dev-Persona: nope' \
  -d '{"account_id":"acct-sg-banking","market":"SG","vertical":"banking"}'   # -> 401
```

In secure profiles `X-Dev-Persona` is ignored entirely (Section 4), and `GET /v1/personas`
returns an empty list outside `local`, so leaving persona-selection code in the UI is harmless
in production.

---

## 3. Shape 1: embed via same-origin reverse proxy

This is the smallest change for a host that controls its edge: serve the agent **under your own
origin** at a sub-path (for example `/agent/`) via a reverse proxy, then drop an iframe pointing
at that same-origin path. Because the iframe is first-party, there are no third-party-cookie
issues and no CORS to configure. The client owns exactly two things: **a proxy route** and **an
iframe tag**.

### 3a. Reverse-proxy `/agent/*` to the agent service

**nginx**:

```nginx
# On https://portal.client.com
location /agent/ {
    proxy_pass         http://agent-ui.internal:3000/;      # the Next.js UI
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
}

# The UI's API calls (NEXT_PUBLIC_API_BASE=/agent/api) also resolve same-origin:
location /agent/api/ {
    proxy_pass         http://agent-backend.internal:8103/;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Forwarded-Proto $scheme;
    # IAP runs in front of this origin, so the x-goog-iap-jwt-assertion header is present on
    # the inbound request and forwarded through to the backend.
}
```

**Next.js host app** (if the parent is itself Next.js, use `rewrites()` in its own config):

```js
// next.config.mjs of the PARENT app
const nextConfig = {
  async rewrites() {
    return [
      { source: "/agent/api/:path*", destination: "http://agent-backend.internal:8103/:path*" },
      { source: "/agent/:path*",     destination: "http://agent-ui.internal:3000/:path*" },
    ];
  },
};
export default nextConfig;
```

### 3b. Mount the agent UI under the sub-path and hide its chrome

```bash
# Environment for the agent UI (build-time)
NEXT_PUBLIC_BASE_PATH=/agent            # mount the UI (and assets) under the sub-path
NEXT_PUBLIC_API_BASE=/agent/api         # same-origin API calls (no CORS needed)
NEXT_PUBLIC_EMBED=1                     # hide the UI's own header chrome when embedded
NEXT_PUBLIC_FRAME_ANCESTORS="https://portal.client.com"  # who may frame the UI document
```

### 3c. The iframe tag (host page)

```html
<!-- On https://portal.client.com, inside your existing page -->
<iframe
  src="/agent/"
  title="Performance Marketing Agent"
  style="width:100%; height:100%; border:0;"
  loading="lazy">
</iframe>
```

**Height caveat.** `height:100%` renders correctly only inside a host container that already has
a fixed pixel height; there is no child-to-parent resize message today, so give the iframe a
sized container.

### 3d. Allow the parent origin to frame the UI

Two layers emit the anti-clickjacking policy, because two different documents are involved:

- **The FastAPI backend** emits `Content-Security-Policy: frame-ancestors <MKT_PERF_FRAME_ANCESTORS>`
  via middleware (`api/app.py`), and adds `X-Frame-Options` for the two policies the legacy
  header can express: `SAMEORIGIN` for `'self'` and `DENY` for `'none'`. It cannot express a
  multi-origin allowlist, so none is sent there and CSP owns the multi-origin case.

  `MKT_PERF_FRAME_ANCESTORS` is read in three states, because a variable you emptied is a
  configuration and not an omission:

  | State | Result |
  |-------|--------|
  | unset | `frame-ancestors 'self'` plus `X-Frame-Options: SAMEORIGIN` (the shipped default). |
  | set and empty | `frame-ancestors 'none'` plus `X-Frame-Options: DENY`, and a warning is logged. Emptying the allowlist means nobody may frame this, so it tightens; it never inherits the unset default. |
  | set to origins | Exactly those origins, whitespace normalised. |

  Before this rule, an empty value went straight into the header, so the response carried
  `frame-ancestors` with an empty directive that browsers discard as a parse error, and the
  `X-Frame-Options` fallback was skipped as well: the clickjacking control disappeared with
  no sign that it had.
- **The Next.js console** emits the same three states of `frame-ancestors` (and the same
  conditional `X-Frame-Options`) from `ui/lib/csp.mjs`, driven by
  `NEXT_PUBLIC_FRAME_ANCESTORS`. This matters because `frame-ancestors` is only honored on the
  HTTP response of the **document the browser actually frames**, which is the console document;
  a CSP on the API/JSON response does not govern framing of the console. The console's read
  deliberately mirrors the service's, including the empty-means-`'none'` rule: two halves of one
  embedding posture that disagree about what an emptied allowlist means are worse than either
  answer, because the deployment that lost the variable becomes indistinguishable from the one
  that locked itself down on purpose.

### 3e. The console's full Content-Security-Policy

`frame-ancestors` is an anti-clickjacking control and nothing more. For a period the console
document shipped it as its ONLY directive: no `default-src`, no `script-src`, no `object-src`,
no `base-uri`. The page was served under no script policy at all.

The whole policy now lives in **one module**, `ui/lib/csp.mjs`, and is read by two enforcement
points that must not both emit it:

| Layer | Emits | Why there |
|-------|-------|-----------|
| `ui/proxy.ts` | the `Content-Security-Policy`, on BOTH the request and the response headers | It is the only layer that can mint a value per request, which a script nonce is. Next reads the nonce off the REQUEST header to stamp it onto the script tags it renders; the browser enforces the RESPONSE header. Either one alone is broken: request-only leaves the page unprotected, response-only blocks the very scripts the nonce was added to allow. |
| `ui/next.config.mjs` | `X-Content-Type-Options`, `Referrer-Policy`, and a build-time refusal | Only headers that are genuinely identical on every response. It no longer emits a CSP: two layers each setting one gives the browser two policies to intersect, per directive the stricter wins, and the static one has no nonce, which reinstates exactly the defect being fixed. |

`script-src` is `'self' 'nonce-<per-request>' 'strict-dynamic'`. The nonce is load-bearing
rather than cosmetic: Next serves its hydration bootstrap as an INLINE `<script>` carrying the
Flight payload, so a bare `script-src 'self'` blocks it, `__next_f` never fills, React never
attaches, and the console renders every control while none of them does anything.

Two things must BOTH hold or this fails silently, in opposite directions:

1. The policy must reach the request headers, which is where Next looks for the nonce.
2. The route must be **dynamically rendered**. `app/layout.tsx` sets
   `export const dynamic = "force-dynamic"` for this reason alone. A statically prerendered page
   was built before the nonce existed, so nothing carries it, and because `'strict-dynamic'`
   switches off the `'self'` fallback, adding a nonce to a static page blocks strictly MORE than
   the unfixed policy did.

Both failures are invisible to headers, types, unit tests, the build and a screenshot, so two
checks exist that can see them. `next.config.mjs` reads `app/layout.tsx` at build and boot and
REFUSES the half-configured combination; and `ui/scripts/assert-hydratable.mjs`, wired into
`make ui-check` and CI, starts the built server, fetches the served document and asserts every
script tag carries the served nonce. A header assertion cannot substitute for the second: the
header is byte-identical in the working and the broken case.

```bash
export MKT_PERF_FRAME_ANCESTORS="https://portal.client.com"
# multiple parents are space-separated, per the CSP grammar:
# export MKT_PERF_FRAME_ANCESTORS="https://portal.client.com https://admin.client.com"
```

---

## 4. Shape 2: standalone behind Cloud IAP

When there is no host application, deploy the agent on its own URL:

1. Deploy backend and UI behind the same HTTPS load balancer and Cloud IAP.
2. Set `MKT_PERF_PROFILE=gcp` and `MKT_PERF_IAP_AUDIENCE` so the backend verifies the IAP
   assertion. The audience is the exact structured protected-resource path (for an HTTPS LB it is
   `/projects/<NUM>/global/backendServices/<ID>`); the backend refuses to verify without it.
3. Point the UI at the backend with `NEXT_PUBLIC_API_BASE`. If UI and backend are on **different**
   origins, also set `MKT_PERF_CORS_ORIGINS` to the UI origin (explicit allowlist, never `"*"`):

   ```bash
   export MKT_PERF_CORS_ORIGINS="https://agent.client.com"
   export NEXT_PUBLIC_API_BASE="https://api.agent.client.com"
   ```

4. Share the URL with authorized users. IAP + Workforce Identity Federation (WIF) gives silent
   SSO from the corporate IdP while the corporate session is live.

Leave `MKT_PERF_FRAME_ANCESTORS` at its `'self'` default: nothing should iframe a standalone
deployment.

**Secure IAP note.** The `IapIdentityAdapter` (`adapters/gcp/iap_identity.py`) verifies the
ES256-signed `x-goog-iap-jwt-assertion` (signature against Google's IAP public keys, `iss`,
`exp`/`iat`, and the exact `aud` resource path), derives `subject` from `email`/`sub` and
`tenant` from the `hd` claim, and never logs the assertion. The backend re-verifies the
assertion even though IAP already gated the edge: this is the defense that survives an edge
bypass or a forged unsigned `x-goog-authenticated-user-*` header. The Google SDK imports are
lazy, so the SDK-free `local` and `onprem` profiles never import them.

---

## 5. The identity contract

`get_principal` (`api/security.py`) builds a `RequestContext` from **all** lower-cased inbound
headers, asks the active `IdentityPort` adapter to resolve a verified `Principal`, and maps an
`IdentityError` to a hard 401. The verified `Principal.actor` (the subject) becomes the audit
actor written into every `AuditEvent`. **The request body carries no identity**: there is no
`actor` field on `ReportRequestModel`, so a client cannot assert who they are.

The `Principal` (`domain/identity.py`) models everything enforcement needs: `subject` (the audit
actor), `principals` (entitlement groups / ACL), `tenant` (multi-tenant partition), `assurance`
(auth-strength hint), and `source` (which adapter resolved it).

Identity is a port like any other, swapped by profile in `config/settings.yaml`:

| Profile | Adapter | Behaviour |
|---------|---------|-----------|
| `local` | `LocalPersonaIdentityAdapter` | Seeded dev personas via `X-Dev-Persona`, no IdP. Default = first persona; unknown id -> `IdentityError` -> 401. |
| `gcp` / `platform` | `IapIdentityAdapter` | Verifies the IAP-injected signed assertion; audience from `MKT_PERF_IAP_AUDIENCE`. |
| `onprem` | `OnPremIdentityAdapter` | Fail-fast `NotImplementedError` placeholder for the client's own enterprise IdP (OIDC/SAML). This is the correct fail-closed default: an unverified identity is never accepted. |

### Defense-in-depth PEP

1. **Edge** (Cloud IAP / Apigee) authenticates and gates at ingress.
2. **`agent-guardrail-gateway`** applies central policy.
3. **This backend re-validates** the assertion and derives identity itself
   (`api/security.py` plus the active adapter).

Each layer assumes the others may be bypassed. This is the seam that defeats actor spoofing and
the confused-deputy risk.

---

## 6. Configuration reference

| Variable | Side | Purpose |
|----------|------|---------|
| `MKT_PERF_PROFILE` | backend | `local` \| `gcp` \| `platform` \| `onprem`. Selects the identity adapter (and the whole adapter set). No default: unset is refused, not `local`, so there are no dev personas and no CORS dev origins. |
| `MKT_PERF_IAP_AUDIENCE` | backend | The IAP audience string (the exact structured resource path) the backend verifies against. Required in `gcp`/`platform`. |
| `MKT_PERF_CORS_ORIGINS` | backend | Explicit origin allowlist for the cross-origin / standalone case. Never `"*"`. Set and empty denies every origin rather than falling back to the dev origins. |
| `MKT_PERF_FRAME_ANCESTORS` | backend | CSP `frame-ancestors` allowlist: parent origins permitted to iframe the UI. Defaults to `'self'`. Set and empty means `'none'`, not the default. |
| `NEXT_PUBLIC_API_BASE` | UI | Backend base URL the UI calls. Build-time. |
| `NEXT_PUBLIC_BASE_PATH` | UI | Sub-path the UI is mounted under. Blank keeps the standalone build. Build-time. |
| `NEXT_PUBLIC_EMBED` | UI | Set to `1` to hide the UI's own chrome. Build-time. |
| `NEXT_PUBLIC_FRAME_ANCESTORS` | UI | CSP `frame-ancestors` the console document emits, resolved in the same three states as the backend variable: unset is `'self'`, set and empty is `'none'`, named origins pass through. Build-time. |
| `X-Dev-Persona` | request header | **Local profile only.** Selects a seeded dev persona; ignored in secure profiles. |

---

## 7. Checklists

### Integration checklist

**Shape 1 (same-origin reverse proxy):**

- [ ] Reverse-proxy route mapping `/agent/*` to the agent UI service (3a).
- [ ] Reverse-proxy route mapping `/agent/api/*` to the agent backend service.
- [ ] Agent UI built with `NEXT_PUBLIC_BASE_PATH`, `NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_EMBED=1`,
      `NEXT_PUBLIC_FRAME_ANCESTORS` (3b).
- [ ] `<iframe src="/agent/">` on the host page in a sized container (3c).
- [ ] IdP federated into IAP (WIF) so users carry one session through.

**Shape 2 (standalone):**

- [ ] DNS + HTTPS LB + IAP fronting the deployment.
- [ ] `MKT_PERF_PROFILE=gcp` and `MKT_PERF_IAP_AUDIENCE` set.
- [ ] IdP federated into IAP for SSO; URL shared with authorized users/groups.

### Security checklist

- [ ] **HTTPS everywhere** (the LB terminates TLS; IAP requires it).
- [ ] **IAP audience configured**: `MKT_PERF_IAP_AUDIENCE` set to the exact structured
      protected-resource path in any IAP profile (backend refuses to verify without it).
- [ ] **Framing locked down**: `MKT_PERF_FRAME_ANCESTORS` (backend) and
      `NEXT_PUBLIC_FRAME_ANCESTORS` (UI) set to the exact parent origin(s); `'self'` for
      standalone; never a wildcard.
- [ ] **Origins locked down**: same-origin proxy (no CORS) for shape 1; otherwise
      `MKT_PERF_CORS_ORIGINS` is an explicit allowlist, **never `"*"`**.
- [ ] **No client-asserted identity trusted**: production uses `gcp`/`platform` (or an
      implemented `onprem`), not `local`. The request body carries no `actor`.

---

## 8. Further layers (not built in this slice)

This slice implements the three shapes above. The reference build
`cdd-sow-research/docs/embedding-and-identity.md` documents the additional hardening layers a
wide-distribution embed product needs, and the exact seams they live on:

- **Cross-origin token-handoff iframe** (SaaS tenants, pure SPAs, no-proxy hosts): a versioned
  SRI-pinned loader plus a framework-agnostic `<agent>` custom element, a host-to-iframe
  bearer-token handoff over a hardened `postMessage` contract (exact `targetOrigin`, origin
  allowlist, schema-checked, nonce-bound channel), and a **new** JWKS-verifying `IdentityPort`
  adapter that reads `Authorization: Bearer` and pins issuer / audience / algorithms. This is a
  pure adapter addition on the existing `IdentityPort` seam, with no domain change.
- **Server-side header injection** for hosts with a server tier but no IAP: the proxy injects
  `Authorization: Bearer <host token>`, verified by the same JWKS adapter.
- **Launch in new tab (OIDC redirect login)**: a self-issued session cookie minted after an OIDC
  Authorization Code + PKCE login, verified per-request under a distinct `oidc-session` profile.
- **Per-hop OAuth2 token-exchange (OBO) + Workload Identity + mTLS** to the platform services;
  **DPoP / step-up** (acr/amr) for consequential actions such as budget-shift approval; **per-tenant
  request-time CORS / frame-ancestors / issuer policy**; **Trusted Types** on the UI bundles.

Consult the reference for the full treatment; none of these change the domain, only the transport
and the identity adapter.
