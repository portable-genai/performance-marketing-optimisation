"""On-prem placeholder for ``MetricsPort`` — the sovereign migration target.

A reversibility (no-lock-in) placeholder: in the managed profile this port binds to the
BigQuery metrics adapter; switching ``profile`` to ``onprem`` rebinds it here. The adapter
constructs cleanly with **no external dependencies** and structurally satisfies the same
Protocol, so the contract tests prove interface parity. Porting D4 on-premise is only a
matter of filling these bodies in; the domain orchestration does not change.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ChannelMetrics, ConversionJourney, Market, MetricPoint, Vertical

_MESSAGE = (
    "On-prem MetricsPort adapter is a migration placeholder; implement against your "
    "on-premise metrics warehouse. Core domain logic is unchanged."
)


class OnPremMetricsAdapter:
    """Placeholder metrics adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def channel_metrics(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ChannelMetrics, ...]:
        raise NotImplementedError(_MESSAGE)

    def conversion_journeys(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[ConversionJourney, ...]:
        raise NotImplementedError(_MESSAGE)

    def metric_series(
        self, account_id: str, market: Market, vertical: Vertical, lookback_days: int
    ) -> tuple[MetricPoint, ...]:
        raise NotImplementedError(_MESSAGE)
