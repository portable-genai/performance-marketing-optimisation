# Mkt4 demo - Performance Marketing and Attribution

Two ways to demo Mkt4: a fully **offline local** demo (no cloud, no API key) and a **GCP**
demo on the managed stack. Both are region + vertical selectable, over obviously-fictional
synthetic data for banking and online retail across JP / AU / SG.

The deterministic engines decide every figure; the LLM only narrates. Every report carries
citations and the maker-checker "human review required" banner; nothing moves a budget
automatically.

## Ports (so all surfaces run side by side)

| Surface | Port |
| --- | --- |
| FastAPI API | 8103 |
| Next.js console (dev) | 3000 |
| Presenter demo server | 8113 |

## 1. Local (offline) demo

No Google Cloud, no credentials, no `google-cloud-*`.

```sh
make install                       # python3.14 venv + [dev] only
make gate                          # prove it is green first

# a) one-shot CLI, region + vertical selectable
MKT_PERF_PROFILE=local .venv/bin/mkt-perf report acct-sg-banking -m SG -v banking
MKT_PERF_PROFILE=local .venv/bin/mkt-perf report acct-jp-online_retail -m JP -v online_retail
MKT_PERF_PROFILE=local .venv/bin/mkt-perf budget-plan acct-au-online_retail -m AU -v online_retail

# b) static audit-first artifacts (JSON + dependency-free HTML) for screenshots
make demo                          # writes scripts/out/*.json and *.html
open scripts/out/index.html

# c) live, presenter-controlled walk-through (click "Next" through verticals + markets)
make demo-server                   # http://localhost:8113

# d) the same walk-through, narrated and paced by Playwright (two terminals)
#    one-time: .venv/bin/pip install playwright && .venv/bin/playwright install chromium
#    terminal 1: make demo-server
#    terminal 2: .venv/bin/python scripts/demo_playwright.py
#    unattended: HEADLESS=1 DEMO_AUTO=1 .venv/bin/python scripts/demo_playwright.py

# e) the API + the thin console, on a PRODUCTION build
make run-api                       # FastAPI on :8103 (local profile)
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8103 npm run build && npm run start
```

`NEXT_PUBLIC_*` is inlined by the BUILD, which is why it is set on `npm run build` and not on
`npm run start`. Demo the built console, never `make run-ui`: that target is the developer
loop and serves `next dev`, and the standing rule for every demo in the fleet is
`org-metadata/docs/demos/demo-inventory.md`: production builds only.

In the console, pick a market (JP / AU / SG), a vertical (banking / online retail) and an
attribution model, then **Build cited report**. The report shows per-channel ROAS / CAC vs
target, the multi-touch attribution split, the deterministic budget plan, the A/B
significance verdicts and any anomalies, each with provenance.

### What to point at in the demo

- **Determinism**: run the same CLI twice; the figures and citations are identical.
- **Generic + APAC**: the same engines produce a banking-SG report (CAC ceiling) and an
  online-retail-JP report (ROAS floor); switching market / vertical is config + seed only.
- **Maker-checker**: every report is flagged human-review; the budget plan is budget-neutral
  and proposed, never executed.
- **Anomaly**: the seeded banking-SG and retail-AU CPA series carry a deliberate spike the
  robust-z engine flags as CRITICAL.

## 2. GCP (managed-stack) demo

Requires the `[gcp]` extra, a project, and the BigQuery warehouse / Vertex AI access. The
residency region is resolved from the chosen market and validated (JP -> `asia-northeast1`,
AU -> `australia-southeast1`, SG -> `asia-southeast1`); a region outside the allow-list is
refused.

```sh
make install-gcp
export GOOGLE_CLOUD_PROJECT=your-project
export MKT_PERF_PROFILE=gcp
export MKT_MARKET=SG MKT_VERTICAL=banking      # region + vertical selectable

# Metrics from BigQuery, narration via Gemini, audit to the WORM bucket, eval via Gen AI eval.
.venv/bin/mkt-perf report acct-sg-banking -m SG -v banking
.venv/bin/python eval/run_eval.py --use-gcp     # route the Hrz4 gate through Gen AI eval
make run-api                                    # the same API on the managed stack
```

Switch the entire stack to the on-prem migration target with `MKT_PERF_PROFILE=onprem`; the
CLI then exits 2 and names the migration target for each unimplemented port, proving
exit-portability without changing any domain code.

## 3. The exit-portability proof (30 seconds)

```sh
MKT_PERF_PROFILE=onprem .venv/bin/mkt-perf report acct-sg-banking -m SG -v banking; echo $?
# error: 'report' is not available under profile 'onprem' ... (exit 2)
```

The domain orchestration is identical across all three profiles; only the bound adapters
change.
