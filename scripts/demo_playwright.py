"""Presenter-controlled Playwright walkthrough of the live D4 performance-marketing-optimisation demo.

Drives a headed browser through the four-account flow served by ``scripts/demo_server.py``.
It is **paced by the presenter**: before each step it prints what is about to happen and
waits for you to press Enter, then performs the action (click "Next") and highlights the
panel to look at. You stay in control.

Usage (two terminals)::

    # terminal 1 - the live demo server
    make demo-server                                    # or: MKT_PERF_PROFILE=local \\
                                                          #   PYTHONPATH=src .venv/bin/python \\
                                                          #   scripts/demo_server.py

    # terminal 2 - the guided walkthrough (a real Chrome window opens)
    .venv/bin/pip install playwright && .venv/bin/playwright install chromium  # one-time
    .venv/bin/python scripts/demo_playwright.py

Point it at the real Next.js console instead with ``DEMO_URL=http://localhost:3000`` (then
it just opens the console for the presenter; the Next/Restart buttons are specific to the
demo server, so against the live console use it as a guided narration overlay).

Environment overrides:
    DEMO_URL    server base URL (default http://127.0.0.1:8113)
    HEADLESS=1  run headless (used for the self-test; no window)
    DEMO_AUTO=1 don't wait for Enter - advance automatically (self-test / recording)
    SLOWMO_MS   per-action slow-motion in ms (default 250 headed, 0 headless)
    CHROME_PATH explicit Chromium/Chrome binary (else Playwright's own)
"""

from __future__ import annotations

import contextlib
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("DEMO_URL", "http://127.0.0.1:8113")
HEADLESS = os.environ.get("HEADLESS") == "1"
AUTO = os.environ.get("DEMO_AUTO") == "1"
SLOWMO = int(os.environ.get("SLOWMO_MS", "0" if HEADLESS else "250"))
CHROME_PATH = os.environ.get("CHROME_PATH") or None

# (narration shown in the terminal, whether this step clicks "Next", panel to spotlight)
STEPS = [
    (
        "The console opens on a Singapore banking account at a blended ROAS of 2.62. The "
        "budget-shift panel is a deterministic optimiser, not the model: it proposes moving "
        "spend into search and out of social and display, each shift severity-ranked, and a "
        "critical CPA-spike anomaly is flagged alongside it.",
        False,
        ".review",
    ),
    (
        "Next is a Japan banking account: the same maths, a very different market, CAC "
        "over 17x the Singapore account at 552.63. The A/B significance panel shows one "
        "experiment shipping (p=0.0002) and one still running (p=0.62): the model narrates "
        "the verdict, the p-value decides it.",
        True,
        ".sev",
    ),
    (
        "A Japan online-retail account has the strongest efficiency of the four, ROAS 6.00. "
        "The attribution panel breaks the blended number down per channel with a "
        "multi-touch model, each bar its share of attributed conversions.",
        True,
        ".bar",
    ),
    (
        "An Australia online-retail account closes the walkthrough with its own critical "
        "CPA-spike anomaly, the same statistical test as Singapore's, on a different "
        "account. Every figure across all four reports traces back to a citation.",
        True,
        ".cites",
    ),
]


def _pause(prompt: str) -> None:
    if AUTO:
        time.sleep(1.2)
        return
    try:
        input(prompt)
    except EOFError:  # non-interactive stdin
        time.sleep(1.0)


def _spotlight(page, selector: str | None) -> None:
    if not selector:
        return
    with contextlib.suppress(Exception):  # cosmetic only
        page.eval_on_selector_all(
            selector,
            "els => els.forEach((e,i)=>{ if(i<6){ e.style.transition='box-shadow .3s';"
            " e.style.boxShadow='0 0 0 3px #3a60f0'; setTimeout(()=>e.style.boxShadow='',1600);} })",
        )


def _reachable() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(BASE + "/", timeout=2):
            return True
    except (urllib.error.URLError, OSError):
        return False


def main() -> int:
    if not _reachable():
        print(f"Cannot reach the demo server at {BASE}.")
        print("Start it first:  make demo-server")
        return 2

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOWMO, executable_path=CHROME_PATH)
        page = browser.new_context(viewport={"width": 1100, "height": 900}).new_page()

        print(
            "\n=== D4 performance-marketing-optimisation live demo - press Enter to advance each step ===\n"
        )
        page.goto(BASE + "/restart", wait_until="load")  # always start clean
        page.goto(BASE + "/", wait_until="load")

        for i, (say, click, spotlight) in enumerate(STEPS):
            print(f"[{i + 1}/{len(STEPS)}] {say}")
            _pause("        press Enter to run this step... ")
            if click:
                btn = page.locator(".democtl button.next")
                if btn.count() and btn.is_enabled():
                    btn.click()
                    page.wait_for_load_state("load")
            page.wait_for_timeout(200)
            _spotlight(page, spotlight)
            page.wait_for_timeout(700)
            print()

        print("Demo complete. The browser stays open for questions.")
        _pause("        press Enter to close the browser... ")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
