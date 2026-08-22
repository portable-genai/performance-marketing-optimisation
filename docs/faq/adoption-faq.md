# Adoption FAQ

For an engineering lead forking this repo as their institution's base. The step-by-step is
[`docs/ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?" questions.

### How do I rebrand it for my institution or measurement domain?

`scripts/rename_fork.py` rewrites the package name (`performance_marketing`), the CLI entry
point (`mkt-perf`), the `MKT_PERF_` env prefix, and the baked-in resource ids
(`performance-marketing-optimisation`) in one pass (preview with `--dry-run`, apply with `--yes`).
Then recreate the venv, `pip install -e ".[dev]"`, and run `make gate`. The script does the
mechanical rename; the human decisions (region, IdP, ROAS / CAC targets, fixtures, eval
golden set) are the checklist in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags** (semver). The repo declares a **core-vs-adopter-owned boundary** (ADOPTING section 2):
upstream owns `ports/`, `tests/contract/`, the eval harness mechanics, CI, and the hexagon
wiring (`config.py`); you own `config/settings.yaml` *values*, the local seed fixtures,
`adapters/onprem/*`, UI theming, the eval golden set, and the `COMPLIANCE.md` regulator
crosswalk rows. Rebase your adopter-owned changes onto each release rather than merging
`main` continuously, so conflicts stay in the files you were told to expect.

### Is there a separate kernel module I keep untouched?

Yes. `domain/kernel.py` is the stable vertical-neutral import surface for citation, LLM,
guardrail, audit and agent vocabulary. It exports no `PerformanceReport`, `AttributionView`
or other measurement aggregate, and a contract test enforces that boundary.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list, and the contract test fails loudly if you miss part of it:
define the `@runtime_checkable` Protocol under `ports/`, re-export it from `ports/__init__.py`,
implement one adapter per profile (at least `local` and `onprem`), bind all of them in
`config/settings.yaml`, add a `cached_property` on the `Container` in `config.py`, and wire it
in `api/deps.py`. `CONTRIBUTING.md` now records separate adapter and new-port checklists,
including behavior parity and evidence updates.

### How do I add a new sub-service or output panel?

A sub-service is pure domain: add `domain/<name>_service.py` (stdlib only, a frozen
`slots=True` dataclass engine), re-export it from `domain/services.py`, construct it in
`api/deps.py`, and unit-test it for determinism. Keep the LLM out of the decision: the engine
computes, the LLM only narrates. For an output panel, `scripts/render_report_ui.py` renders
attached artifacts; add a stable hook so the demo walkthrough can target it.

### How do I retune the ROAS / CAC targets and statistical tunables?

The per-market / per-vertical `RoasTarget` values are config plus seed through the ad-platform
adapter. Engine values (`alpha`, minimum sample, anomaly thresholds, optimisation cap and
attribution weights) live under validated `config/settings.yaml:policy`; the production
composition root threads them into the pure services. Treat the shipped values as reference
defaults and approve adopter values deliberately.

### Can I use it for a vertical or market other than the ones shipped?

Yes. `banking` and `online_retail` are first-class configurable verticals, and Japan
(`asia-northeast1`), Australia (`australia-southeast1`) and Singapore (`asia-southeast1`) are
configurable markets: residency region, locales and targets come from the per-market profiles
as config plus seed, never a hard-coded branch. Adding a market or a vertical is a config plus
seed change. To adapt the engines to a different measurement domain entirely, keep the ports
and the engine mechanics and rewrite the artifact models and the narration prompts.

### Does the CI run for my fork out of the box?

Yes. CI and the eval smoke gate run on the `local` profile with **no cloud credentials and no
org secrets** (audit check D3 = PASS): a fork's build is green immediately. You add secrets
only when you wire the `gcp` / `platform` profiles. Note the eval gate measures the
*reference* bundle (`mkt4-performance`) until you rebuild the golden set
(`eval/datasets/golden_accounts.jsonl`); that is an explicit adoption step, not a silent
pass. One minor drift to know about: CI currently pins Python 3.14 while `pyproject` targets
3.12.
