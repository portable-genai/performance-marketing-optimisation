"""OptimisationService — deterministic bid / budget reallocation.

The third deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given the per-channel efficiency report and the current daily
budgets, it proposes a **budget-neutral** reallocation: cut spend on channels that miss
their ROAS / CAC target and redeploy it onto the efficient channels, weighted by relative
ROAS and bounded by a maximum per-channel step. Moving budget is the consequential action
in D4, so the proposed shift is code an analyst can re-run, not an LLM guess. The LLM only
drafts the human-readable rationale; nothing auto-executes (maker-checker).

Determinism: same efficiency + same budgets -> same plan. No LLM, no clock, no randomness,
no network. The max-step fraction and minimum-ROAS gap are tunable fields, not magic
numbers. The plan is budget-neutral: the sum of all deltas is (within rounding) zero.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    BidStrategy,
    BudgetPlan,
    BudgetShift,
    Channel,
    ChannelEfficiency,
    Citation,
    EfficiencyReport,
    Market,
    Severity,
    ShiftDirection,
    Vertical,
)


@dataclass(frozen=True, slots=True)
class OptimisationService:
    """Pure, deterministic budget-neutral reallocation toward efficient channels."""

    # The largest fraction of a channel's current budget that may move in one step.
    max_step_fraction: float = 0.25
    # A shift below this absolute delta is treated as HOLD (noise, not worth moving).
    min_shift: float = 1.0

    def plan(
        self,
        efficiency: EfficiencyReport,
        budgets: dict[Channel, float],
        market: Market,
        vertical: Vertical,
    ) -> BudgetPlan:
        """Propose a budget-neutral reallocation from under- to over-performers."""
        total_budget = sum(budgets.values())
        # Channels that miss target give up budget; efficient channels receive it.
        donors = [c for c in efficiency.channels if not self._meets(c)]
        receivers = [c for c in efficiency.channels if self._meets(c) and c.roas > 0]

        cuts: dict[Channel, float] = {}
        freed = 0.0
        for c in donors:
            current = budgets.get(c.channel, 0.0)
            cut = round(current * self.max_step_fraction, 6)
            if cut >= self.min_shift:
                cuts[c.channel] = cut
                freed += cut

        # A receiver may only take in up to its own max step, so the plan can absorb at most
        # the sum of those caps. Free no more than that (keeping the plan budget-neutral): if
        # the donors free more than the receivers can stably accept, scale the cuts down to
        # the absorbable amount rather than over-funding a single channel.
        absorbable = sum(budgets.get(c.channel, 0.0) * self.max_step_fraction for c in receivers)
        if freed > absorbable and freed > 0:
            scale = absorbable / freed
            cuts = {ch: round(cut * scale, 6) for ch, cut in cuts.items()}
            freed = sum(cuts.values())

        gains = self._distribute(freed, receivers, budgets)

        shifts: list[BudgetShift] = []
        for c in efficiency.channels:
            current = budgets.get(c.channel, 0.0)
            delta = round(gains.get(c.channel, 0.0) - cuts.get(c.channel, 0.0), 6)
            shifts.append(self._shift(c, current, delta))
        shifts.sort(key=lambda s: (-abs(s.delta), s.channel.value))
        return BudgetPlan(
            market=market,
            vertical=vertical,
            shifts=tuple(shifts),
            total_budget=round(total_budget, 6),
        )

    # ------------------------------------------------------------------ #
    # Distribution
    # ------------------------------------------------------------------ #
    def _distribute(
        self,
        freed: float,
        receivers: list[ChannelEfficiency],
        budgets: dict[Channel, float],
    ) -> dict[Channel, float]:
        """Share ``freed`` budget across receivers in proportion to their ROAS.

        ROAS-weighted, but each receiver's intake is bounded by its own max-step cap (the
        per-channel stability bound). Budget the caller could not pre-scale away (a receiver
        hitting its cap) is re-shared across the receivers that still have headroom via a
        water-filling pass, so the freed budget is fully and neutrally redeployed whenever the
        receivers can collectively absorb it, and no channel ever exceeds its cap.
        """
        if freed <= 0 or not receivers:
            return {}
        caps = {c.channel: budgets.get(c.channel, 0.0) * self.max_step_fraction for c in receivers}
        gains: dict[Channel, float] = {c.channel: 0.0 for c in receivers}
        remaining = freed
        # Receivers that can still take more budget (cap not yet reached).
        open_channels = [c for c in receivers if caps[c.channel] > gains[c.channel]]
        # Iterate: distribute by ROAS share among open channels; any overflow above a cap is
        # clipped and redistributed in the next pass. Terminates because each pass either
        # exhausts ``remaining`` or closes at least one channel.
        while remaining > 1e-9 and open_channels:
            weight_total = sum(c.roas for c in open_channels)
            if weight_total <= 0:
                break
            newly_closed: list[ChannelEfficiency] = []
            distributed = 0.0
            for c in open_channels:
                headroom = caps[c.channel] - gains[c.channel]
                want = remaining * (c.roas / weight_total)
                take = min(want, headroom)
                gains[c.channel] += take
                distributed += take
                if take >= headroom - 1e-9:
                    newly_closed.append(c)
            remaining -= distributed
            if distributed <= 1e-9:
                break
            for c in newly_closed:
                open_channels.remove(c)
        return {ch: round(v, 6) for ch, v in gains.items()}

    # ------------------------------------------------------------------ #
    # Shift construction
    # ------------------------------------------------------------------ #
    def _shift(self, c: ChannelEfficiency, current: float, delta: float) -> BudgetShift:
        if abs(delta) < self.min_shift:
            direction = ShiftDirection.HOLD
            delta = 0.0
        elif delta > 0:
            direction = ShiftDirection.INCREASE
        else:
            direction = ShiftDirection.DECREASE
        proposed = round(current + delta, 6)
        return BudgetShift(
            channel=c.channel,
            direction=direction,
            current_budget=round(current, 6),
            proposed_budget=proposed,
            delta=round(delta, 6),
            rationale=self._rationale(c, direction, delta),
            severity=self._severity(current, delta),
            citations=self._citations(c),
        )

    @staticmethod
    def _meets(c: ChannelEfficiency) -> bool:
        return c.meets_roas_target and c.meets_cac_target

    @staticmethod
    def _rationale(c: ChannelEfficiency, direction: ShiftDirection, delta: float) -> str:
        if direction is ShiftDirection.HOLD:
            return f"{c.channel.value}: on target (ROAS {c.roas:.2f}); hold budget."
        verb = "increase" if direction is ShiftDirection.INCREASE else "decrease"
        return (
            f"{c.channel.value}: ROAS {c.roas:.2f}, CAC {c.cac:.2f}; {verb} by "
            f"{abs(delta):.2f} ({'meets' if direction is ShiftDirection.INCREASE else 'misses'} "
            "target)."
        )

    def _severity(self, current: float, delta: float) -> Severity:
        if abs(delta) < self.min_shift:
            return Severity.LOW
        if current <= 0:
            return Severity.MEDIUM
        fraction = abs(delta) / current
        if fraction >= self.max_step_fraction - 1e-9:
            return Severity.HIGH
        if fraction >= self.max_step_fraction / 2:
            return Severity.MEDIUM
        return Severity.LOW

    @staticmethod
    def _citations(c: ChannelEfficiency) -> tuple[Citation, ...]:
        return c.citations


def budgets_from_strategies(strategies: tuple[BidStrategy, ...]) -> dict[Channel, float]:
    """Helper: extract the current daily budget per channel from bid strategies."""
    return {s.channel: s.daily_budget for s in strategies}
