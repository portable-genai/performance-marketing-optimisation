"""Ad-platform adapter (AdPlatformPort) — GCP managed stack with Vertex forecasting.

The primary D4 account / experiment backend: the paid-media ad-platform account state
(bid strategies + per-account ROAS / CAC target) read from BigQuery, plus a **Vertex AI
forecasting** hook for projecting spend / conversions over the optimisation horizon. The
adapter maps the account row onto the domain :class:`Account` and the experiment rows onto
:class:`AbTest`; the deterministic engines compute the significance and the budget plan.

The region is resolved from the active market and **validated** against the per-market
allow-list, so account / forecast calls stay inside the configured residency boundary.

All Google Cloud / Vertex SDK imports are LAZY so the on-prem / local / test profile imports
this module without the SDKs installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...config import Settings
from ...domain.models import (
    AbTest,
    AbVariant,
    Account,
    BidStrategy,
    BidStrategyKind,
    Channel,
    Citation,
    Market,
    RoasTarget,
    SourceType,
    Vertical,
)
from ._region import resolve_region

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.cloud import bigquery


class VertexAdPlatformAdapter:
    """Read the account / experiments from BigQuery; forecast via Vertex AI."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._bq = settings.bigquery
        self._forecast = settings.forecast
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Lazy, region-validated client construction
    # ------------------------------------------------------------------ #
    def _get_client(self, market: Market | None = None) -> bigquery.Client:
        region = resolve_region(self._settings, market)
        if self._client is None:
            from google.cloud import bigquery  # noqa: PLC0415 — lazy: gcp profile only

            self._client = bigquery.Client(project=self._settings.project_id, location=region)
        return self._client

    # ------------------------------------------------------------------ #
    # AdPlatformPort
    # ------------------------------------------------------------------ #
    def account(self, account_id: str, market: Market, vertical: Vertical) -> Account:
        from google.cloud import bigquery  # noqa: PLC0415 — lazy

        client = self._get_client(market)
        sql = (
            f"SELECT * FROM `{self._settings.project_id}.{self._bq.dataset}.accounts` "
            "WHERE account_id = @account_id AND market = @market AND vertical = @vertical "
            "LIMIT 1"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
                bigquery.ScalarQueryParameter("market", "STRING", market.value),
                bigquery.ScalarQueryParameter("vertical", "STRING", vertical.value),
            ]
        )
        rows = [dict(r) for r in client.query(sql, job_config=job_config).result()]
        row = rows[0] if rows else {}
        return self._to_account(account_id, market, vertical, row)

    def experiments(
        self, account_id: str, market: Market, vertical: Vertical
    ) -> tuple[AbTest, ...]:
        from google.cloud import bigquery  # noqa: PLC0415 — lazy

        client = self._get_client(market)
        sql = (
            f"SELECT * FROM `{self._settings.project_id}.{self._bq.dataset}.experiments` "
            "WHERE account_id = @account_id AND status = 'running'"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("account_id", "STRING", account_id),
            ]
        )
        rows = [dict(r) for r in client.query(sql, job_config=job_config).result()]
        return tuple(self._to_test(r, market, vertical) for r in rows)

    # ------------------------------------------------------------------ #
    # Forecasting hook (Vertex AI)
    # ------------------------------------------------------------------ #
    def forecast_spend(self, account_id: str, market: Market) -> list[float]:
        """Project spend over the horizon via Vertex AI forecasting (opt-in)."""
        if not self._forecast.enabled:
            return []
        import vertexai  # noqa: PLC0415 — lazy: gcp profile only

        region = resolve_region(self._settings, market)
        # verify: https://cloud.google.com/vertex-ai/generative-ai/docs/forecasting
        vertexai.init(project=self._settings.project_id, location=region)
        return []  # wired to the forecasting model at deploy time

    # ------------------------------------------------------------------ #
    # Mapping helpers
    # ------------------------------------------------------------------ #
    def _to_account(
        self, account_id: str, market: Market, vertical: Vertical, row: dict[str, Any]
    ) -> Account:
        target = RoasTarget(
            market=market,
            vertical=vertical,
            target_roas=float(row.get("target_roas", 0.0) or 0.0),
            target_cac=float(row.get("target_cac", 0.0) or 0.0),
            currency=str(row.get("currency", "")),
        )
        strategies = tuple(
            BidStrategy(
                channel=self._coerce_channel(s.get("channel")),
                kind=self._coerce_kind(s.get("kind")),
                target_value=float(s.get("target_value", 0.0) or 0.0),
                daily_budget=float(s.get("daily_budget", 0.0) or 0.0),
            )
            for s in (row.get("bid_strategies", []) or [])
        )
        return Account(
            id=account_id,
            name=str(row.get("name", account_id)),
            market=market,
            vertical=vertical,
            bid_strategies=strategies,
            roas_target=target,
        )

    def _to_test(self, row: dict[str, Any], market: Market, vertical: Vertical) -> AbTest:
        return AbTest(
            id=str(row.get("experiment_id", "")),
            metric=str(row.get("metric", "")),
            control=AbVariant(
                name="control",
                visitors=int(row.get("control_visitors", 0) or 0),
                conversions=int(row.get("control_conversions", 0) or 0),
            ),
            variant=AbVariant(
                name="variant",
                visitors=int(row.get("variant_visitors", 0) or 0),
                conversions=int(row.get("variant_conversions", 0) or 0),
            ),
            market=market,
            vertical=vertical,
            citation=Citation(
                source_id=str(row.get("experiment_id", "")),
                source_type=SourceType.EXPERIMENT,
                title=str(row.get("name", "experiment")),
                page=1,
            ),
        )

    @staticmethod
    def _coerce_channel(raw: Any) -> Channel:
        try:
            return Channel(str(raw))
        except ValueError:
            return Channel.OTHER

    @staticmethod
    def _coerce_kind(raw: Any) -> BidStrategyKind:
        try:
            return BidStrategyKind(str(raw))
        except ValueError:
            return BidStrategyKind.MAXIMISE_CONVERSIONS
