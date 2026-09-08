"""The shipped demo book: fictional channel metrics, conversion journeys and metric series.

The rows live as newline-delimited JSON under ``performance_marketing/data/demo_book/``, one
file per BigQuery table and in that table's column order, so one set of files feeds the
DuckDB store the ``local`` profile reads, the loader that fills the managed dataset, and the
tests. The reading, the overwrite guard and the tenant rule come from
:mod:`hex_service_kit.demobook`; what is here is the part that is about THIS system.

Two things this book fixes rather than merely records.

**The managed schema could not satisfy the managed adapter.** The adapter filters on
``account_id`` and ``observed_date`` and reads ``impressions``, ``clicks`` and a nested
``touchpoints`` array; the Terraform declared ``date``, ``touch_order`` and no account column
at all. Every one of those queries would have failed at the first request on a deployment.
The columns below are the adapter's, which is the shape the domain needs, and a contract test
holds the Terraform against them.

**An account id used to mean nothing on the laptop.** The local adapter keyed only on market
and vertical and ignored the account entirely, so any string returned the same rows and the
portal's walkthrough passed on an account that exists nowhere. The local store now filters on
it exactly as BigQuery does, which makes an unknown account an empty result on both surfaces.

Everything is fictional. See ``data/demo_book/README.md``.
"""

from __future__ import annotations

from typing import Any

from hex_service_kit.demobook import BookError, NdjsonBook, Table

from .domain.models import (
    Channel,
    ChannelMetrics,
    Citation,
    ConversionJourney,
    MetricPoint,
    SourceType,
    Touchpoint,
)

#: The tenant the shipped rows carry. This system's rows are account-scoped rather than
#: customer-scoped, so only the manifest names a tenant; the loader still requires one, and
#: requires it for the same reason: a deployment's own value is never guessable from here.
SHIPPED_TENANT = "demo-bank"

CROSS_TENANT: dict[str, str] = {}

CHANNEL_METRICS = Table(
    name="channel_metrics",
    columns=(
        "account_id",
        "market",
        "vertical",
        "channel",
        "spend",
        "impressions",
        "clicks",
        "conversions",
        "revenue",
        "observed_date",
    ),
    types={
        "account_id": "TEXT NOT NULL",
        "market": "TEXT NOT NULL",
        "vertical": "TEXT NOT NULL",
        "channel": "TEXT NOT NULL",
        "spend": "DOUBLE NOT NULL",
        "impressions": "BIGINT NOT NULL",
        "clicks": "BIGINT NOT NULL",
        "conversions": "DOUBLE NOT NULL",
        "revenue": "DOUBLE NOT NULL",
        "observed_date": "DATE NOT NULL",
    },
    primary_key=("account_id", "channel", "observed_date"),
    date_columns=frozenset({"observed_date"}),
)

CONVERSION_JOURNEYS = Table(
    name="conversion_journeys",
    columns=(
        "journey_id",
        "account_id",
        "market",
        "vertical",
        "converted",
        "revenue",
        "observed_date",
        "touchpoints",
    ),
    types={
        "journey_id": "TEXT NOT NULL",
        "account_id": "TEXT NOT NULL",
        "market": "TEXT NOT NULL",
        "vertical": "TEXT NOT NULL",
        "converted": "BOOLEAN NOT NULL",
        "revenue": "DOUBLE NOT NULL",
        "observed_date": "DATE NOT NULL",
        # A journey is its ordered touchpoints, so they are nested rather than spread across
        # one row per touch. The previous schema modelled them as separate rows keyed by
        # touch_order, which the attribution engine would have had to reassemble and the
        # adapter never did: it read row["touchpoints"] and got nothing.
        "touchpoints": 'STRUCT(channel VARCHAR, observed_date VARCHAR, "position" BIGINT)[]',
    },
    primary_key=("journey_id",),
    date_columns=frozenset({"observed_date"}),
)

METRIC_SERIES = Table(
    name="metric_series",
    columns=("account_id", "market", "vertical", "metric", "observed_date", "value"),
    types={
        "account_id": "TEXT NOT NULL",
        "market": "TEXT NOT NULL",
        "vertical": "TEXT NOT NULL",
        "metric": "TEXT NOT NULL",
        "observed_date": "DATE NOT NULL",
        "value": "DOUBLE NOT NULL",
    },
    primary_key=("account_id", "metric", "observed_date"),
    date_columns=frozenset({"observed_date"}),
)

TABLES = (CHANNEL_METRICS, CONVERSION_JOURNEYS, METRIC_SERIES)

BOOK = NdjsonBook("performance_marketing.data.demo_book", TABLES)


def accounts() -> tuple[str, ...]:
    """Every account the book carries, sorted. The console and the demos read this."""
    return tuple(sorted({str(row["account_id"]) for row in BOOK.rows("channel_metrics")}))


def validate() -> None:
    """The book's own invariants, on top of the shape the kit checks.

    Each rule here is one a hand edit can break and nothing else would notice until a demo:
    an account with metrics but no series to detect an anomaly in, a journey whose
    touchpoints are out of order, or a converted journey with no revenue to attribute.
    """
    BOOK.validate()
    metric_accounts = {row["account_id"] for row in BOOK.rows("channel_metrics")}
    if not metric_accounts:
        raise BookError("the book ships no channel metrics")

    series_accounts = {row["account_id"] for row in BOOK.rows("metric_series")}
    missing = sorted(metric_accounts - series_accounts)
    if missing:
        raise BookError(f"accounts with metrics and no metric series: {missing}")

    journey_accounts = {row["account_id"] for row in BOOK.rows("conversion_journeys")}
    missing = sorted(metric_accounts - journey_accounts)
    if missing:
        raise BookError(f"accounts with metrics and no conversion journeys: {missing}")

    for row in BOOK.rows("conversion_journeys"):
        touchpoints = row.get("touchpoints") or []
        if not touchpoints:
            raise BookError(f"journey {row['journey_id']!r} has no touchpoints to attribute")
        positions = [int(tp["position"]) for tp in touchpoints]
        if positions != sorted(positions) or positions != list(range(len(positions))):
            raise BookError(
                f"journey {row['journey_id']!r} touchpoints are not 0-based and in order: "
                f"{positions}"
            )
        if row["converted"] and float(row["revenue"]) <= 0:
            raise BookError(f"journey {row['journey_id']!r} converted with no revenue")

    for row in BOOK.rows("channel_metrics"):
        where = f"{row['account_id']}/{row['channel']}"
        if int(row["clicks"]) > int(row["impressions"]):
            raise BookError(f"{where} has more clicks than impressions")
        if float(row["spend"]) < 0 or float(row["revenue"]) < 0:
            raise BookError(f"{where} has a negative spend or revenue")


# --------------------------------------------------------------------------- #
# Row to domain
# --------------------------------------------------------------------------- #
def _channel(raw: Any) -> Channel:
    try:
        return Channel(str(raw))
    except ValueError:
        return Channel.OTHER


def _citation(row: dict[str, Any], what: str, source: str) -> Citation:
    return Citation(
        source_id=f"{row.get('account_id', '')}-{what}",
        source_type=SourceType.METRICS,
        title=f"{what.replace('_', ' ')} for {row.get('account_id', '')}",
        snippet=source,
    )


def to_channel_metrics(row: dict[str, Any], source: str) -> ChannelMetrics:
    return ChannelMetrics(
        channel=_channel(row.get("channel")),
        spend=float(row.get("spend") or 0.0),
        impressions=int(row.get("impressions") or 0),
        clicks=int(row.get("clicks") or 0),
        conversions=float(row.get("conversions") or 0.0),
        revenue=float(row.get("revenue") or 0.0),
        observed_date=str(row.get("observed_date") or ""),
        citation=_citation(row, "channel_metrics", source),
    )


def to_journey(row: dict[str, Any], source: str) -> ConversionJourney:
    citation = _citation(row, "conversion_journey", source)
    touchpoints = tuple(
        Touchpoint(
            channel=_channel(tp.get("channel")),
            observed_date=str(tp.get("observed_date") or ""),
            position=int(tp.get("position", index) or index),
            citation=citation,
        )
        for index, tp in enumerate(row.get("touchpoints") or ())
    )
    return ConversionJourney(
        id=str(row.get("journey_id") or ""),
        touchpoints=touchpoints,
        converted=bool(row.get("converted", True)),
        revenue=float(row.get("revenue") or 0.0),
    )


def to_metric_point(row: dict[str, Any], source: str) -> MetricPoint:
    return MetricPoint(
        metric=str(row.get("metric") or ""),
        observed_date=str(row.get("observed_date") or ""),
        value=float(row.get("value") or 0.0),
        citation=_citation(row, "metric_series", source),
    )
