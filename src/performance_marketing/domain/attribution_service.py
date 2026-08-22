"""AttributionService — deterministic multi-touch attribution.

The first deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given conversion journeys (ordered touchpoints per converting
journey) it distributes conversion and revenue credit across channels using a chosen
:class:`AttributionModel` (last-touch, first-touch, linear or 40/20/40 position-based).
Attribution drives where credit (and therefore budget) is assigned, so it must be code an
analyst can re-run to the identical split, not an LLM guess. The LLM only narrates it.

Determinism: same journeys + same model -> same output. No LLM, no clock, no randomness,
no network. The position-based weights are tunable fields, not magic numbers.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from .models import (
    AttributionModel,
    AttributionView,
    Channel,
    ChannelAttribution,
    Citation,
    ConversionJourney,
    Market,
    Touchpoint,
    Vertical,
)


@dataclass(frozen=True, slots=True)
class AttributionService:
    """Pure, deterministic multi-touch attribution.

    ``first_weight`` / ``last_weight`` set the 40/20/40 position-based split (the middle
    touchpoints share the remainder). They are tunables, not magic numbers.
    """

    first_weight: float = 0.4
    last_weight: float = 0.4

    def attribute(
        self,
        journeys: tuple[ConversionJourney, ...] | list[ConversionJourney],
        model: AttributionModel,
        market: Market,
        vertical: Vertical,
    ) -> AttributionView:
        """Distribute conversion + revenue credit across channels for ``model``."""
        converting = [j for j in journeys if j.converted and j.touchpoints]
        # Per-channel running totals (ordered by first appearance for stable output).
        conv: OrderedDict[Channel, float] = OrderedDict()
        rev: OrderedDict[Channel, float] = OrderedDict()
        cites: dict[Channel, list[Citation]] = {}
        total_conv = 0.0
        total_rev = 0.0

        for journey in converting:
            weights = self._weights(journey.touchpoints, model)
            total_conv += 1.0
            total_rev += journey.revenue
            for tp, w in zip(journey.touchpoints, weights, strict=True):
                conv[tp.channel] = conv.get(tp.channel, 0.0) + w
                rev[tp.channel] = rev.get(tp.channel, 0.0) + w * journey.revenue
                if tp.citation is not None:
                    cites.setdefault(tp.channel, []).append(tp.citation)

        channels = tuple(
            ChannelAttribution(
                channel=ch,
                attributed_conversions=round(conv[ch], 6),
                attributed_revenue=round(rev[ch], 6),
                credit_share=round(conv[ch] / total_conv, 6) if total_conv > 0 else 0.0,
                citations=self._dedup_citations(cites.get(ch, [])),
            )
            for ch in self._ordered_channels(conv)
        )
        return AttributionView(
            model=model,
            market=market,
            vertical=vertical,
            channels=channels,
            total_conversions=round(total_conv, 6),
            total_revenue=round(total_rev, 6),
            journeys_considered=len(converting),
        )

    # ------------------------------------------------------------------ #
    # Credit weights per model (each journey's weights sum to 1.0)
    # ------------------------------------------------------------------ #
    def _weights(self, touchpoints: tuple[Touchpoint, ...], model: AttributionModel) -> list[float]:
        n = len(touchpoints)
        if n == 0:
            return []
        if n == 1:
            return [1.0]
        if model is AttributionModel.LAST_TOUCH:
            return [0.0] * (n - 1) + [1.0]
        if model is AttributionModel.FIRST_TOUCH:
            return [1.0] + [0.0] * (n - 1)
        if model is AttributionModel.LINEAR:
            return [1.0 / n] * n
        return self._position_based(n)

    def _position_based(self, n: int) -> list[float]:
        """40/20/40: first and last get a fixed share; the middle splits the remainder."""
        if n == 2:
            # No middle: split the configured first/last weights proportionally to 1.0.
            total = self.first_weight + self.last_weight
            if total <= 0:
                return [0.5, 0.5]
            return [self.first_weight / total, self.last_weight / total]
        middle = 1.0 - self.first_weight - self.last_weight
        if middle < 0:
            # Misconfigured tunables (first_weight + last_weight > 1): fall back to a
            # proportional first/last split with no middle credit, never negative weights.
            total = self.first_weight + self.last_weight
            first = self.first_weight / total
            last = self.last_weight / total
            return [first] + [0.0] * (n - 2) + [last]
        per_middle = middle / (n - 2)
        return [self.first_weight] + [per_middle] * (n - 2) + [self.last_weight]

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _ordered_channels(conv: OrderedDict[Channel, float]) -> list[Channel]:
        # Highest credit first, then first-seen order via the channel enum value.
        return sorted(conv, key=lambda ch: (-conv[ch], ch.value))

    @staticmethod
    def _dedup_citations(citations: list[Citation]) -> tuple[Citation, ...]:
        seen: set[tuple[str, int | None]] = set()
        out: list[Citation] = []
        for c in citations:
            key = (c.source_id, c.page)
            if key not in seen:
                seen.add(key)
                out.append(c)
        return tuple(out)
