"""Unit tests for the deterministic ROAS / CAC efficiency engine."""

from __future__ import annotations

from performance_marketing.domain.efficiency_service import EfficiencyService
from performance_marketing.domain.models import (
    Channel,
    ChannelMetrics,
    Market,
    RoasTarget,
    Vertical,
)

SVC = EfficiencyService()


def _m(channel: Channel, spend: float, revenue: float, conv: float) -> ChannelMetrics:
    return ChannelMetrics(channel=channel, spend=spend, revenue=revenue, conversions=conv)


def test_roas_and_cac_are_computed():
    metrics = [_m(Channel.SEARCH, 1000.0, 4000.0, 100.0)]
    report = SVC.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL)
    c = report.channels[0]
    assert c.roas == 4.0
    assert c.cac == 10.0


def test_blended_figures():
    metrics = [
        _m(Channel.SEARCH, 1000.0, 4000.0, 100.0),
        _m(Channel.SOCIAL, 1000.0, 1000.0, 50.0),
    ]
    report = SVC.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL)
    assert abs(report.blended_roas - 2.5) < 1e-9  # 5000 / 2000
    assert abs(report.blended_cac - (2000.0 / 150.0)) < 1e-5  # rounded to 6 dp


def test_zero_spend_and_zero_conversions_are_safe():
    report = SVC.compute([_m(Channel.SEARCH, 0.0, 0.0, 0.0)], Market.SG, Vertical.BANKING)
    c = report.channels[0]
    assert c.roas == 0.0
    assert c.cac == 0.0


def test_roas_target_floor():
    target = RoasTarget(market=Market.SG, vertical=Vertical.ONLINE_RETAIL, target_roas=4.0)
    metrics = [
        _m(Channel.SEARCH, 1000.0, 5000.0, 100.0),  # ROAS 5 >= 4 OK
        _m(Channel.SOCIAL, 1000.0, 2000.0, 100.0),  # ROAS 2 < 4 MISS
    ]
    report = SVC.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL, target)
    by_ch = {c.channel: c for c in report.channels}
    assert by_ch[Channel.SEARCH].meets_roas_target is True
    assert by_ch[Channel.SOCIAL].meets_roas_target is False
    assert {c.channel for c in report.underperformers} == {Channel.SOCIAL}


def test_cac_target_ceiling():
    target = RoasTarget(market=Market.SG, vertical=Vertical.BANKING, target_cac=30.0)
    metrics = [
        _m(Channel.SEARCH, 1000.0, 4000.0, 100.0),  # CAC 10 <= 30 OK
        _m(Channel.SOCIAL, 1000.0, 500.0, 10.0),  # CAC 100 > 30 MISS
    ]
    report = SVC.compute(metrics, Market.SG, Vertical.BANKING, target)
    by_ch = {c.channel: c for c in report.channels}
    assert by_ch[Channel.SEARCH].meets_cac_target is True
    assert by_ch[Channel.SOCIAL].meets_cac_target is False


def test_cac_target_missed_when_spend_no_conversions():
    target = RoasTarget(market=Market.SG, vertical=Vertical.BANKING, target_cac=30.0)
    report = SVC.compute(
        [_m(Channel.DISPLAY, 500.0, 0.0, 0.0)], Market.SG, Vertical.BANKING, target
    )
    assert report.channels[0].meets_cac_target is False


def test_rows_for_same_channel_are_merged():
    metrics = [
        _m(Channel.SEARCH, 500.0, 2000.0, 50.0),
        _m(Channel.SEARCH, 500.0, 2000.0, 50.0),
    ]
    report = SVC.compute(metrics, Market.SG, Vertical.ONLINE_RETAIL)
    assert len(report.channels) == 1
    assert report.channels[0].spend == 1000.0
    assert report.channels[0].conversions == 100.0


def test_determinism():
    metrics = [_m(Channel.SEARCH, 1000.0, 4000.0, 100.0), _m(Channel.SOCIAL, 800.0, 700.0, 20.0)]
    a = SVC.compute(metrics, Market.SG, Vertical.BANKING)
    b = SVC.compute(metrics, Market.SG, Vertical.BANKING)
    assert [c.roas for c in a.channels] == [c.roas for c in b.channels]
