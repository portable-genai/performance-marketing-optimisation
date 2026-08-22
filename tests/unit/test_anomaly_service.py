"""Unit tests for the deterministic robust-z anomaly detection engine."""

from __future__ import annotations

from performance_marketing.domain.anomaly_service import AnomalyService
from performance_marketing.domain.models import (
    AnomalyKind,
    Market,
    MetricPoint,
    Severity,
    Vertical,
)

SVC = AnomalyService()


def _series(metric: str, values: list[float]) -> list[MetricPoint]:
    return [
        MetricPoint(metric=metric, observed_date=f"2026-06-{10 + i:02d}", value=v)
        for i, v in enumerate(values)
    ]


def test_spike_is_detected():
    points = _series("cpa", [20.0, 21.0, 19.0, 20.5, 20.0, 21.5, 60.0])
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert len(report.anomalies) == 1
    a = report.anomalies[0]
    assert a.kind is AnomalyKind.SPIKE
    assert a.deviation > 0


def test_drop_is_detected():
    points = _series("ctr", [10.0, 11.0, 9.0, 10.5, 10.0, 9.5, 1.0])
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert len(report.anomalies) == 1
    assert report.anomalies[0].kind is AnomalyKind.DROP


def test_stable_series_has_no_anomaly():
    points = _series("cpa", [20.0, 21.0, 19.0, 20.5, 20.0, 21.5, 20.2])
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert report.anomalies == ()


def test_short_series_is_skipped():
    points = _series("cpa", [20.0, 100.0])
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert report.anomalies == ()


def test_multiple_metrics_are_handled_independently():
    points = _series("cpa", [20.0, 21.0, 19.0, 20.5, 20.0, 21.5, 60.0]) + _series(
        "ctr", [5.0, 5.1, 4.9, 5.0, 5.0, 4.95, 5.05]
    )
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    metrics = {a.metric for a in report.anomalies}
    assert metrics == {"cpa"}


def test_severity_escalates_with_magnitude():
    points = _series("cpa", [20.0, 20.0, 20.0, 20.0, 20.0, 20.0, 1000.0])
    report = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert report.anomalies[0].severity is Severity.CRITICAL
    assert report.material


def test_determinism():
    points = _series("cpa", [20.0, 21.0, 19.0, 20.5, 20.0, 21.5, 60.0])
    a = SVC.detect(points, Market.SG, Vertical.BANKING)
    b = SVC.detect(points, Market.SG, Vertical.BANKING)
    assert [x.deviation for x in a.anomalies] == [x.deviation for x in b.anomalies]
