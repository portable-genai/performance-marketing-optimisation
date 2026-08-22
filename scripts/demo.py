#!/usr/bin/env python3
"""Offline synthetic-data demo for D4 (audit-first).

Runs the real ``PerformanceReportService`` over the local (offline) adapters for a few
(vertical, market) accounts, prints a readable, cited trace to stdout, and writes the report
audit views to ``scripts/out/*.json`` for the dependency-free renderer / screenshots. It is
also the end-to-end smoke test for the slice: deterministic, so screenshots never drift.

Usage::

    MKT_PERF_PROFILE=local python scripts/demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from performance_marketing.api.deps import make_report_service
from performance_marketing.config import Container, LocalSettings, Settings
from performance_marketing.domain.models import Market, ReportRequest, Vertical
from performance_marketing.domain.serialization import to_jsonable
from performance_marketing.domain.services import PerformanceReportService

_OUT = Path(__file__).resolve().parent / "out"

_SCENARIOS = [
    ("acct-sg-banking", Market.SG, Vertical.BANKING),
    ("acct-jp-banking", Market.JP, Vertical.BANKING),
    ("acct-jp-online_retail", Market.JP, Vertical.ONLINE_RETAIL),
    ("acct-au-online_retail", Market.AU, Vertical.ONLINE_RETAIL),
]


def _service() -> PerformanceReportService:
    base = Settings.load("config/settings.yaml")
    settings = Settings(
        project_id=base.project_id,
        region=base.region,
        profile="local",
        vertical=base.vertical,
        market=base.market,
        models=base.models,
        bigquery=base.bigquery,
        forecast=base.forecast,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(audit_path=":memory:"),
        policy=base.policy,
        markets=base.markets,
        adapters=base.adapters,
    )
    return make_report_service(Container(settings))


def main() -> int:
    _OUT.mkdir(parents=True, exist_ok=True)
    service = _service()
    for account_id, market, vertical in _SCENARIOS:
        request = ReportRequest(account_id=account_id, market=market, vertical=vertical)
        report = service.build_report(request, actor="demo", tenant="demo-bank")
        print("=" * 78)
        print(f"REPORT: {account_id}  [{market.value}/{vertical.value}]")
        print(f"  review required : {report.requires_human_review}")
        if report.efficiency is not None:
            print(
                f"  blended         : ROAS {report.efficiency.blended_roas:.2f}, "
                f"CAC {report.efficiency.blended_cac:.2f}"
            )
        if report.budget_plan is not None:
            for s in report.budget_plan.material_shifts:
                print(
                    f"  shift [{s.severity.value}]: {s.channel.value} {s.direction.value} "
                    f"{s.delta:+.2f}"
                )
        for r in report.ab_results:
            print(f"  ab            : {r.test_id} -> {r.verdict.value} (p={r.p_value:.4f})")
        if report.anomalies is not None:
            for a in report.anomalies.anomalies:
                print(
                    f"  anomaly [{a.severity.value}]: {a.metric} {a.kind.value} (z {a.deviation:.2f})"
                )
        print(f"  citations       : {len(report.citations)}")
        out_path = _OUT / f"{report.id}.json"
        out_path.write_text(json.dumps(to_jsonable(report), indent=2), encoding="utf-8")
        print(f"  wrote           : {out_path}")
    print("=" * 78)
    print("Demo complete. Audit views written to scripts/out/ (obviously-fictional data).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
