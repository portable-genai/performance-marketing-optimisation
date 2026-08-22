"""Unit tests for the deterministic multi-touch attribution engine."""

from __future__ import annotations

from performance_marketing.domain.attribution_service import AttributionService
from performance_marketing.domain.models import (
    AttributionModel,
    Channel,
    ConversionJourney,
    Market,
    Touchpoint,
    Vertical,
)

SVC = AttributionService()


def _tp(channel: Channel, pos: int) -> Touchpoint:
    return Touchpoint(channel=channel, observed_date="2026-06-20", position=pos)


def _journey(channels: list[Channel], revenue: float = 100.0, converted: bool = True):
    return ConversionJourney(
        id="j",
        touchpoints=tuple(_tp(c, i) for i, c in enumerate(channels)),
        converted=converted,
        revenue=revenue,
    )


def test_position_based_never_produces_negative_weights_when_misconfigured():
    """Regression: misconfigured tunables (first+last > 1) must not yield negative credit.

    With first_weight + last_weight > 1.0 the middle remainder goes negative; the engine
    must fall back to a first/last-only split rather than crediting middle touchpoints a
    negative (and total-distorting) share. Every per-journey weight stays in [0, 1] and the
    journey's weights still sum to 1.0.
    """
    svc = AttributionService(first_weight=0.6, last_weight=0.6)
    weights = svc._position_based(4)
    assert all(w >= 0.0 for w in weights)
    assert abs(sum(weights) - 1.0) < 1e-9
    assert weights[1] == 0.0 and weights[2] == 0.0


def test_last_touch_credits_only_last_channel():
    j = _journey([Channel.SEARCH, Channel.SOCIAL, Channel.DISPLAY])
    view = SVC.attribute([j], AttributionModel.LAST_TOUCH, Market.SG, Vertical.BANKING)
    assert view.credit_for(Channel.DISPLAY) == 1.0
    assert view.credit_for(Channel.SEARCH) == 0.0


def test_first_touch_credits_only_first_channel():
    j = _journey([Channel.SEARCH, Channel.SOCIAL])
    view = SVC.attribute([j], AttributionModel.FIRST_TOUCH, Market.SG, Vertical.BANKING)
    assert view.credit_for(Channel.SEARCH) == 1.0
    assert view.credit_for(Channel.SOCIAL) == 0.0


def test_linear_splits_credit_evenly():
    j = _journey([Channel.SEARCH, Channel.SOCIAL, Channel.DISPLAY, Channel.VIDEO])
    view = SVC.attribute([j], AttributionModel.LINEAR, Market.SG, Vertical.BANKING)
    for ch in (Channel.SEARCH, Channel.SOCIAL, Channel.DISPLAY, Channel.VIDEO):
        assert abs(view.credit_for(ch) - 0.25) < 1e-9


def test_position_based_is_40_20_40():
    j = _journey([Channel.SEARCH, Channel.SOCIAL, Channel.DISPLAY])
    view = SVC.attribute([j], AttributionModel.POSITION_BASED, Market.SG, Vertical.BANKING)
    assert abs(view.credit_for(Channel.SEARCH) - 0.4) < 1e-9
    assert abs(view.credit_for(Channel.DISPLAY) - 0.4) < 1e-9
    assert abs(view.credit_for(Channel.SOCIAL) - 0.2) < 1e-9


def test_credit_shares_sum_to_one():
    j1 = _journey([Channel.SEARCH, Channel.SOCIAL])
    j2 = _journey([Channel.DISPLAY])
    view = SVC.attribute([j1, j2], AttributionModel.POSITION_BASED, Market.SG, Vertical.BANKING)
    total = sum(c.credit_share for c in view.channels)
    assert abs(total - 1.0) < 1e-9


def test_revenue_is_attributed():
    j = _journey([Channel.SEARCH, Channel.SOCIAL], revenue=1000.0)
    view = SVC.attribute([j], AttributionModel.LINEAR, Market.SG, Vertical.BANKING)
    assert abs(view.total_revenue - 1000.0) < 1e-9
    rev = {c.channel: c.attributed_revenue for c in view.channels}
    assert abs(rev[Channel.SEARCH] - 500.0) < 1e-9


def test_non_converting_journeys_are_ignored():
    j = _journey([Channel.SEARCH], converted=False)
    view = SVC.attribute([j], AttributionModel.LAST_TOUCH, Market.SG, Vertical.BANKING)
    assert view.total_conversions == 0.0
    assert view.channels == ()


def test_single_touchpoint_gets_full_credit():
    j = _journey([Channel.SEARCH])
    view = SVC.attribute([j], AttributionModel.POSITION_BASED, Market.SG, Vertical.BANKING)
    assert view.credit_for(Channel.SEARCH) == 1.0


def test_determinism():
    j = _journey([Channel.SEARCH, Channel.SOCIAL, Channel.DISPLAY])
    a = SVC.attribute([j], AttributionModel.POSITION_BASED, Market.SG, Vertical.BANKING)
    b = SVC.attribute([j], AttributionModel.POSITION_BASED, Market.SG, Vertical.BANKING)
    assert [c.channel for c in a.channels] == [c.channel for c in b.channels]
    assert [c.credit_share for c in a.channels] == [c.credit_share for c in b.channels]
