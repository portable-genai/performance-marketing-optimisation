"""MetricsPort and AdPlatformPort — the data feeds for the performance engines.

Primary GCP adapters: **BigQuery** for the metrics warehouse (per-channel spend /
conversions / revenue, the metric time series and the conversion journeys) and the paid-
media **ad-platform** export for the live account / bid-strategy state plus a Vertex AI
forecasting hook. These ports only return raw, cited data; they never compute the
attribution, the ROAS / CAC, the budget plan or the significance: the deterministic engines
do that.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import (
    AbTest,
    Account,
    ChannelMetrics,
    ConversionJourney,
    Market,
    MetricPoint,
    Vertical,
)


@runtime_checkable
class MetricsPort(Protocol):
    def channel_metrics(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ChannelMetrics, ...]:
        """Return cited per-channel spend / conversions / revenue for the window."""
        ...

    def conversion_journeys(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ConversionJourney, ...]:
        """Return the cited conversion journeys for the multi-touch attribution engine."""
        ...

    def metric_series(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[MetricPoint, ...]:
        """Return the cited dated metric points for the anomaly engine."""
        ...


@runtime_checkable
class AdPlatformPort(Protocol):
    def account(self, account_id: str, market: Market, vertical: Vertical) -> Account:
        """Return the account with its current bid strategies and ROAS / CAC target."""
        ...

    def experiments(
        self, account_id: str, market: Market, vertical: Vertical
    ) -> tuple[AbTest, ...]:
        """Return the running A/B experiments for the account."""
        ...
