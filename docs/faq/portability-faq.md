# Portability FAQ

For architecture, cloud-governance, and exit-planning teams. The claim this repo makes is
"no vendor lock-in": the whole managed stack swaps by one config value, and the domain never
changes. Cross-references: [`ARCHITECTURE.md`](../../ARCHITECTURE.md),
[`docs/onprem-migration.md`](../onprem-migration.md),
[`docs/embedding-and-identity.md`](../embedding-and-identity.md).

### What does "portable" actually mean here?

Two axes, each with a rehearsed exit: **compute** (the whole stack migrates by a one-line
profile change, no domain edits) and **experience / identity** (identity resolves across
hosts by an adapter swap, not a rewrite). Data portability is aided by the audit store's open
JSONL export / restore, but note the honest limit below: there is no single one-command
`portability_demo.py` in this build yet (audit check F3 = PARTIAL). The proof today is the
contract tests, not a scripted tour.

### How does the profile switch work?

The pure-domain core (`src/performance_marketing/domain`) speaks only to
`@runtime_checkable` `typing.Protocol` **ports**; four **adapter families** implement them,
and `config/settings.yaml` binds one adapter per port per profile. Setting
`MKT_PERF_PROFILE` (or `profile:` in the settings) rebinds the entire stack:

- `local`: a WORKING offline stack (deterministic seeded metrics, deterministic engines,
  deterministic LLM, hash-chained audit). No Google Cloud SDK. The default for dev / test /
  CI, and the stack the gate runs on.
- `gcp`: real managed services (BigQuery, Vertex AI forecasting, Gemini, Model Armor, Cloud
  Logging WORM, Cloud Trace, Gen AI evaluation). All Google imports are lazy.
- `platform`: thin HTTP clients delegating to the sibling horizontal-platform services.
- `onprem`: fail-fast placeholder stubs that still satisfy every Protocol (the sovereign-exit
  target).

No `domain/` code changes across any of these. The contract test
(`tests/contract/test_port_parity.py`) proves both `local` and `onprem` construct with a
single `Settings` argument and satisfy every port with no cloud SDK installed; deleting a
binding from `config/settings.yaml` fails the suite.

### How many ports are there, and are they enforced?

Ten ports (`ports/*.py`), each `@runtime_checkable` and re-exported once from
`ports/__init__.py` (proven by `test_all_protocols_are_runtime_checkable`). The parity test
enforces structural parity, single-settings construction, and an `onprem` + `local` binding
for every port. This is the portability guarantee made executable in CI.

### How do we get our data out?

The `local` audit store (`LocalAppendOnlyAuditAdapter`, wrapping the shared
`hex_service_kit.audit.HashChainedAuditLog`) supports **JSONL export / restore**: one
`{seq, prev_hash, entry_hash, event}` object per line, reloaded into a fresh store with the
hash chain re-verified line by line (`verify_chain()`). The exit story for the audit trail is
"copy the JSONL file", not "migrate a product". The reports themselves are plain dataclasses
serialised via the domain's `to_jsonable`, so every output is an open-format JSON document,
not a proprietary blob. Honest limit: this export / restore path is a library capability of
the adapter, not yet exposed as a CLI subcommand.

### Is on-prem / sovereign deployment real or aspirational?

The `onprem` adapters are deliberate fail-fast placeholders (they raise
`NotImplementedError`) that nonetheless satisfy every Protocol and construct with a single
`Settings` arg, so the *interface contract* for a sovereign migration is proven and enforced
by CI today. The actual on-prem implementations are the migration work, scoped in
[`docs/onprem-migration.md`](../onprem-migration.md). This repo is not the sovereign-exit
*planner*: that is the sibling **Rsk5 exit-portability planner** (APRA CPS 230, MAS / HKMA
outsourcing). This repo is one of the systems whose exit that planner reasons about.

### Does residency compromise portability?

No: residency is a deploy-time pin (the region, an Org Policy resource-location allowlist,
CMEK, a VPC-SC perimeter, WORM logging), and portability is the ability to change *where* the
stack runs by configuration. They are orthogonal. The APAC region is a validated `region`
Terraform variable (fail-fast allowlist matching `config/settings.yaml`: JP
`asia-northeast1`, AU `australia-southeast1`, SG `asia-southeast1`), and a second market or
region is a tfvars change, not a fork. Residency enforcement overlaps with the sibling
**Rsk4 residency validator** (a CI gate for region violations), which a fork should run
rather than re-implement.

### What is NOT yet portable / proven end to end?

- There is no single executable `scripts/portability_demo.py` that runs the full claim
  (profile swap + parity + audit export / reload + identity swap) and gates it by exit code
  (F3 = PARTIAL); the pieces are proven by the contract tests instead.
- The audit export / restore is a library capability, not a CLI command.
- The `platform` delegates other than the Hrz4 eval client are phase stubs.

Everything in the one-shot report pipeline runs across `local` today, and the port parity
that makes the `gcp` / `platform` / `onprem` swap safe is enforced on every merge.
