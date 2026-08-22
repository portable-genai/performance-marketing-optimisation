"""BigQuery metrics adapter (MetricsPort) — GCP managed stack.

The primary D4 metrics backend: **BigQuery** over the marketing-performance warehouse
(per-channel spend / conversions / revenue, the conversion-journey table and the metric
time-series table). The adapter issues parameterised queries scoped to the account, market
and vertical and maps each row onto the domain :class:`ChannelMetrics` /
:class:`ConversionJourney` / :class:`MetricPoint`, each carrying a :class:`Citation` back to
its warehouse row. It only returns raw, cited data: the deterministic engines compute the
attribution, ROAS / CAC, budget plan and anomalies.

The BigQuery dataset location is resolved from the active market and **validated** against
the per-market allow-list, so queries stay inside the configured residency boundary.

The ``google-cloud-bigquery`` import is LAZY so the on-prem / local / test profile imports
this module without the SDK installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import (
    Channel,
    ChannelMetrics,
    Citation,
    ConversionJourney,
    Market,
    MetricPoint,
    SourceType,
    Touchpoint,
    Vertical,
)
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.cloud import bigquery


class BigQueryMetricsAdapter:
    """Read cited performance metrics from the BigQuery warehouse."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bq = settings.bigquery
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Lazy, region-validated client construction
    # ------------------------------------------------------------------ #
    def _get_client(self, market: Market | None = None) -> bigquery.Client:
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google.cloud import bigquery  # noqa: PLC0415 — lazy: gcp profile only

            self._client = bigquery.Client(project=self._settings.project_id, location=region)
        return self._client

    # ------------------------------------------------------------------ #
    # MetricsPort
    # ------------------------------------------------------------------ #
    def channel_metrics(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ChannelMetrics, ...]:
        rows = self._query(self._bq.metrics_table, account_id, market, vertical, lookback_days)
        out: list[ChannelMetrics] = []
        for row in rows:
            out.append(
                ChannelMetrics(
                    channel=self._coerce_channel(row.get("channel")),
                    spend=float(row.get("spend", 0.0) or 0.0),
                    impressions=int(row.get("impressions", 0) or 0),
                    clicks=int(row.get("clicks", 0) or 0),
                    conversions=float(row.get("conversions", 0.0) or 0.0),
                    revenue=float(row.get("revenue", 0.0) or 0.0),
                    observed_date=str(row.get("observed_date", "")),
                    citation=self._citation(row, "channel metrics"),
                )
            )
        return tuple(out)

    def conversion_journeys(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ConversionJourney, ...]:
        rows = self._query(self._bq.journeys_table, account_id, market, vertical, lookback_days)
        journeys: list[ConversionJourney] = []
        for row in rows:
            touchpoints = tuple(
                Touchpoint(
                    channel=self._coerce_channel(tp.get("channel")),
                    observed_date=str(tp.get("observed_date", "")),
                    position=int(tp.get("position", idx) or idx),
                    citation=self._citation(row, "journey touchpoint"),
                )
                for idx, tp in enumerate(row.get("touchpoints", []) or [])
            )
            journeys.append(
                ConversionJourney(
                    id=str(row.get("journey_id", "")),
                    touchpoints=touchpoints,
                    converted=bool(row.get("converted", True)),
                    revenue=float(row.get("revenue", 0.0) or 0.0),
                )
            )
        return tuple(journeys)

    def metric_series(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[MetricPoint, ...]:
        rows = self._query(self._bq.series_table, account_id, market, vertical, lookback_days)
        return tuple(
            MetricPoint(
                metric=str(row.get("metric", "")),
                observed_date=str(row.get("observed_date", "")),
                value=float(row.get("value", 0.0) or 0.0),
                citation=self._citation(row, "metric series"),
            )
            for row in rows
        )

    # ------------------------------------------------------------------ #
    # Query plumbing
    # ------------------------------------------------------------------ #
    def _query(
        self,
        table: str,
        account_id: str,
        market: Market,
        vertical: Vertical,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        from google.cloud import bigquery  # noqa: PLC0415 — lazy

        client = self._get_client(market)
        sql = (
            f"SELECT * FROM `{self._settings.project_id}.{self._bq.dataset}.{table}` "
            "WHERE account_id = @account_id AND market = @market AND vertical = @vertical "
            "AND observed_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @lookback DAY)"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
                bigquery.ScalarQueryParameter("market", "STRING", market.value),
                bigquery.ScalarQueryParameter("vertical", "STRING", vertical.value),
                bigquery.ScalarQueryParameter("lookback", "INT64", lookback_days),
            ]
        )
        return [dict(row) for row in client.query(sql, job_config=job_config).result()]

    # ------------------------------------------------------------------ #
    # Mapping helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _coerce_channel(raw: Any) -> Channel:
        try:
            return Channel(str(raw))
        except ValueError:
            return Channel.OTHER

    @staticmethod
    def _citation(row: dict[str, Any], title: str) -> Citation:
        sid = str(row.get("row_id") or row.get("journey_id") or row.get("observed_date") or title)
        return Citation(
            source_id=sid,
            source_type=SourceType.METRICS,
            title=title,
            observed_date=str(row.get("observed_date", "")) or None,
            page=1,
        )
