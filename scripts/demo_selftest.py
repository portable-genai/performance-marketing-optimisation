#!/usr/bin/env python3
"""Credential-free anti-rot check for the real D4 presenter demo.

Two stages, both executed, neither asserting against hard-coded prose:

1. **In-process** -- the real :class:`DemoSession` builds all four live performance
   reports and renders / advances / resets every presenter step.
2. **Served** -- the real ``ThreadingHTTPServer`` from ``scripts/demo_server.py`` is
   started on an ephemeral port and the whole presenter journey is driven over HTTP with
   ``POST /advance``. Every figure asserted at this stage is read back out of the SERVED
   bytes through the stable ``data-*`` evidence hooks and compared with what the RUNNING
   app computed, so a renderer that stops emitting a figure, a server that stops
   advancing, or a hook that gets renamed all fail here. A check that never served a byte
   cannot see whether serving works.

Both stages are credential-free and pure standard library, so they run in the same offline
gate as everything else. ``tests/unit/test_report_ui_citations.py`` pins the same evidence
rule hermetically, against a synthetic report rather than the live demo.
"""

from __future__ import annotations

import re
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from typing import Any

from demo_server import DemoSession, Handler


def _hook(html: str, attribute: str) -> str:
    """Read one stable ``data-*`` evidence hook out of served markup."""
    match = re.search(rf"{attribute}='([^']*)'", html) or re.search(rf'{attribute}="([^"]*)"', html)
    assert match, f"evidence hook {attribute} is missing from the served page"
    return match.group(1)


def _hooks(html: str, attribute: str) -> list[str]:
    """Read every occurrence of a stable ``data-*`` evidence hook, in document order."""
    return re.findall(rf"{attribute}='([^']*)'", html) or re.findall(
        rf'{attribute}="([^"]*)"', html
    )


def _assert_live_figures(page: str, report: dict[str, Any]) -> None:
    """Every asserted figure comes from the running app, never from a literal."""
    assert _hook(page, "data-report") == report["id"]
    assert _hook(page, "data-report-account") == report["account_id"]
    assert _hook(page, "data-report-market") == report["market"]
    assert _hook(page, "data-report-vertical") == report["vertical"]
    assert _hook(page, "data-report-citations") == str(len(report["citations"]))
    assert _hook(page, "data-report-review") == str(bool(report["requires_human_review"])).lower()
    assert _hook(page, "data-review-gate") == "required"

    panels = _hooks(page, "data-panel")
    for required in (
        "summary",
        "channel-efficiency",
        "attribution",
        "budget-plan",
        "ab-significance",
        "anomalies",
    ):
        assert required in panels, f"served page lost the {required} panel hook"

    # Computed performance figures: ROAS / CAC / spend, per channel and blended.
    efficiency = report["efficiency"]
    channels = efficiency["channels"]
    assert _hook(page, "data-blended-roas") == str(efficiency["blended_roas"])
    assert _hook(page, "data-blended-cac") == str(efficiency["blended_cac"])
    assert _hook(page, "data-channel-count") == str(len(channels))
    assert _hooks(page, "data-channel") == [c["channel"] for c in channels]
    assert _hooks(page, "data-channel-spend") == [str(c["spend"]) for c in channels]
    assert _hooks(page, "data-channel-roas") == [str(c["roas"]) for c in channels]
    assert _hooks(page, "data-channel-cac") == [str(c["cac"]) for c in channels]
    assert _hooks(page, "data-channel-meets-target") == [
        str(bool(c["meets_roas_target"] and c["meets_cac_target"])).lower() for c in channels
    ]

    # Multi-touch attribution split.
    attribution = report["attribution"]
    assert _hook(page, "data-attribution-model") == attribution["model"]
    assert _hook(page, "data-attr-channel-count") == str(len(attribution["channels"]))
    assert _hook(page, "data-attr-total-conversions") == str(attribution["total_conversions"])
    assert _hooks(page, "data-attr-channel") == [c["channel"] for c in attribution["channels"]]
    assert _hooks(page, "data-attr-credit-pct") == [
        str(int(round(float(c["credit_share"]) * 100))) for c in attribution["channels"]
    ]

    # The deterministic budget plan: only material (non-hold) shifts are shown.
    plan = report["budget_plan"]
    material = [s for s in plan["shifts"] if s["direction"] != "hold"]
    assert _hook(page, "data-shift-count") == str(len(material))
    assert _hook(page, "data-plan-total-budget") == str(plan["total_budget"])
    assert _hooks(page, "data-shift-channel") == [s["channel"] for s in material]
    assert _hooks(page, "data-shift-delta") == [str(s["delta"]) for s in material]
    assert _hooks(page, "data-shift-severity") == [s["severity"] for s in material]

    # A/B significance: the p-value decides the verdict, so both must survive serving.
    ab_results = report["ab_results"]
    assert _hook(page, "data-ab-count") == str(len(ab_results))
    assert _hooks(page, "data-ab-test") == [a["test_id"] for a in ab_results]
    assert _hooks(page, "data-ab-pvalue") == [str(a["p_value"]) for a in ab_results]
    assert _hooks(page, "data-ab-verdict") == [a["verdict"] for a in ab_results]

    # Anomalies.
    found = report["anomalies"]["anomalies"]
    assert _hook(page, "data-anomaly-count") == str(len(found))
    assert _hooks(page, "data-anomaly-metric") == [a["metric"] for a in found]
    assert _hooks(page, "data-anomaly-severity") == [a["severity"] for a in found]
    assert _hooks(page, "data-anomaly-value") == [str(a["value"]) for a in found]


def check_in_process() -> None:
    """Stage 1: the real session builds, renders, advances and resets."""
    session = DemoSession()
    assert len(session.reports) == 4
    for step, report in enumerate(session.reports, 1):
        assert report["requires_human_review"] is True
        assert report["citations"]
        page = session.render()
        assert f"Step {step}/{len(session.reports)}" in page
        assert "HUMAN REVIEW REQUIRED" in page
        _assert_live_figures(page, report)
        if step < len(session.reports):
            session.advance()
    assert session.at_end
    session.reset()
    assert session.idx == 0
    print("PASS demo self-test: 4/4 live performance reports rendered, advanced, and reset")


def check_served() -> None:
    """Stage 2: drive the REAL server over HTTP and assert figures from served bytes."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.session = DemoSession()  # type: ignore[attr-defined]
    server.lock = threading.Lock()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    reports = server.session.reports  # type: ignore[attr-defined]

    try:
        for index in range(len(reports)):
            with urllib.request.urlopen(f"{base}/", timeout=30) as response:  # noqa: S310
                assert response.status == 200
                page = response.read().decode("utf-8")

            # The served page is at the step the served app believes it is at.
            assert _hook(page, "data-step") == str(index), f"served step marker is not {index}"
            assert _hook(page, "data-step-count") == str(len(reports))
            assert _hook(page, "data-step-report") == reports[index]["id"]
            assert "HUMAN REVIEW REQUIRED" in page

            _assert_live_figures(page, reports[index])

            # Live citations: every citation the running app produced is on the audit page.
            served_ids = set(_hooks(page, "data-citation"))
            assert served_ids, "the served audit view shows no citations at all"
            for citation in reports[index]["citations"]:
                assert citation["source_id"] in served_ids, (
                    f"live citation {citation['source_id']} never reached the served page"
                )

            if index < len(reports) - 1:
                request = urllib.request.Request(f"{base}/advance", method="POST", data=b"")
                with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                    assert response.status in (200, 303)
            else:
                assert "Demo complete" in page

        # Restart must genuinely rewind the SERVED journey, not just the in-process one.
        with urllib.request.urlopen(f"{base}/restart", timeout=30) as response:  # noqa: S310
            rewound = response.read().decode("utf-8")
        assert response.status == 200
        assert _hook(rewound, "data-step") == "0"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print(
        "PASS served: every presenter step, panel hook, computed performance figure and "
        "live citation read back over HTTP from the running demo server"
    )


def main() -> int:
    check_in_process()
    check_served()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
