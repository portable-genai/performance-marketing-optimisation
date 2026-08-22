"""EfficiencyService — deterministic ROAS / CAC efficiency.

The second deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given per-channel spend / conversions / revenue it computes ROAS
(revenue / spend) and CAC (spend / conversions) per channel and the blended account
figures, and compares each against the configured per-market + per-vertical
:class:`RoasTarget`. ROAS / CAC decide which channels are over- or under-performing (and
therefore which to defund), so they are code an auditor can re-run, not an LLM estimate.

Determinism: same metrics + same target -> same output. No LLM, no clock, no randomness,
no network. Division guards keep ROAS / CAC well-defined when spend or conversions is zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Channel,
    ChannelEfficiency,
    ChannelMetrics,
    Citation,
    EfficiencyReport,
    Market,
    RoasTarget,
    Vertical,
)


@dataclass(frozen=True, slots=True)
class EfficiencyService:
    """Pure, deterministic ROAS / CAC computation with target comparison."""

    def compute(
        self,
        metrics: tuple[ChannelMetrics, ...] | list[ChannelMetrics],
        market: Market,
        vertical: Vertical,
        target: RoasTarget | None = None,
    ) -> EfficiencyReport:
        """Compute per-channel ROAS / CAC and the blended figures vs the target."""
        merged = self._merge_by_channel(metrics)
        channels: list[ChannelEfficiency] = []
        total_spend = 0.0
        total_revenue = 0.0
        total_conv = 0.0
        for ch in sorted(merged, key=lambda c: c.value):
            m = merged[ch]
            roas = self._safe_div(m.revenue, m.spend)
            cac = self._safe_div(m.spend, m.conversions)
            channels.append(
                ChannelEfficiency(
                    channel=ch,
                    spend=round(m.spend, 6),
                    revenue=round(m.revenue, 6),
                    conversions=round(m.conversions, 6),
                    roas=round(roas, 6),
                    cac=round(cac, 6),
                    meets_roas_target=self._meets_roas(roas, target),
                    meets_cac_target=self._meets_cac(cac, m.conversions, target),
                    citations=self._citations(m),
                )
            )
            total_spend += m.spend
            total_revenue += m.revenue
            total_conv += m.conversions

        # Highest spend first for a stable, reviewer-friendly order.
        channels.sort(key=lambda c: (-c.spend, c.channel.value))
        return EfficiencyReport(
            market=market,
            vertical=vertical,
            channels=tuple(channels),
            blended_roas=round(self._safe_div(total_revenue, total_spend), 6),
            blended_cac=round(self._safe_div(total_spend, total_conv), 6),
            target=target,
        )

    # ------------------------------------------------------------------ #
    # Target comparison
    # ------------------------------------------------------------------ #
    @staticmethod
    def _meets_roas(roas: float, target: RoasTarget | None) -> bool:
        if target is None or not target.has_roas:
            return True
        return roas >= target.target_roas

    @staticmethod
    def _meets_cac(cac: float, conversions: float, target: RoasTarget | None) -> bool:
        if target is None or not target.has_cac:
            return True
        if conversions <= 0:
            # Spend with no conversions cannot meet a CAC ceiling.
            return False
        return cac <= target.target_cac

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator > 0 else 0.0

    @staticmethod
    def _merge_by_channel(
        metrics: tuple[ChannelMetrics, ...] | list[ChannelMetrics],
    ) -> dict[Channel, ChannelMetrics]:
        """Sum rows that share a channel (the warehouse may emit one row per day)."""
        out: dict[Channel, ChannelMetrics] = {}
        for m in metrics:
            existing = out.get(m.channel)
            if existing is None:
                out[m.channel] = m
            else:
                out[m.channel] = ChannelMetrics(
                    channel=m.channel,
                    spend=existing.spend + m.spend,
                    impressions=existing.impressions + m.impressions,
                    clicks=existing.clicks + m.clicks,
                    conversions=existing.conversions + m.conversions,
                    revenue=existing.revenue + m.revenue,
                    observed_date=existing.observed_date or m.observed_date,
                    citation=existing.citation or m.citation,
                )
        return out

    @staticmethod
    def _citations(m: ChannelMetrics) -> tuple[Citation, ...]:
        return (m.citation,) if m.citation is not None else ()
