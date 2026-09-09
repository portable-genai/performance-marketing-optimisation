# How the performance marketing optimiser is evaluated

Read this page if you decide what this service is allowed to attribute. The metrics, the bars and
the corpora below are generated from the artifacts that actually gate the build, so they cannot
drift from what runs: `make evals-doc-check` fails the build when this page and those artifacts
disagree.

## How to run it

```sh
make eval              # offline, no credentials
make evals-doc-check   # this page is still true
```

`make gate` runs both on every change.

## Credit summing to 1.0 is not attribution

`attribution_accuracy` checks the credit shares sum to 1.0. They sum to 1.0 **however the credit
is distributed**, so an attribution that gave every point to a channel appearing in no journey
scores a perfect 1.000 there. Nobody buys an attribution model because its shares add up.

`attribution_placement` asks the other question, against the SHIPPED conversion journeys, per
account. Two halves that fail in opposite directions:

- **on journey**: every channel receiving credit appears as a touchpoint in this account's
  journeys. Credit on a channel nobody touched is credit invented.
- **covered**: every channel that appears as a touchpoint receives some credit. That is not
  pedantry: a last-touch model does exactly that to everything before the last touch, and a
  channel silently given nothing is a channel the next budget decision will starve.

The oracle is the book, not a list restated in the eval. The touchpoints the gate measures
against are the touchpoints the demo narrates, so a book edit moves both together.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. There is no dict of thresholds in the runner any more: a
metric scored with no reviewed bar fails the build, and so does a bar that names no
metric, which is the direction that rots quietly because it rots toward looking well
governed.

The third column is the denominator rule, and it applies only where a score is a
FRACTION over scored positives: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` of them. `all or nothing` marks a bar that already asks for no
headroom, so a bigger corpus would not change what it means. Each rubric declares which
it is rather than the rule being guessed from the number.

| Metric | Bar | Denominator | What it measures |
|---|---|---|---|
| `attribution_accuracy` | 0.8 | a rate; needs 5 positives | Fraction of golden accounts where the deterministic attribution credit shares sum to 1.0 within tolerance (credit is conserved across channels). |
| `attribution_placement` | 1 | all or nothing | Credit lands on the channels the account's conversion journeys actually contain, and every channel in those journeys receives some. |
| `citation_accuracy` | 1 | a rate; needs 0 positives | Fraction of cited source ids that appear in the computed / derived evidence set (no fabricated citations). |
| `report_groundedness` | 0.8 | a rate; needs 5 positives | Fraction of reports whose computed figures all carry at least one citation. A report built on uncited figures fails. |
| `review_safety` | 1 | a rate; needs 0 positives | Fraction of reports that correctly set requires_human_review=True (maker-checker) before any budget shift is executed. |

Scored over 6 golden accounts.

## What is exercised

- **6 golden accounts** in `eval/datasets/golden_accounts.jsonl`, each with
  the maker-checker expectation a reviewer assigned. The oracle is the dataset's, never
  a re-read of the report's own flag.
- **12 touchpoint channels across 6 accounts**, read from the
  SHIPPED conversion journeys. That is the oracle `attribution_placement` measures
  against, and it is the book rather than a list restated in the eval: the touchpoints
  the gate measures are the touchpoints the demo narrates, so a book edit moves both
  together instead of moving only one.

## What is NOT measured here

- **Whether the shares are right.** `attribution_placement` says the credit is on the channels
  the journeys contain and that none of them was skipped. It does not say the split between them
  is correct, which needs an incrementality experiment nothing here has.
- **A real model's words.** Every metric scores a deterministic core against a deterministic fake
  LLM adapter.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.
