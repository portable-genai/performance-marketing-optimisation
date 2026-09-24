"""The runtime-control seam: what a switched-off control binds, and what a caller reports.

**Disabled adapters.** When a deployment switches a cheap runtime control off
(``MKT_PERF_GUARDRAIL``, ``MKT_PERF_REVIEW_ROUTING``), the container binds one of these
instead of the profile's class. Each satisfies its port and does nothing, so no service grows a
``None`` branch, and the container logs the posture at startup.

**Recording wrapper.** Every caller that hands a report to the router (the API route, the agent
tool, the three MCP tools and both CLI commands) wraps the bound router in
:class:`RecordingReviewRouter` for that one call, so what it returns can say what happened:
``routed``, ``failed``, ``off`` or ``not_required``. A failure is logged and absorbed here,
because an already-audited report must not fail on a console outage, but it is no longer
invisible: the caller reports ``failed``.

There is no redaction wrapper: this service has no PII redaction port.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from ..config import Settings
from ..domain.models import Direction, GuardrailVerdict, PerformanceReport

_log = logging.getLogger(__name__)


class ReviewRouting(StrEnum):
    """What happened to the human-review hand-off for one result."""

    ROUTED = "routed"
    FAILED = "failed"
    OFF = "off"
    NOT_REQUIRED = "not_required"


# --------------------------------------------------------------------------- #
# Disabled adapters
# --------------------------------------------------------------------------- #
class DisabledGuardrail:
    """GuardrailPort with the guardrail switched off: allows everything, text unchanged."""

    enabled = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        return GuardrailVerdict(
            allowed=True, direction=direction, sanitized_text=text, reason="guardrail off"
        )


class DisabledReviewRouter:
    """ReviewRouterPort with routing switched off: nothing is submitted anywhere."""

    enabled = False

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(self, report: PerformanceReport, *, maker: str, tenant: str = "") -> None:
        return None


# --------------------------------------------------------------------------- #
# Per-call disclosure
# --------------------------------------------------------------------------- #
class RecordingReviewRouter:
    """Wraps the bound review router for one caller and records each hand-off's outcome."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._outcomes: list[ReviewRouting] = []

    def route(self, report: PerformanceReport, *, maker: str, tenant: str = "") -> None:
        if not getattr(self._inner, "enabled", True):
            self._outcomes.append(ReviewRouting.OFF)
            return
        try:
            self._inner.route(report, maker=maker, tenant=tenant)
        except Exception as exc:  # noqa: BLE001 - the outcome is reported, never raised
            _log.warning("human-review hand-off failed: %s", type(exc).__name__)
            self._outcomes.append(ReviewRouting.FAILED)
            return
        self._outcomes.append(ReviewRouting.ROUTED)

    @property
    def outcome(self) -> ReviewRouting:
        """One value for the caller: any failure wins, then off, then routed."""
        for worst in (ReviewRouting.FAILED, ReviewRouting.OFF, ReviewRouting.ROUTED):
            if worst in self._outcomes:
                return worst
        return ReviewRouting.NOT_REQUIRED
