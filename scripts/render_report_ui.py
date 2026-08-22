#!/usr/bin/env python3
"""Render the D4 audit-first console from the demo JSON into static HTML pages.

Server-side, dependency-free rendering of a cited :class:`PerformanceReport` (summary,
per-channel ROAS / CAC with provenance, multi-touch attribution split, the deterministic
budget plan, the A/B significance verdicts, the anomalies, and the maker-checker "human
review required" banner). It reuses the exact palette of the thin Next.js console so
screenshots match the live UI, and runs entirely offline over the obviously-fictional
synthetic reports written by ``scripts/demo.py``.

    PYTHONPATH=src python scripts/demo.py
    PYTHONPATH=src python scripts/render_report_ui.py scripts/out

Writes ``index.html`` (a small chooser) plus one ``<report-id>.html`` per report. The
rendering functions are also imported by ``scripts/demo_server.py`` for the presenter demo.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any

SEV_COLOR = {
    "low": ("#eef2f7", "#546b8b"),
    "medium": ("#fef3c7", "#92400e"),
    "high": ("#ffedd5", "#c2410c"),
    "critical": ("#fee2e2", "#b91c1c"),
}
SOURCE_LABEL = {
    "metrics": "METRICS",
    "ad_platform": "AD",
    "target": "TARGET",
    "experiment": "EXP",
    "internal": "INTERNAL",
    "other": "SRC",
}
MARKET_LABEL = {"JP": "Japan", "AU": "Australia", "SG": "Singapore"}
VERTICAL_LABEL = {"banking": "Banking", "online_retail": "Online retail"}
VERDICT_LABEL = {"ship": "SHIP", "stop": "STOP", "keep_running": "KEEP RUNNING"}

CSS = """
:root{--ink-50:#f5f7fa;--ink-100:#e6ebf2;--ink-200:#cdd7e4;--ink-300:#a6b6cc;
--ink-400:#7790ae;--ink-500:#546b8b;--ink-600:#3f5470;--ink-700:#33445b;--ink-800:#1f2a3a;
--brand-50:#eef4ff;--brand-100:#dbe7ff;--brand-600:#2945d6;--brand-700:#2237ad;
--ok:#059669;--warn:#d97706;--warn-bg:#fffbeb;
--shadow:0 1px 2px rgba(11,16,26,.06),0 8px 24px rgba(11,16,26,.06);}
*{box-sizing:border-box}
body{margin:0;background:var(--ink-50);color:var(--ink-800);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
font-size:14px;line-height:1.5;padding:24px 18px}
.wrap{max-width:920px;margin:0 auto}
h1{font-size:18px;margin:0 0 2px}
.sub{color:var(--ink-500);font-size:13px;margin:0 0 16px}
.sub b{color:var(--ink-800)}
.pill{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;
border:1px solid var(--brand-100);background:var(--brand-50);color:var(--brand-700);margin-right:6px}
.panel{border:1px solid var(--ink-200);background:#fff;border-radius:10px;box-shadow:var(--shadow);margin-bottom:16px}
.panel>h2{border-bottom:1px solid var(--ink-100);padding:11px 16px;margin:0;font-size:13px;font-weight:600;color:var(--ink-800)}
.panel>.body{padding:16px}
.review{border:1px solid #fcd34d;background:var(--warn-bg);color:#92400e;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;margin-bottom:14px}
.summary{font-size:14px;line-height:1.6}
.row{display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--ink-100)}
.row:last-child{border-bottom:0}
.sev{font-size:11px;font-weight:700;padding:1px 7px;border-radius:5px;white-space:nowrap}
.muted{color:var(--ink-400);font-size:12px}
.bar{flex:0 0 120px;height:8px;border-radius:6px;background:var(--ink-100);border:1px solid var(--ink-200);overflow:hidden}
.bar>span{display:block;height:100%;background:linear-gradient(90deg,#3a60f0,#2945d6)}
.cites{margin-top:8px;display:flex;flex-direction:column;gap:6px}
.cite{display:flex;gap:8px;align-items:baseline;border:1px solid var(--ink-200);background:var(--ink-50);border-radius:7px;padding:7px 10px}
.cite .src{font-family:ui-monospace,Menlo,monospace;font-size:11px;font-weight:600;color:var(--brand-700);background:var(--brand-50);border:1px solid var(--brand-100);border-radius:5px;padding:1px 6px;white-space:nowrap}
.cite .title{font-size:12px;color:var(--ink-700)}
.cite .id{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--ink-500);margin-left:auto;white-space:nowrap}
.cite a{color:var(--brand-600);text-decoration:none;font-size:11px}
a.choose{display:block;padding:10px 12px;border:1px solid var(--ink-200);border-radius:8px;background:#fff;margin-bottom:8px;text-decoration:none;color:var(--ink-800)}
"""


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{esc(title)}</title><style>{CSS}</style></head><body>"
        f"<div class='wrap'>{body}</div></body></html>"
    )


def _citations(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "<div class='muted' data-citation-count='0'>(no citations)</div>"
    rows = []
    for c in citations:
        label = SOURCE_LABEL.get(str(c.get("source_type")), "SRC")
        url = c.get("url") or ""
        link = f"<a href='{esc(url)}'>open</a>" if url else ""
        rows.append(
            f"<div class='cite' data-citation='{esc(c.get('source_id'))}' "
            f"data-citation-type='{esc(c.get('source_type'))}'>"
            f"<span class='src'>{esc(label)}</span>"
            f"<span class='title'>{esc(c.get('title'))}</span>"
            f"<span class='id'>{esc(c.get('source_id'))}</span>{link}"
            "</div>"
        )
    return f"<div class='cites' data-citation-count='{len(citations)}'>" + "".join(rows) + "</div>"


def _panel(title: str, body: str, slug: str) -> str:
    """One result section, carrying a stable styling-independent evidence hook (F2)."""
    return (
        f"<div class='panel' data-panel='{esc(slug)}'><h2>{esc(title)}</h2>"
        f"<div class='body' data-panel-body='{esc(slug)}'>{body}</div></div>"
    )


def render_report(data: dict[str, Any]) -> str:
    """Render one cited PerformanceReport dict into a standalone HTML page."""
    market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
    vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
    head = (
        f"<div data-report='{esc(data.get('id'))}' "
        f"data-report-account='{esc(data.get('account_id'))}' "
        f"data-report-market='{esc(data.get('market'))}' "
        f"data-report-vertical='{esc(data.get('vertical'))}' "
        f"data-report-citations='{len(data.get('citations') or [])}' "
        f"data-report-review='{str(bool(data.get('requires_human_review'))).lower()}'></div>"
        f"<h1>Performance report — {esc(data.get('account_id'))}</h1>"
        f"<p class='sub'><span class='pill'>{esc(market)}</span>"
        f"<span class='pill'>{esc(vertical)}</span> id <b>{esc(data.get('id'))}</b></p>"
    )
    review = ""
    if data.get("requires_human_review"):
        review = (
            "<div class='review' data-review-gate='required'>HUMAN REVIEW REQUIRED — maker-checker "
            "gate. Do not move any budget until a qualified performance lead signs off.</div>"
        )

    summary = _panel("Summary", f"<div class='summary'>{esc(data.get('summary'))}</div>", "summary")

    eff = data.get("efficiency") or {}
    eff_channels = eff.get("channels", [])
    eff_rows = [
        "<div class='row'><div style='flex:1'><b>Blended</b> "
        f"<span class='muted'>ROAS {esc(eff.get('blended_roas'))}, "
        f"CAC {esc(eff.get('blended_cac'))}</span></div></div>"
    ]
    for c in eff_channels:
        ok = bool(c.get("meets_roas_target") and c.get("meets_cac_target"))
        flag = "" if ok else " <span class='muted'>· misses target</span>"
        eff_rows.append(
            f"<div class='row' data-channel='{esc(c.get('channel'))}' "
            f"data-channel-spend='{esc(c.get('spend'))}' "
            f"data-channel-roas='{esc(c.get('roas'))}' "
            f"data-channel-cac='{esc(c.get('cac'))}' "
            f"data-channel-meets-target='{str(ok).lower()}'><div style='flex:1'>"
            f"<b>{esc(c.get('channel'))}</b> <span class='muted'>spend {esc(c.get('spend'))}, "
            f"ROAS {esc(c.get('roas'))}, CAC {esc(c.get('cac'))}</span>{flag}"
            f"{_citations(c.get('citations', []))}</div></div>"
        )
    efficiency = _panel(
        "Channel efficiency (ROAS / CAC)",
        f"<div data-blended-roas='{esc(eff.get('blended_roas'))}' "
        f"data-blended-cac='{esc(eff.get('blended_cac'))}' "
        f"data-channel-count='{len(eff_channels)}'>" + "".join(eff_rows) + "</div>",
        "channel-efficiency",
    )

    attr = data.get("attribution") or {}
    attr_channels = attr.get("channels", [])
    attr_rows = []
    for c in attr_channels:
        pct = int(round(float(c.get("credit_share", 0.0)) * 100))
        attr_rows.append(
            f"<div class='row' data-attr-channel='{esc(c.get('channel'))}' "
            f"data-attr-credit-pct='{pct}' "
            f"data-attr-conversions='{esc(c.get('attributed_conversions'))}' "
            f"data-attr-revenue='{esc(c.get('attributed_revenue'))}'>"
            f"<div style='flex:1'>{esc(c.get('channel'))} "
            f"<span class='muted'>· {esc(c.get('attributed_conversions'))} conv, "
            f"{esc(c.get('attributed_revenue'))} rev</span>"
            f"{_citations(c.get('citations', []))}</div>"
            f"<div class='bar'><span style='width:{pct}%'></span></div>"
            f"<div class='muted'>{pct}%</div></div>"
        )
    attribution = _panel(
        f"Attribution ({esc(attr.get('model'))})",
        f"<div data-attribution-model='{esc(attr.get('model'))}' "
        f"data-attr-channel-count='{len(attr_channels)}' "
        f"data-attr-total-conversions='{esc(attr.get('total_conversions'))}' "
        f"data-attr-total-revenue='{esc(attr.get('total_revenue'))}'>"
        + ("".join(attr_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "attribution",
    )

    plan = data.get("budget_plan") or {}
    material = [s for s in plan.get("shifts", []) if s.get("direction") != "hold"]
    plan_rows = []
    for s in material:
        bg, fg = SEV_COLOR.get(str(s.get("severity")), SEV_COLOR["medium"])
        plan_rows.append(
            f"<div class='row' data-shift-channel='{esc(s.get('channel'))}' "
            f"data-shift-direction='{esc(s.get('direction'))}' "
            f"data-shift-delta='{esc(s.get('delta'))}' "
            f"data-shift-severity='{esc(s.get('severity'))}'>"
            f"<span class='sev' style='background:{bg};color:{fg}'>{esc(s.get('severity'))}</span>"
            f"<div style='flex:1'><b>{esc(s.get('channel'))}</b> "
            f"<span class='muted'>{esc(s.get('direction'))}</span> {esc(s.get('delta'))} "
            f"<span class='muted'>({esc(s.get('current_budget'))} -> {esc(s.get('proposed_budget'))})</span>"
            f"{_citations(s.get('citations', []))}</div></div>"
        )
    budget = _panel(
        "Budget plan (deterministic, budget-neutral)",
        f"<div data-shift-count='{len(material)}' "
        f"data-plan-total-budget='{esc(plan.get('total_budget'))}'>"
        + ("".join(plan_rows) or "<div class='muted'>no material shifts</div>")
        + "</div>",
        "budget-plan",
    )

    ab_results = data.get("ab_results", [])
    ab_rows = []
    for result in ab_results:
        verdict = VERDICT_LABEL.get(str(result.get("verdict")), str(result.get("verdict")))
        ab_rows.append(
            f"<div class='row' data-ab-test='{esc(result.get('test_id'))}' "
            f"data-ab-verdict='{esc(result.get('verdict'))}' "
            f"data-ab-pvalue='{esc(result.get('p_value'))}' "
            f"data-ab-significant='{str(bool(result.get('significant'))).lower()}'>"
            f"<div style='flex:1'><b>{esc(result.get('test_id'))}</b> "
            f"<span class='muted'>lift "
            f"{esc(round(float(result.get('relative_lift', 0.0)) * 100, 1))}%, "
            f"p={esc(result.get('p_value'))}</span> · {esc(verdict)}"
            f"{_citations(result.get('citations', []))}</div></div>"
        )
    ab = _panel(
        "A/B significance",
        f"<div data-ab-count='{len(ab_results)}'>"
        + ("".join(ab_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "ab-significance",
    )

    anomalies = data.get("anomalies") or {}
    found = anomalies.get("anomalies", [])
    anom_rows = []
    for a in found:
        bg, fg = SEV_COLOR.get(str(a.get("severity")), SEV_COLOR["medium"])
        anom_rows.append(
            f"<div class='row' data-anomaly-metric='{esc(a.get('metric'))}' "
            f"data-anomaly-kind='{esc(a.get('kind'))}' "
            f"data-anomaly-severity='{esc(a.get('severity'))}' "
            f"data-anomaly-value='{esc(a.get('value'))}' "
            f"data-anomaly-baseline='{esc(a.get('baseline'))}'>"
            f"<span class='sev' style='background:{bg};color:{fg}'>{esc(a.get('severity'))}</span>"
            f"<div style='flex:1'><b>{esc(a.get('metric'))}</b> "
            f"<span class='muted'>{esc(a.get('kind'))}: {esc(a.get('value'))} vs baseline "
            f"{esc(a.get('baseline'))} (z {esc(a.get('deviation'))})</span>"
            f"{_citations(a.get('citations', []))}</div></div>"
        )
    anom = _panel(
        "Anomalies",
        f"<div data-anomaly-count='{len(found)}'>"
        + ("".join(anom_rows) or "<div class='muted'>none</div>")
        + "</div>",
        "anomalies",
    )

    body = head + review + summary + efficiency + attribution + budget + ab + anom
    return _page(f"Performance report — {data.get('account_id')}", body)


def render_index(reports: list[tuple[str, dict[str, Any]]]) -> str:
    rows = []
    for fname, data in reports:
        market = MARKET_LABEL.get(str(data.get("market")), str(data.get("market")))
        vertical = VERTICAL_LABEL.get(str(data.get("vertical")), str(data.get("vertical")))
        rows.append(
            f"<a class='choose' href='{esc(fname)}'><b>{esc(data.get('account_id'))}</b> "
            f"<span class='muted'>· {esc(market)} · {esc(vertical)}</span></a>"
        )
    body = (
        "<h1>D4 Performance Marketing — demo reports</h1>"
        "<p class='sub'>Offline, obviously-fictional synthetic data. Local profile, no cloud.</p>"
        + "".join(rows)
    )
    return _page("D4 demo reports", body)


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("scripts/out")
    reports: list[tuple[str, dict[str, Any]]] = []
    for json_path in sorted(out_dir.glob("report-*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        html_name = json_path.stem + ".html"
        (out_dir / html_name).write_text(render_report(data), encoding="utf-8")
        reports.append((html_name, data))
        print(f"wrote {out_dir / html_name}")
    (out_dir / "index.html").write_text(render_index(reports), encoding="utf-8")
    print(f"wrote {out_dir / 'index.html'}  ({len(reports)} report(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
