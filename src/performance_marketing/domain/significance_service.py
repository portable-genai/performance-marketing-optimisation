"""SignificanceService — deterministic A/B significance (two-proportion z-test).

The fourth deterministic engine (see the ``deterministic-domain-service`` skill): pure,
stdlib-only, replayable. Given an :class:`AbTest` (control + variant, each with visitors
and conversions) it computes the conversion rates, the absolute / relative lift, a pooled
two-proportion z-statistic, the two-sided p-value (via an stdlib erf-based normal CDF) and
a ship / stop / keep-running verdict at the configured significance level. Whether to ship
a variant decides real spend, so it is code an analyst can re-run, not an LLM call. The LLM
only narrates the verdict.

Determinism: same counts -> same output. No LLM, no clock, no randomness, no network. The
normal CDF uses :func:`math.erf` so there is no SciPy dependency. ``alpha`` and the minimum
sample size are tunable fields, not magic numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import AbResult, AbTest, AbVariant, AbVerdict, Citation


def _normal_cdf(z: float) -> float:
    """Standard-normal CDF via the error function (stdlib only)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def two_sided_p_value(z: float) -> float:
    """Two-sided p-value for a z-statistic."""
    return 2.0 * (1.0 - _normal_cdf(abs(z)))


@dataclass(frozen=True, slots=True)
class SignificanceService:
    """Pure, deterministic two-proportion significance test for an A/B experiment."""

    alpha: float = 0.05  # significance level (two-sided)
    min_sample_per_arm: int = 100  # below this an arm is treated as underpowered

    def evaluate(self, test: AbTest) -> AbResult:
        """Compute lift, z, p-value and a ship / stop / keep-running verdict."""
        control = test.control
        variant = test.variant
        p_c = control.rate
        p_v = variant.rate
        absolute = p_v - p_c
        relative = (absolute / p_c) if p_c > 0 else 0.0

        z = self._z_score(control, variant)
        p_value = two_sided_p_value(z)
        powered = (
            control.visitors >= self.min_sample_per_arm
            and variant.visitors >= self.min_sample_per_arm
        )
        significant = powered and p_value < self.alpha
        verdict = self._verdict(significant, absolute)
        return AbResult(
            test_id=test.id,
            metric=test.metric,
            control_rate=round(p_c, 6),
            variant_rate=round(p_v, 6),
            absolute_lift=round(absolute, 6),
            relative_lift=round(relative, 6),
            z_score=round(z, 6),
            p_value=round(p_value, 6),
            significant=significant,
            verdict=verdict,
            rationale=self._rationale(verdict, p_value, powered, relative),
            citations=self._citations(test),
        )

    # ------------------------------------------------------------------ #
    # Statistics
    # ------------------------------------------------------------------ #
    @staticmethod
    def _z_score(control: AbVariant, variant: AbVariant) -> float:
        n_c, n_v = control.visitors, variant.visitors
        if n_c <= 0 or n_v <= 0:
            return 0.0
        p_pool = (control.conversions + variant.conversions) / (n_c + n_v)
        se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_c + 1.0 / n_v))
        if se <= 0:
            return 0.0
        return (variant.rate - control.rate) / se

    def _verdict(self, significant: bool, absolute: float) -> AbVerdict:
        if not significant:
            return AbVerdict.KEEP_RUNNING
        return AbVerdict.SHIP if absolute > 0 else AbVerdict.STOP

    @staticmethod
    def _rationale(verdict: AbVerdict, p_value: float, powered: bool, relative: float) -> str:
        if not powered:
            return f"Underpowered (below minimum sample per arm); p={p_value:.4f}. Keep running."
        if verdict is AbVerdict.SHIP:
            return f"Variant wins: +{relative * 100:.1f}% relative lift, p={p_value:.4f}. Ship."
        if verdict is AbVerdict.STOP:
            return f"Variant loses: {relative * 100:.1f}% relative lift, p={p_value:.4f}. Stop."
        return f"Not significant yet (p={p_value:.4f}). Keep running."

    @staticmethod
    def _citations(test: AbTest) -> tuple[Citation, ...]:
        return (test.citation,) if test.citation is not None else ()
