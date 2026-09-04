# `performance-marketing-optimisation` console (thin Next.js UI)

A thin demo console for `performance-marketing-optimisation` Performance Marketing and Attribution. It calls the `performance-marketing-optimisation` FastAPI
backend (`POST /v1/report`) and renders the cited performance report: per-channel ROAS /
CAC, the multi-touch attribution split, the deterministic budget plan, the A/B significance
verdicts, the anomalies, and the maker-checker "human review required" banner.

```sh
npm ci
npm run build           # must compile (tsconfig has baseUrl "." for the @/* alias)
NEXT_PUBLIC_API_BASE=http://localhost:8103 npm run dev
```

The API base defaults to `http://localhost:8103` (the `performance-marketing-optimisation` API port), so nothing needs
configuring to run against `make run-api`. Override it by setting `NEXT_PUBLIC_API_BASE`
before `npm run build`: Next inlines every `NEXT_PUBLIC_*` value at build time.

## Source map

| Path | Owns |
|------|------|
| `app/layout.tsx` | The document shell. Sets `export const dynamic = "force-dynamic"`, which the nonce CSP requires (see below); it is not a performance preference. |
| `app/page.tsx` | The console itself: the report form and the rendered result. |
| `lib/api.ts` | The typed fetch client, and `API_BASE`. |
| `lib/csp.mjs` | The Content-Security-Policy, built ONCE. Also `DEFAULT_API_BASE`, so the origin `lib/api.ts` fetches and the origin `connect-src` permits cannot drift apart. |
| `proxy.ts` | Mints the per-request script nonce and sets the CSP on both the request and the response headers. |
| `next.config.mjs` | Static headers only (`nosniff`, `Referrer-Policy`), plus the build-time refusal of an unhydratable CSP. It deliberately emits NO CSP. |
| `scripts/assert-hydratable.mjs` | Starts the built server and proves the served document can hydrate. |
| `tests/csp.test.mjs` | Unit cover for what the policy STRING can decide. |

## Security headers

The policy lives in `lib/csp.mjs` and is emitted by `proxy.ts` alone. Two layers both emitting
a CSP would give the browser two policies to intersect, per directive stricter wins, and the
static one carries no nonce, so the scripts it is meant to allow get blocked anyway.

`script-src` carries a per-request nonce plus `'strict-dynamic'`. Next serves its hydration
bootstrap as an inline script, so without the nonce the browser blocks it, `__next_f` never
fills, React never attaches, and every control on the page is dead markup that renders,
type-checks, builds and screenshots exactly like a working console.

Configuration, all build-time (`NEXT_PUBLIC_*` values are substituted at build):

| Variable | Effect |
|----------|--------|
| `NEXT_PUBLIC_API_BASE` | Where the client fetches, and what `connect-src` widens to (its origin only, not the path). Unset means `DEFAULT_API_BASE`. A relative value is refused rather than silently dropped. |
| `NEXT_PUBLIC_FRAME_ANCESTORS` | Who may frame the console. Read in three states, matching `MKT_PERF_FRAME_ANCESTORS` on the service: unset is `'self'`, set-but-naming-nothing is `'none'` (never an empty directive, which browsers discard as a parse error), named origins pass through. |
| `NEXT_PUBLIC_BASE_PATH` | Sub-path the console is mounted under. |
| `NEXT_PUBLIC_EMBED` | `1` hides the console's own chrome for embedding. |

## Gate

```sh
make ui-install    # npm ci
make ui-check      # lint (tsc) -> unit tests -> build -> assert-hydratable
```

`assert-hydratable` runs last and against the artefact the build just produced. It is the only
step that executes the page: it starts the built server, fetches the served document, and
asserts that every directive the policy needs is present and non-empty and that every `<script>`
tag carries the nonce from the response header. Header-string assertions cannot replace it,
because the header is byte-identical in the working and the broken case. Run it against a
deliberately broken state once before trusting it green.
