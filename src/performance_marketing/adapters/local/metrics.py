"""Local metrics adapter (MetricsPort) : the laptop's DuckDB metrics warehouse.

The ``local`` profile's stand-in for **BigQuery**: a DuckDB file holding the same three
tables the managed dataset holds, in the same column order, self-seeded from the shipped book
under ``performance_marketing/data/demo_book/``. DuckDB is an embedded engine in a wheel, so
this needs no service and no credentials, and the offline gate stays offline while the store
it exercises is still SQL.

**An account id used to mean nothing here, and that is the defect this replaces.** The old
adapter keyed only on market and vertical and ignored ``account_id`` entirely, while the
managed adapter has always filtered on it. So any string returned a full report on the
laptop and the same string returned nothing on a deployment, and the portal's walkthrough
had been passing for weeks on ``acct-sg-001``, an account that exists in no seed and no
warehouse. It asserted two headings, both of which render whatever the numbers are.

This store filters on the account exactly as BigQuery does, so an unknown account is an
empty result on both surfaces, and a demo that names one fails where it should.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from hex_service_kit.demobook import DuckDbStore

from ... import demo_book
from ...config import Settings
from ...domain.models import (
    ChannelMetrics,
    ConversionJourney,
    Market,
    MetricPoint,
    Vertical,
)

#: Default on-disk location for the laptop warehouse (settings.local.book_path overrides).
_DEFAULT_BOOK_PATH = Path.home() / ".performance_marketing" / "book.duckdb"

_SOURCE = "DuckDB metrics warehouse (local)"


class LocalMetricsAdapter:
    """Serve channel metrics, journeys and metric series from the laptop's DuckDB book."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        path = getattr(getattr(settings, "local", None), "book_path", "") or str(_DEFAULT_BOOK_PATH)
        self._store = DuckDbStore(demo_book.BOOK, path)
        self._conn = self._store.connection

    def close(self) -> None:
        """Close the connection (the CLI and tests reopen the same file)."""
        self._store.close()

    def _rows(
        self,
        table: str,
        columns: tuple[str, ...],
        account_id: str,
        market: Market,
        vertical: Vertical,
        lookback_days: int,
    ) -> list[dict[str, object]]:
        """Every row for this account and scope inside the lookback, oldest first.

        The lookback is measured from the book's own as-of date rather than from today.
        Measuring it from ``CURRENT_DATE`` would mean a fictional warehouse that silently
        empties as it ages: the demo would work until the fixtures fell out of the window,
        and then show a report with no data and no explanation.
        """
        as_of = demo_book.BOOK.manifest()["as_of_date"]
        selected = ", ".join(columns)
        return [
            dict(zip(columns, row, strict=True))
            for row in self._conn.execute(
                f"SELECT {selected} FROM {table} "
                "WHERE account_id = ? AND market = ? AND vertical = ? "
                "AND observed_date >= (CAST(? AS DATE) - CAST(? AS INTEGER)) "
                "ORDER BY observed_date",
                [account_id, market.value, vertical.value, as_of, lookback_days],
            ).fetchall()
        ]

    # ------------------------------------------------------------------ #
    # MetricsPort
    # ------------------------------------------------------------------ #
    def channel_metrics(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ChannelMetrics, ...]:
        rows = self._rows(
            "channel_metrics",
            demo_book.CHANNEL_METRICS.columns,
            account_id,
            market,
            vertical,
            lookback_days,
        )
        return tuple(demo_book.to_channel_metrics(_dates_as_text(row), _SOURCE) for row in rows)

    def conversion_journeys(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ConversionJourney, ...]:
        rows = self._rows(
            "conversion_journeys",
            demo_book.CONVERSION_JOURNEYS.columns,
            account_id,
            market,
            vertical,
            lookback_days,
        )
        return tuple(demo_book.to_journey(_dates_as_text(row), _SOURCE) for row in rows)

    def metric_series(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[MetricPoint, ...]:
        rows = self._rows(
            "metric_series",
            demo_book.METRIC_SERIES.columns,
            account_id,
            market,
            vertical,
            lookback_days,
        )
        return tuple(demo_book.to_metric_point(_dates_as_text(row), _SOURCE) for row in rows)


def _dates_as_text(row: dict[str, object]) -> dict[str, object]:
    """Render date columns back to ISO strings, which is what the domain types hold.

    The store keeps them as dates so the lookback comparison is a date comparison rather
    than a string one; the domain carries the ISO text a citation quotes.
    """
    out = dict(row)
    value = out.get("observed_date")
    if isinstance(value, date):
        out["observed_date"] = value.isoformat()
    return out
