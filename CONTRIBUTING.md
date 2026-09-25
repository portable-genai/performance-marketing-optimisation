# Contributing

This repo follows the catalog's ports-and-adapters bar. Before any change lands, the **hard
gate** must be green in a fresh `[dev]`-only venv (no `google-cloud-*`):

```sh
make install          # python3.14 venv + [dev] only
make gate             # ruff check + ruff format --check + mypy + pytest + eval (exit 0)
```

Plus, for a UI change: `cd ui && npm install && npm run build` must compile.

## Principles

- **The deterministic engines are the heart.** Multi-touch attribution, ROAS / CAC,
  bid / budget optimisation, A/B significance and anomaly detection are pure, stdlib-only,
  replayable and unit-tested. The LLM only narrates the result and drafts the spend-shift
  rationale; it never decides a number, a verdict or a budget move.
- **Provenance on every figure.** Every figure that leaves the system carries a `Citation`.
- **Maker-checker.** Every `PerformanceReport` sets `requires_human_review=True`; nothing
  auto-executes a budget shift.
- **No vendor lock-in.** Every port is a `@runtime_checkable` Protocol with a `gcp` (lazy),
  `local` (default, SDK-free, the working offline stack), `platform` and `onprem`
  (fail-fast) adapter family. The contract test asserts `local` + `onprem` satisfy every
  port. Keep Google imports lazy (inside methods), never at module load time.
- **Generic + APAC.** Banking and online retail are configurable verticals; JP / AU / SG
  are config + seed (residency region, locales, per-market targets). Never hard-code a
  market or vertical into a branch.
- **Docs are em-dash-free; YAML scalars carry no space-colon-space.**

## Commits

The user authors all commits. Do not add `Co-Authored-By` trailers.

## Adding an adapter

1. Implement the existing Protocol in `src/<package>/adapters/<profile>/<name>.py` with the
   single constructor `Adapter(settings)`; cloud SDK imports stay inside methods.
2. Add the dotted binding under the existing port in `config/settings.yaml` for that profile.
3. Add the adapter to the constructor and behavioral cases in
   `tests/contract/test_port_parity.py`; a placeholder must construct and fail fast.
4. Add profile-specific boundary tests, including unavailable service and malformed response
   cases. Do not copy business rules into the adapter.
5. A MODEL port adapter notes what answered and samples per call. After a successful call the
   `gcp` adapter calls `hex_service_kit.provenance.note_model(<the model id it actually
   called>)`, and `provenance.note_search()` only when an online search tool was attached to
   THAT call; the `local` stub notes `config.STUB_GENERATOR_MODEL`; a `live` adapter on the
   kit's local-model client needs nothing. `api/app.py` turns the notes into `X-Answered-By` /
   `X-Search-Used` for the console's pills. `LlmRequest.temperature` is `float | None = None`
   and an adapter OMITS it when `None` (some models reject the parameter, so free means absent,
   never `1.0`); pin `0.0` only where the output is extracted, classified, scored or compared,
   and leave narration, drafting and judges free. No flag may swap in a second model:
   `generator_model` is the model the adapter calls (`tests/unit/test_answer_provenance.py`,
   `tests/unit/test_sampling_per_call.py`).
6. Run `make gate`, the UI gate when applicable, and `make tf-validate` when deployment
   configuration changed.

## Adding a new port or sub-service

1. Add a `@runtime_checkable` Protocol in `src/<package>/ports/<name>.py` and re-export it once
   from `ports/__init__.py`.
2. Add one binding per declared profile in `config/settings.yaml`: working local, managed GCP
   or platform, and an honest on-premises implementation or fail-fast placeholder.
3. Register the Protocol in the `PORT_PROTOCOLS` map used by
   `tests/contract/test_port_parity.py`; the reverse set-equality assertion must stay green.
4. Wire the port only in the composition root or service factory. Domain services accept the
   Protocol dependency and never import an adapter.
5. Add behavioral parity tests and an end-to-end local test, then update the architecture,
   compliance evidence and adopter guidance.
