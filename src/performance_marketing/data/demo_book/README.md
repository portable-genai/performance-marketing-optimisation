# The demo book

A fictional marketing warehouse: per-channel spend and outcomes, conversion journeys with
their ordered touchpoints, and dated metric series for the anomaly detector. Six accounts,
one per market and vertical. No row describes a real advertiser, campaign or platform.

One file per table, newline-delimited JSON, keys in the column order the BigQuery schema in
`infra/terraform/bigquery.tf` declares. The same rows feed three consumers:

| Consumer | How it reads the files |
|---|---|
| The `local` profile | `adapters/local/metrics.py` opens a DuckDB file holding the same three tables and, when they are empty, inserts these rows |
| The deployment | `scripts/load_demo_book.py` streams them into the `mkt_performance` dataset |
| Tests | `performance_marketing.demo_book` builds the domain objects |

| File | Rows | What a row is |
|---|---|---|
| `channel_metrics.ndjson` | 13 | one account, channel and day: spend, impressions, clicks, conversions, revenue |
| `conversion_journeys.ndjson` | 18 | one journey, its ordered touchpoints nested inside it |
| `metric_series.ndjson` | 48 | one dated observation of one metric |
| `book_manifest.ndjson` | 1 | the book's version, its as-of date, and `fictional: true` |

**Two defects this book fixed.**

The managed schema could not satisfy the managed adapter. The adapter filters on `account_id`
and `observed_date` and reads `impressions`, `clicks` and a nested `touchpoints` array; the
Terraform declared `date`, `touch_order` and no account column, so every managed query would
have failed at the first request. The columns here are the adapter's, and
`tests/contract/test_demo_book.py` holds the Terraform against them.

An account id used to mean nothing on the laptop. The local adapter keyed only on market and
vertical, so any string returned a full report and the portal's walkthrough passed for weeks
on `acct-sg-001`, which exists nowhere. The local store now filters on the account exactly as
BigQuery does.

**The as-of date is load-bearing.** The lookback window is measured from
`book_manifest.as_of_date`, not from today, so a fictional warehouse does not silently empty
as it ages. It is the day after the latest observation; move the data and move it too.
