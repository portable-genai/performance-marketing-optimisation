"""The demo book: one warehouse, served the same way by the laptop store and the managed one.

Pinned here, and each was watched failing first:

* the managed adapter reads only columns the Terraform declares. Written against this
  repository as it was, it fails: the adapter filtered on ``account_id`` and ``observed_date``
  and read ``impressions``, ``clicks`` and ``touchpoints``, and the schema declared ``date``,
  ``touch_order`` and no account column, so every managed query would have failed at the
  first request on a deployment;
* the shipped book carries exactly the columns the schema declares, so a load cannot be
  short a field;
* **an account id selects**. The local adapter keyed only on market and vertical and ignored
  the account, so any string returned a full report and the portal's walkthrough passed for
  weeks on ``acct-sg-001``, an account that exists nowhere;
* the book's own invariants: a converted journey has revenue to attribute, touchpoints are
  0-based and ordered, and no channel reports more clicks than impressions.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from performance_marketing import demo_book
from performance_marketing.adapters.gcp import bigquery_metrics as managed
from performance_marketing.adapters.local.metrics import LocalMetricsAdapter
from performance_marketing.config import LocalSettings, Settings
from performance_marketing.domain.models import Market, Vertical

_REPO = Path(__file__).resolve().parents[2]
_TF = _REPO / "infra" / "terraform" / "bigquery.tf"

#: A real account from the book, and the scope it belongs to.
_ACCOUNT = "acct-sg-banking"
_SCOPE = (Market.SG, Vertical.BANKING)

#: The account the portal's walkthrough used to submit. It is in no seed and no warehouse.
_GHOST_ACCOUNT = "acct-sg-001"

_LOOKBACK = 3650


def _settings() -> Settings:
    base = Settings.load("config/settings.yaml")
    return dataclasses.replace(
        base,
        profile="local",
        local=LocalSettings(audit_path=":memory:", book_path=":memory:"),
    )


@pytest.fixture
def store() -> LocalMetricsAdapter:
    adapter = LocalMetricsAdapter(_settings())
    yield adapter
    adapter.close()


# --------------------------------------------------------------------------- #
# The shipped rows
# --------------------------------------------------------------------------- #
def test_the_shipped_book_is_internally_consistent() -> None:
    demo_book.validate()
    assert demo_book.BOOK.manifest()["fictional"] is True
    assert _ACCOUNT in demo_book.accounts()
    assert _GHOST_ACCOUNT not in demo_book.accounts()


def test_a_converted_journey_without_revenue_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is nothing to attribute, so the attribution engine would divide up zero."""
    real = demo_book.BOOK.rows

    def broken(table: str):  # type: ignore[no-untyped-def]
        rows = real(table)
        if table == "conversion_journeys":
            return [dict(rows[0], converted=True, revenue=0.0), *rows[1:]]
        return rows

    monkeypatch.setattr(demo_book.BOOK, "rows", broken)
    with pytest.raises(demo_book.BookError, match="converted with no revenue"):
        demo_book.validate()


def test_out_of_order_touchpoints_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Attribution is positional, so an unordered journey credits the wrong channel."""
    real = demo_book.BOOK.rows

    def broken(table: str):  # type: ignore[no-untyped-def]
        rows = real(table)
        if table == "conversion_journeys":
            first = dict(rows[0])
            first["touchpoints"] = list(reversed(first["touchpoints"]))
            return [first, *rows[1:]]
        return rows

    monkeypatch.setattr(demo_book.BOOK, "rows", broken)
    with pytest.raises(demo_book.BookError, match="not 0-based and in order"):
        demo_book.validate()


def test_more_clicks_than_impressions_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    real = demo_book.BOOK.rows

    def broken(table: str):  # type: ignore[no-untyped-def]
        rows = real(table)
        if table == "channel_metrics":
            return [dict(rows[0], clicks=int(rows[0]["impressions"]) + 1), *rows[1:]]
        return rows

    monkeypatch.setattr(demo_book.BOOK, "rows", broken)
    with pytest.raises(demo_book.BookError, match="more clicks than impressions"):
        demo_book.validate()


# --------------------------------------------------------------------------- #
# The managed schema
# --------------------------------------------------------------------------- #
def _terraform_tables() -> dict[str, set[str]]:
    text = _TF.read_text(encoding="utf-8")
    blocks = re.findall(
        r'resource\s+"google_bigquery_table"\s+"\w+"\s*\{(.*?)\n\}', text, flags=re.DOTALL
    )
    assert blocks, "no google_bigquery_table blocks found; the regex or the file moved"
    out: dict[str, set[str]] = {}
    for block in blocks:
        table_id = re.search(r'table_id\s*=\s*"(\w+)"', block)
        assert table_id is not None
        # Only the TOP-LEVEL column names: a nested record's fields are not columns, and
        # counting them would let a missing top-level column hide behind a nested one.
        schema = block[block.index("schema = jsonencode([") :]
        depth = 0
        top: set[str] = set()
        for match in re.finditer(r"[\[\]]|name = \"(\w+)\"", schema):
            token = match.group(0)
            if token == "[":
                depth += 1
            elif token == "]":
                depth -= 1
            elif depth == 1 and match.group(1):
                top.add(match.group(1))
        out[table_id.group(1)] = top
    return out


def test_the_managed_adapter_reads_only_columns_the_terraform_declares() -> None:
    declared = _terraform_tables()
    settings = _settings()
    for table_key, columns in managed.SELECTED_COLUMNS.items():
        table_id = getattr(settings.bigquery, table_key)
        assert table_id in declared, f"{table_key} -> {table_id!r} is not a Terraform table"
        undeclared = sorted(set(columns) - declared[table_id])
        assert not undeclared, f"{table_id} reads columns Terraform never declares: {undeclared}"


def test_the_book_and_the_terraform_declare_the_same_columns() -> None:
    """The set checked is ``load_order()``, so it includes the manifest the loader writes.

    ``TABLES`` is this repository's own tables and the loader writes one more: the manifest,
    stamped last because it records the load that wrote the others. The loader creates
    nothing, so a manifest missing from the Terraform is a load that exits before its first
    row -- which is exactly what iterating ``TABLES`` cannot see, and what it did not see in
    a sibling repository.
    """
    declared = _terraform_tables()
    for table in demo_book.BOOK.load_order():
        assert table.name in declared, f"the book ships {table.name} and Terraform does not"
        book_columns, tf_columns = sorted(table.columns), sorted(declared[table.name])
        assert book_columns == tf_columns, (
            f"{table.name}: book {book_columns} vs terraform {tf_columns}"
        )


# --------------------------------------------------------------------------- #
# The DuckDB store, and the account that used to mean nothing
# --------------------------------------------------------------------------- #
def test_the_store_serves_the_shipped_metrics(store: LocalMetricsAdapter) -> None:
    metrics = store.channel_metrics(_ACCOUNT, *_SCOPE, _LOOKBACK)
    shipped = [
        row for row in demo_book.BOOK.rows("channel_metrics") if row["account_id"] == _ACCOUNT
    ]
    assert len(metrics) == len(shipped)
    assert {m.channel.value for m in metrics} == {row["channel"] for row in shipped}
    assert all(m.impressions > 0 and m.clicks > 0 for m in metrics), (
        "impressions and clicks are what the rate engines divide by"
    )


def test_an_unknown_account_returns_nothing_on_the_laptop_too(
    store: LocalMetricsAdapter,
) -> None:
    """The defect this replaces: any string used to return a full report here.

    The managed adapter has always filtered on the account, so the two profiles disagreed,
    and a walkthrough naming an account that exists nowhere passed for weeks.
    """
    assert store.channel_metrics(_GHOST_ACCOUNT, *_SCOPE, _LOOKBACK) == ()
    assert store.conversion_journeys(_GHOST_ACCOUNT, *_SCOPE, _LOOKBACK) == ()
    assert store.metric_series(_GHOST_ACCOUNT, *_SCOPE, _LOOKBACK) == ()


def test_an_account_is_scoped_to_its_own_market_and_vertical(store: LocalMetricsAdapter) -> None:
    assert store.channel_metrics(_ACCOUNT, Market.JP, Vertical.BANKING, _LOOKBACK) == ()


def test_journeys_come_back_with_their_touchpoints_in_order(store: LocalMetricsAdapter) -> None:
    journeys = store.conversion_journeys(_ACCOUNT, *_SCOPE, _LOOKBACK)
    assert journeys, "the SG banking account has no journeys to attribute"
    for journey in journeys:
        assert journey.touchpoints, "a journey with no touchpoints attributes nothing"
        assert [tp.position for tp in journey.touchpoints] == list(range(len(journey.touchpoints)))


def test_the_lookback_is_measured_from_the_book_rather_than_today(
    store: LocalMetricsAdapter,
) -> None:
    """A window measured from CURRENT_DATE would empty the demo silently as it ages."""
    assert store.channel_metrics(_ACCOUNT, *_SCOPE, 3650) != ()
    assert store.channel_metrics(_ACCOUNT, *_SCOPE, 0) == ()
