# performance-marketing-optimisation

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

Catalog id `performance-marketing-optimisation`. Performance marketing and attribution: multi-touch attribution, ROAS
and CAC, bid and budget optimisation, A/B significance and anomaly detection, each a pure
replayable statistic the model narrates but never decides.

Verticals (`banking`, `online_retail`) and markets (Japan, Australia, Singapore) are
configuration plus seed data, not branches in the domain. Adding either is a config and
seed change.

## Concrete bindings

| | |
|---|---|
| Catalog id | `performance-marketing-optimisation` |
| Package | `src/performance_marketing/` |
| Profile variable | `MKT_PERF_PROFILE` |
| Adapter families | `gcp`, `local`, `onprem`, `platform` |
| Gate | `make gate` |
| Console gate | `make ui-check` |

`MKT_PERF_PROFILE` is read in `config.py` alone, in three states. UNSET is no choice: the
SDK-free adapters bind so the process can boot, but every relaxation sees the
`unconfigured` posture instead of `local`, so it gets no CORS allowlist and no persona
picker. SET-AND-EMPTY raises rather than inheriting the unset case. SET-AND-UNKNOWN raises
with the accepted set named, and the comparison is exact and case-sensitive so a
capitalisation typo is a boot failure rather than a silent choice.
`tests/unit/test_profile_single_source.py` fails the build if any other module re-derives
the profile, in Python or in the shipped settings file.

`ProfileChoice` publishes two derived strings, never one. `exposure_profile` drives the
relaxations and is `unconfigured` when nobody chose; `bind_profile` drives the bind guard
and is `local` when nobody chose. They fail closed in opposite directions, so a single
effective-profile string would harden one and weaken the other.

## What this repository still owes

The `Capability gaps` cell on this repository's row in the maintainer's system tracker
is the authoritative list. Its verdict against the shared checks, including the ones it
does not pass, is in [`docs/practices-audit.md`](docs/practices-audit.md).
