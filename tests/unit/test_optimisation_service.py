"""Unit tests for the deterministic bid / budget optimisation engine."""

from __future__ import annotations

from performance_marketing.domain.efficiency_service import EfficiencyService
from performance_marketing.domain.models import (
    Channel,
    ChannelMetrics,
    Market,
    RoasTarget,
    ShiftDirection,
    Vertical,
)
from performance_marketing.domain.optimisation_service import (
    OptimisationService,
    budgets_from_strategies,
)

EFF = EfficiencyService()
OPT = OptimisationService()


def _m(channel: Channel, spend: float, revenue: float, conv: float) -> ChannelMetrics:
    return ChannelMetrics(channel=channel, spend=spend, revenue=revenue, conversions=conv)


def _efficiency():
    target = RoasTarget(market=Market.SG, vertical=Vertical.ONLINE_RETAIL, target_roas=4.0)
    metrics = [
        _m(Channel.SEARCH, 1000.0, 6000.0, 100.0),  # ROAS 6 efficient
        _m(Channel.SOCIAL, 1000.0, 2000.0, 50.0),  # ROAS 2 underperformer
    ]
    return EFF.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL, target)


def test_underperformer_is_cut_and_efficient_channel_gains():
    eff = _efficiency()
    budgets = {Channel.SEARCH: 1000.0, Channel.SOCIAL: 1000.0}
    plan = OPT.plan(eff, budgets, Market.SG, Vertical.ONLINE_RETAIL)
    shifts = {s.channel: s for s in plan.shifts}
    assert shifts[Channel.SOCIAL].direction is ShiftDirection.DECREASE
    assert shifts[Channel.SEARCH].direction is ShiftDirection.INCREASE


def test_plan_is_budget_neutral():
    eff = _efficiency()
    budgets = {Channel.SEARCH: 1000.0, Channel.SOCIAL: 1000.0}
    plan = OPT.plan(eff, budgets, Market.SG, Vertical.ONLINE_RETAIL)
    total_delta = sum(s.delta for s in plan.shifts)
    assert abs(total_delta) < 1e-6


def test_step_is_bounded_by_max_fraction():
    eff = _efficiency()
    budgets = {Channel.SEARCH: 1000.0, Channel.SOCIAL: 1000.0}
    plan = OPT.plan(eff, budgets, Market.SG, Vertical.ONLINE_RETAIL)
    social = next(s for s in plan.shifts if s.channel is Channel.SOCIAL)
    assert abs(social.delta) <= 1000.0 * OPT.max_step_fraction + 1e-6


def test_all_on_target_holds_everything():
    target = RoasTarget(market=Market.SG, vertical=Vertical.ONLINE_RETAIL, target_roas=1.0)
    metrics = [
        _m(Channel.SEARCH, 1000.0, 6000.0, 100.0),
        _m(Channel.SOCIAL, 1000.0, 5000.0, 100.0),
    ]
    eff = EFF.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL, target)
    plan = OPT.plan(
        eff, {Channel.SEARCH: 1000.0, Channel.SOCIAL: 1000.0}, Market.SG, Vertical.ONLINE_RETAIL
    )
    assert plan.material_shifts == ()


def test_budgets_from_strategies_helper():
    from performance_marketing.domain.models import BidStrategy, BidStrategyKind

    strategies = (
        BidStrategy(channel=Channel.SEARCH, kind=BidStrategyKind.TARGET_ROAS, daily_budget=500.0),
        BidStrategy(channel=Channel.SOCIAL, kind=BidStrategyKind.TARGET_ROAS, daily_budget=300.0),
    )
    budgets = budgets_from_strategies(strategies)
    assert budgets == {Channel.SEARCH: 500.0, Channel.SOCIAL: 300.0}


def test_receiver_intake_is_bounded_by_its_own_max_step():
    """Regression: a receiver must never take in more than its own max-step cap.

    A huge donor frees far more than two small receivers can stably absorb. The earlier
    distribution used ``max(budget*fraction, freed)`` as the cap, which never bound, so a
    small channel could be handed a multiple of its own budget in one step. Each receiver's
    increase must stay within budget * max_step_fraction.
    """
    target = RoasTarget(market=Market.SG, vertical=Vertical.BANKING, target_roas=4.0)
    metrics = [
        _m(Channel.SEARCH, 100.0, 500.0, 10.0),  # ROAS 5, efficient, small budget
        _m(Channel.SOCIAL, 100.0, 400.0, 10.0),  # ROAS 4, efficient, small budget
        _m(Channel.DISPLAY, 10000.0, 100.0, 1.0),  # ROAS 0.01, big underperformer
    ]
    eff = EFF.compute(metrics, Market.SG, Vertical.BANKING, target)
    budgets = {Channel.SEARCH: 100.0, Channel.SOCIAL: 100.0, Channel.DISPLAY: 10000.0}
    plan = OPT.plan(eff, budgets, Market.SG, Vertical.BANKING)
    for s in plan.shifts:
        if s.direction is ShiftDirection.INCREASE:
            cap = s.current_budget * OPT.max_step_fraction
            assert abs(s.delta) <= cap + 1e-6, f"{s.channel} took {s.delta} > cap {cap}"


def test_plan_is_budget_neutral_when_donor_outpaces_receiver_capacity():
    """Regression: budget-neutral even when receivers cannot absorb all freed budget.

    With one tiny receiver and one large underperformer, the freed amount exceeds the
    receivers' combined cap. Cuts must scale down to the absorbable amount so the plan still
    sums to zero (no budget conjured or lost) and no receiver overshoots its cap.
    """
    target = RoasTarget(market=Market.SG, vertical=Vertical.BANKING, target_roas=4.0)
    metrics = [
        _m(Channel.SEARCH, 40.0, 360.0, 4.0),  # ROAS 9, efficient, tiny budget
        _m(Channel.SOCIAL, 400.0, 400.0, 40.0),  # ROAS 1, efficient, mid budget
        _m(Channel.DISPLAY, 1000.0, 10.0, 1.0),  # ROAS 0.01, underperformer
    ]
    eff = EFF.compute(metrics, Market.SG, Vertical.BANKING, target)
    budgets = {Channel.SEARCH: 40.0, Channel.SOCIAL: 400.0, Channel.DISPLAY: 1000.0}
    plan = OPT.plan(eff, budgets, Market.SG, Vertical.BANKING)
    assert abs(sum(s.delta for s in plan.shifts)) < 1e-6
    for s in plan.shifts:
        if s.direction is ShiftDirection.INCREASE:
            assert abs(s.delta) <= s.current_budget * OPT.max_step_fraction + 1e-6


def test_determinism():
    eff = _efficiency()
    budgets = {Channel.SEARCH: 1000.0, Channel.SOCIAL: 1000.0}
    a = OPT.plan(eff, budgets, Market.SG, Vertical.ONLINE_RETAIL)
    b = OPT.plan(eff, budgets, Market.SG, Vertical.ONLINE_RETAIL)
    assert [(s.channel, s.delta) for s in a.shifts] == [(s.channel, s.delta) for s in b.shifts]
