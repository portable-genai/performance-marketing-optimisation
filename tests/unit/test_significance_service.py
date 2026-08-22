"""Unit tests for the deterministic A/B significance engine (two-proportion z-test)."""

from __future__ import annotations

from performance_marketing.domain.models import AbTest, AbVariant, AbVerdict
from performance_marketing.domain.significance_service import (
    SignificanceService,
    two_sided_p_value,
)

SVC = SignificanceService()


def _test(c_v: int, c_c: int, v_v: int, v_c: int) -> AbTest:
    return AbTest(
        id="t",
        metric="rate",
        control=AbVariant(name="control", visitors=c_v, conversions=c_c),
        variant=AbVariant(name="variant", visitors=v_v, conversions=v_c),
    )


def test_clear_winner_ships():
    result = SVC.evaluate(_test(10000, 500, 10000, 650))
    assert result.verdict is AbVerdict.SHIP
    assert result.significant is True
    assert result.p_value < 0.05
    assert result.absolute_lift > 0


def test_clear_loser_stops():
    result = SVC.evaluate(_test(10000, 650, 10000, 500))
    assert result.verdict is AbVerdict.STOP
    assert result.significant is True


def test_underpowered_keeps_running():
    result = SVC.evaluate(_test(50, 5, 50, 7))
    assert result.verdict is AbVerdict.KEEP_RUNNING
    assert result.significant is False


def test_no_difference_keeps_running():
    result = SVC.evaluate(_test(10000, 500, 10000, 500))
    assert result.verdict is AbVerdict.KEEP_RUNNING
    assert abs(result.absolute_lift) < 1e-9


def test_relative_lift_is_computed():
    result = SVC.evaluate(_test(10000, 500, 10000, 600))
    # control 5%, variant 6% -> +20% relative
    assert abs(result.relative_lift - 0.2) < 1e-6


def test_zero_visitors_does_not_crash():
    result = SVC.evaluate(_test(0, 0, 0, 0))
    assert result.z_score == 0.0
    assert result.verdict is AbVerdict.KEEP_RUNNING


def test_p_value_helper_symmetric_and_bounded():
    assert 0.0 <= two_sided_p_value(0.0) <= 1.0
    assert abs(two_sided_p_value(0.0) - 1.0) < 1e-9
    assert two_sided_p_value(5.0) < 0.001


def test_determinism():
    a = SVC.evaluate(_test(10000, 500, 10000, 620))
    b = SVC.evaluate(_test(10000, 500, 10000, 620))
    assert a.z_score == b.z_score
    assert a.p_value == b.p_value
    assert a.verdict == b.verdict
