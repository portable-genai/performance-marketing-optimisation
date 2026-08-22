"""Local metrics adapter (MetricsPort) — deterministic seeded warehouse.

The ``local`` profile's stand-in for **BigQuery**: a deterministic, seedable feed over the
bundled fictional warehouse (``_seed.py``), with no SDK and no network. It returns cited
per-channel metrics, conversion journeys and dated metric series for the requested (account,
market, vertical). SDK-free and unconditional (there is no offline BigQuery emulator here),
and reproducible so the offline CLI and the unit tests agree.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import (
    ChannelMetrics,
    ConversionJourney,
    Market,
    MetricPoint,
    Vertical,
)
from ._seed import CHANNEL_METRICS, CONVERSION_JOURNEYS, METRIC_SERIES


class LocalMetricsAdapter:
    """Deterministic metrics warehouse over the seeded fictional data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def channel_metrics(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ChannelMetrics, ...]:
        return CHANNEL_METRICS.get((market, vertical), ())

    def conversion_journeys(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ConversionJourney, ...]:
        return CONVERSION_JOURNEYS.get((market, vertical), ())

    def metric_series(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[MetricPoint, ...]:
        return METRIC_SERIES.get((market, vertical), ())
