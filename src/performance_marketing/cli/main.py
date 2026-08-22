"""``mkt-perf`` — the Typer CLI for the D4 Performance Marketing system.

A thin presentation layer over the domain services. It owns no business logic: every
command builds the wiring from :func:`performance_marketing.api.deps.make_report_service`,
invokes one domain service, and pretty-prints the cited result.

Design constraints honoured here:

* **Import-safe.** Importing this module (the ``[project.scripts]`` entry point, or
  ``--help``) must never pull in FastAPI, uvicorn or the Google Cloud SDKs. They are
  imported lazily inside command bodies, so the on-prem / local / test profile (which
  installs no Google Cloud SDK) can still load the CLI.
* **Profile-aware.** ``MKT_PERF_PROFILE`` selects the adapter stack. The ``onprem`` profile
  binds placeholder adapters that raise ``NotImplementedError``; the CLI then fails clearly
  (exit code 2) naming the migration target.
* **Citations are first-class.** Every artifact prints with source-and-page provenance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import Citation, PerformanceReport

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help=(
        "D4 Performance Marketing and Attribution — cited performance reports (multi-touch "
        "attribution, ROAS / CAC, budget plan, A/B significance, anomalies), generic across "
        "banking and online retail and the JP/AU/SG markets."
    ),
)

_PROFILE_EXIT = 2
_RUNTIME_EXIT = 1
_CLI_ACTOR = "cli:operator"
_CLI_TENANT = "demo-bank"  # the CLI operates within the demo tenant (object-level authz, C2)


def _fail(message: str, *, code: int = _RUNTIME_EXIT) -> Any:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _run(action: str, fn: Any) -> Any:
    """Execute ``fn`` and translate adapter failures into clean CLI errors."""
    from ..config import Settings

    profile = Settings.load().profile
    try:
        return fn()
    except NotImplementedError as exc:
        detail = str(exc) or "method not implemented"
        _fail(
            f"'{action}' is not available under profile '{profile}'. "
            f"This profile uses placeholder adapters (migration target): {detail}",
            code=_PROFILE_EXIT,
        )
    except KeyError as exc:
        _fail(f"'{action}' has no adapter wired for profile '{profile}': {exc}", code=_PROFILE_EXIT)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI boundary: no tracebacks to operators
        _fail(f"'{action}' failed: {type(exc).__name__}: {exc}", code=_RUNTIME_EXIT)


# --------------------------------------------------------------------------- #
# Pretty-printing
# --------------------------------------------------------------------------- #
def _fmt_citation(c: Citation) -> str:
    page = f" p.{c.page}" if c.page is not None else ""
    st = c.source_type.value if hasattr(c.source_type, "value") else str(c.source_type)
    url = f" — {c.url}" if c.url else ""
    return f"[{c.source_id}, {st}{page}]{url}"


def _echo_citations(citations: tuple[Citation, ...], indent: str = "  ") -> None:
    if not citations:
        typer.secho(f"{indent}(no citations)", fg=typer.colors.YELLOW)
        return
    typer.secho(f"{indent}Citations:", bold=True)
    for c in citations:
        typer.echo(f"{indent}  - {_fmt_citation(c)}")


def _echo_review_banner(requires_review: bool) -> None:
    if requires_review:
        typer.secho(
            "  [HUMAN REVIEW REQUIRED] maker-checker gate — do not move any budget until a "
            "qualified performance lead signs off.",
            fg=typer.colors.YELLOW,
            bold=True,
        )


def _echo_report(report: PerformanceReport) -> None:
    typer.secho(f"\nPERFORMANCE REPORT: {report.account_id}", bold=True)
    typer.echo(f"  id        : {report.id}")
    typer.echo(f"  market    : {report.market.value}")
    typer.echo(f"  vertical  : {report.vertical.value}")
    _echo_review_banner(report.requires_human_review)

    typer.secho("\n  Summary:", bold=True)
    typer.echo(f"    {report.summary}")

    eff = report.efficiency
    if eff is not None:
        typer.secho("\n  Channel efficiency (ROAS / CAC):", bold=True)
        typer.echo(f"    blended ROAS {eff.blended_roas:.2f}, blended CAC {eff.blended_cac:.2f}")
        for c in eff.channels:
            flag = "" if (c.meets_roas_target and c.meets_cac_target) else "  [MISSES TARGET]"
            typer.echo(
                f"    - {c.channel.value}: spend {c.spend:.2f}, ROAS {c.roas:.2f}, "
                f"CAC {c.cac:.2f}{flag}"
            )

    attr = report.attribution
    if attr is not None:
        typer.secho(f"\n  Attribution ({attr.model.value}):", bold=True)
        for ac in attr.channels:
            typer.echo(
                f"    - {ac.channel.value}: {ac.credit_share * 100:.1f}% credit "
                f"({ac.attributed_conversions:.2f} conv, {ac.attributed_revenue:.2f} rev)"
            )

    plan = report.budget_plan
    if plan is not None:
        typer.secho("\n  Budget plan (deterministic, budget-neutral):", bold=True)
        for s in plan.material_shifts:
            typer.echo(
                f"    - [{s.severity.value}] {s.channel.value}: {s.direction.value} "
                f"{s.delta:+.2f} ({s.current_budget:.2f} -> {s.proposed_budget:.2f})"
            )
        if not plan.material_shifts:
            typer.echo("    (no material shifts)")

    if report.ab_results:
        typer.secho("\n  A/B significance:", bold=True)
        for r in report.ab_results:
            typer.echo(
                f"    - {r.test_id}: {r.verdict.value} "
                f"(lift {r.relative_lift * 100:+.1f}%, p={r.p_value:.4f})"
            )

    anomalies = report.anomalies
    if anomalies is not None and anomalies.anomalies:
        typer.secho("\n  Anomalies:", bold=True)
        for a in anomalies.anomalies:
            typer.echo(
                f"    - [{a.severity.value}] {a.metric} {a.kind.value}: {a.value:.2f} "
                f"vs baseline {a.baseline:.2f} (z {a.deviation:.2f})"
            )

    typer.secho("", nl=True)
    _echo_citations(report.citations)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@app.command()
def report(
    account_id: str = typer.Argument(..., help="The account id, e.g. 'acct-sg-banking'."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
    model: str = typer.Option(
        "position_based",
        "--model",
        help="Attribution: last_touch | first_touch | linear | position_based.",
    ),
    lookback: int = typer.Option(30, "--lookback", help="Lookback window in days."),
) -> None:
    """Build a cited performance report for an account in a market and vertical."""
    from ..api.deps import make_report_service
    from ..domain.models import AttributionModel, Market, ReportRequest, Vertical

    def go() -> PerformanceReport:
        request = ReportRequest(
            account_id=account_id,
            market=Market(market),
            vertical=Vertical(vertical),
            attribution_model=AttributionModel(model),
            lookback_days=lookback,
        )
        return make_report_service().build_report(request, actor=_CLI_ACTOR, tenant=_CLI_TENANT)

    result = _run("report", go)
    _echo_report(result)


@app.command("budget-plan")
def budget_plan(
    account_id: str = typer.Argument(..., help="The account id to optimise."),
    market: str = typer.Option("SG", "--market", "-m", help="Market: JP | AU | SG."),
    vertical: str = typer.Option(
        "banking", "--vertical", "-v", help="Vertical: banking | online_retail."
    ),
) -> None:
    """Show only the deterministic budget-reallocation plan for an account."""
    from ..api.deps import make_report_service
    from ..domain.models import Market, ReportRequest, Vertical

    def go() -> Any:
        request = ReportRequest(
            account_id=account_id, market=Market(market), vertical=Vertical(vertical)
        )
        return make_report_service().build_report(request, actor=_CLI_ACTOR, tenant=_CLI_TENANT)

    result = _run("budget-plan", go)
    typer.secho(
        f"\nBUDGET PLAN: {result.account_id} [{result.market.value}/{result.vertical.value}]",
        bold=True,
    )
    _echo_review_banner(result.requires_human_review)
    plan = result.budget_plan
    if plan is not None:
        for s in plan.shifts:
            typer.echo(
                f"  - [{s.severity.value}] {s.channel.value}: {s.direction.value} "
                f"{s.delta:+.2f} — {s.rationale}"
            )
        _echo_citations(tuple(c for s in plan.shifts for c in s.citations))


if __name__ == "__main__":  # pragma: no cover
    app()
