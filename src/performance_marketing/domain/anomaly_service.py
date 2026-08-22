"""AnomalyService — deterministic robust-z anomaly detection.

The fifth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given a dated series of metric points it flags spikes / drops with
a **robust z-score** (deviation from the median, scaled by the median absolute deviation),
which is resistant to outliers in the very series it is screening. Anomalies trigger alerts
and budget pauses, so detection is code an auditor can re-run, not an LLM hunch. The LLM
only narrates the anomaly.

Determinism: same series + same ``as_of`` index window -> same output. No LLM, no clock
read inside the method, no randomness, no network. The robust-z threshold and the minimum
window are tunable fields, not magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Anomaly,
    AnomalyKind,
    AnomalyReport,
    Citation,
    Market,
    MetricPoint,
    Severity,
    Vertical,
)

# 0.6745 = the 0.75 quantile of the standard normal; scales MAD to a normal-consistent sigma.
_MAD_SCALE = 0.6745


@dataclass(frozen=True, slots=True)
class AnomalyService:
    """Pure, deterministic robust-z anomaly detection over a metric series."""

    z_threshold: float = 3.0  # robust-z magnitude above which a point is anomalous
    high_threshold: float = 4.0  # robust-z magnitude that escalates severity to HIGH
    critical_threshold: float = 6.0
    min_window: int = 4  # need at least this many comparison points to judge

    def detect(
        self,
        points: tuple[MetricPoint, ...] | list[MetricPoint],
        market: Market,
        vertical: Vertical,
    ) -> AnomalyReport:
        """Flag spikes / drops across every metric present in ``points``."""
        by_metric: dict[str, list[MetricPoint]] = {}
        for p in points:
            by_metric.setdefault(p.metric, []).append(p)

        anomalies: list[Anomaly] = []
        for metric in sorted(by_metric):
            series = sorted(by_metric[metric], key=lambda p: p.observed_date)
            anomalies.extend(self._detect_one(series))
        # Most severe / most deviant first for a reviewer-friendly order.
        anomalies.sort(key=lambda a: (-abs(a.deviation), a.metric, a.observed_date))
        return AnomalyReport(market=market, vertical=vertical, anomalies=tuple(anomalies))

    # ------------------------------------------------------------------ #
    # Per-metric detection
    # ------------------------------------------------------------------ #
    def _detect_one(self, series: list[MetricPoint]) -> list[Anomaly]:
        if len(series) < self.min_window + 1:
            return []
        # The latest point is the candidate; the prior window is the baseline.
        baseline = series[:-1]
        candidate = series[-1]
        median = self._median([p.value for p in baseline])
        mad = self._mad([p.value for p in baseline], median)
        deviation = self._robust_z(candidate.value, median, mad)
        if abs(deviation) < self.z_threshold:
            return []
        kind = AnomalyKind.SPIKE if deviation > 0 else AnomalyKind.DROP
        return [
            Anomaly(
                metric=candidate.metric,
                observed_date=candidate.observed_date,
                value=round(candidate.value, 6),
                baseline=round(median, 6),
                deviation=round(deviation, 6),
                kind=kind,
                severity=self._severity(abs(deviation)),
                rationale=(
                    f"{candidate.metric} {kind.value}: {candidate.value:.2f} vs baseline "
                    f"{median:.2f} (robust z {deviation:.2f})."
                ),
                citations=self._citations(candidate),
            )
        ]

    # ------------------------------------------------------------------ #
    # Robust statistics (stdlib only)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _median(values: list[float]) -> float:
        s = sorted(values)
        n = len(s)
        if n == 0:
            return 0.0
        mid = n // 2
        if n % 2 == 1:
            return s[mid]
        return (s[mid - 1] + s[mid]) / 2.0

    def _mad(self, values: list[float], median: float) -> float:
        return self._median([abs(v - median) for v in values])

    def _robust_z(self, value: float, median: float, mad: float) -> float:
        if mad <= 0:
            # Degenerate window (no spread): only an exact match is non-anomalous.
            return (
                0.0
                if value == median
                else (self.critical_threshold + 1.0) * (1.0 if value > median else -1.0)
            )
        return _MAD_SCALE * (value - median) / mad

    def _severity(self, magnitude: float) -> Severity:
        if magnitude >= self.critical_threshold:
            return Severity.CRITICAL
        if magnitude >= self.high_threshold:
            return Severity.HIGH
        return Severity.MEDIUM

    @staticmethod
    def _citations(point: MetricPoint) -> tuple[Citation, ...]:
        return (point.citation,) if point.citation is not None else ()
