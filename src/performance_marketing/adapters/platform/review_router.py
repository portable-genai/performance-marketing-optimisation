"""Platform ReviewRouterPort: submit the routed report review to Hrz7 via ``review-kit``.

Builds the review from the escalated performance report and submits it to the Hrz7 service intake
(``POST /v1/service/reviews``), S2S-authenticated. The Hrz7 base URL comes from the environment
(``MKT4_HRZ7_URL``) and the S2S credentials from this repo's shared env-var names
(``HRZ_S2S_TOKEN`` / ``HRZ_S2S_SIGNING_KEY``, the same pair the other platform delegates use). No
cloud SDK is involved (the kit uses stdlib ``urllib`` + wire-compatible S2S headers), so this
module imports cleanly with no GCP SDK; it is bound under the ``gcp`` and ``platform`` profiles
because it makes a real network call to a sibling service.
"""

from __future__ import annotations

from review_kit import ReviewClient

from ...config import Settings
from ...domain.models import PerformanceReport
from ...envread import read_env_setting
from .._review_payload import report_to_review
from ._s2s import SIGNING_KEY_ENV, TOKEN_ENV

_URL_ENV = "MKT4_HRZ7_URL"


class PlatformReviewRouter:
    """Submit escalated performance reports to Hrz7 (rule R8), reusing the shared client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(
        self, report: PerformanceReport, *, maker: str, tenant: str = ""
    ) -> None:  # pragma: no cover - needs live Hrz7
        # Unset and set-but-empty collapse DELIBERATELY: both are closed in the same direction,
        # because there is no default Hrz7 to fall back to and the routing refuses below either
        # way. A localhost default here would be the dangerous shape; there isn't one.
        base_url = read_env_setting(_URL_ENV).value
        if not base_url:
            raise RuntimeError(f"{_URL_ENV} must be set to route reviews to Hrz7")
        client = ReviewClient(base_url, token_env=TOKEN_ENV, signing_key_env=SIGNING_KEY_ENV)
        client.submit(
            report_to_review(report, maker=maker, tenant=tenant),
            actor="mkt4-performance-marketing-optimisation",
        )
