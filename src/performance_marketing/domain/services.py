"""Domain services aggregator — one import surface for the wiring layers.

The API, CLI and agent layers import services from here so that adding or renaming a
service is a single-file change at the boundary. The orchestrator
(:class:`PerformanceReportService`) composes the five deterministic engines and the ports.
"""

from __future__ import annotations

from .anomaly_service import AnomalyService
from .attribution_service import AttributionService
from .efficiency_service import EfficiencyService
from .optimisation_service import OptimisationService
from .report_service import PerformanceReportService
from .significance_service import SignificanceService

__all__ = [
    "PerformanceReportService",
    "AttributionService",
    "EfficiencyService",
    "OptimisationService",
    "SignificanceService",
    "AnomalyService",
]
