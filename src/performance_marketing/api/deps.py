"""Service factories — build domain services from the DI container.

One place that wires the ports resolved by :class:`performance_marketing.config.Container`
into the domain orchestrator, so the CLI, API and agent layers share identical wiring.
"""

from __future__ import annotations

from functools import lru_cache

from ..config import Container, build_container
from ..domain.anomaly_service import AnomalyService
from ..domain.attribution_service import AttributionService
from ..domain.optimisation_service import OptimisationService
from ..domain.services import PerformanceReportService
from ..domain.significance_service import SignificanceService


@lru_cache(maxsize=1)
def get_container() -> Container:
    return build_container()


def make_report_service(container: Container | None = None) -> PerformanceReportService:
    container = container or get_container()
    policy = container.settings.policy
    return PerformanceReportService(
        metrics=container.metrics,
        ad_platform=container.ad_platform,
        llm=container.llm,
        guardrail=container.guardrail,
        tracer=container.tracer,
        audit=container.audit,
        attribution=AttributionService(
            first_weight=policy.attribution_first_weight,
            last_weight=policy.attribution_last_weight,
        ),
        optimisation=OptimisationService(
            max_step_fraction=policy.optimisation_max_step_fraction,
            min_shift=policy.optimisation_min_shift,
        ),
        significance=SignificanceService(
            alpha=policy.significance_alpha,
            min_sample_per_arm=policy.significance_min_sample_per_arm,
        ),
        anomaly=AnomalyService(
            z_threshold=policy.anomaly_z_threshold,
            high_threshold=policy.anomaly_high_threshold,
            critical_threshold=policy.anomaly_critical_threshold,
            min_window=policy.anomaly_min_window,
        ),
        review_router=container.review_router,
    )
