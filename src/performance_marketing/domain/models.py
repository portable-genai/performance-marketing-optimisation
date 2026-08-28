"""Domain models for the Performance Marketing and Attribution system (D4).

This module is the heart of the hexagon. It has **no dependency on Google Cloud,
ADK, FastAPI, or any framework** (only the Python standard library). Every adapter
(GCP, remote-platform, or on-prem placeholder) speaks in terms of these types, which
is what lets the managed-service stack be swapped for an on-premise one without
touching domain logic (no vendor lock-in, ports and adapters).

D4 is deliberately **generic performance marketing**, not a bank-specific tool:

* ``Vertical`` is a configurable enum (banking, online retail), so the same engines
  reason over a deposit-account acquisition funnel and an e-commerce purchase funnel.
* ``Market`` is a configurable enum (JP, AU, SG) carrying its residency region and
  locales, so JP, AU and SG are first-class config and seed, never hard-coded.

The deterministic engines are the heart of the system: multi-touch attribution,
ROAS / CAC, bid / budget optimisation, A/B significance and anomaly detection, all
pure statistics that an analyst (or auditor) must be able to re-run. The LLM only
narrates the result and drafts spend-shift recommendations; every figure that leaves
the system carries a :class:`Citation` and every consequential aggregate sets
``requires_human_review``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from agent_eval_kit.report import EvalMetricResult as EvalMetricResult
from agent_eval_kit.report import EvalReport as EvalReport
from hex_service_kit import StrEnum
from hex_service_kit.observability import TokenUsage as TokenUsage

from .kernel import ThinkingLevel

# ``TokenUsage``, ``EvalMetricResult`` and ``EvalReport`` are RE-EXPORTED, not declared here.
#
# Sixteen repositories had each hand-copied them, and a value type copied into N repos is N
# types that drift the moment one copy is edited. Re-exporting retires that whole class of
# defect: there is one definition, in the commons, and this module's name for it is the same
# object (``tests/contract/test_port_parity.py`` asserts identity with ``is``, which is the
# only assertion a structural look-alike cannot satisfy).
#
# The commons ``EvalReport`` carries the same fail-closed ``passed`` rule this repo wrote for
# itself (``n_examples > 0 and bool(results) and all(...)``: ``all(())`` is vacuously true and
# is not evidence), plus the durable-evidence fields the promotion gate needs: ``run_id``,
# ``dataset_version``, ``dataset_digest``, ``evaluator``, ``schema_version``, ``trace_id``,
# ``correlation_id``, ``artifact_refs`` and ``attested``. All are defaulted, so every existing
# construction site still compiles.
#
# ``agent_eval_kit.report`` is imported as a SUBMODULE deliberately: the package root pulls in
# ``gate_client``, and with it ``httpx``, which this stdlib-only domain module must not require.


def utcnow() -> datetime:
    """Timezone-aware UTC now (the single clock the domain uses)."""
    return datetime.now(UTC)


# --------------------------------------------------------------------------- #
# Vertical and Market — the two configurable axes (generic, multi-vertical, APAC)
# --------------------------------------------------------------------------- #
class Vertical(StrEnum):
    """The business vertical the performance report is scoped to.

    D4 is generic: banking is ONE vertical and online retail is another. The
    deterministic engines and the LLM prompts switch conversion taxonomy / target
    benchmarks by vertical; no bank-only logic is baked into the domain.
    """

    BANKING = "banking"
    ONLINE_RETAIL = "online_retail"


class Market(StrEnum):
    """A supported market (Japan, Australia, Singapore).

    The residency region, locales and per-market rule sets are config + seed (see
    :data:`MARKET_PROFILES` and ``config/settings.yaml``), never hard-coded into a
    branch. Adding a market is a config + seed change, not a code change.
    """

    JP = "JP"
    AU = "AU"
    SG = "SG"


@dataclass(frozen=True, slots=True)
class MarketProfile:
    """Static, fictional-data-friendly metadata for a market.

    The residency ``region`` is a GCP regional id selectable at deploy and validated;
    ``locales`` drives bilingual (ja + en) output. These defaults can be overridden in
    ``config/settings.yaml`` so the catalog stays config-driven.
    """

    market: Market
    region: str  # GCP residency region, e.g. "asia-northeast1" (Tokyo)
    display_name: str
    locales: tuple[str, ...]  # e.g. ("ja", "en") or ("en",)
    currency: str = ""


# Built-in defaults. Region/locale are config + seed: settings.yaml may override these.
MARKET_PROFILES: dict[Market, MarketProfile] = {
    Market.JP: MarketProfile(
        market=Market.JP,
        region="asia-northeast1",
        display_name="Japan",
        locales=("ja", "en"),
        currency="JPY",
    ),
    Market.AU: MarketProfile(
        market=Market.AU,
        region="australia-southeast1",
        display_name="Australia",
        locales=("en",),
        currency="AUD",
    ),
    Market.SG: MarketProfile(
        market=Market.SG,
        region="asia-southeast1",
        display_name="Singapore",
        locales=("en",),
        currency="SGD",
    ),
}


# --------------------------------------------------------------------------- #
# Provenance / citation
# --------------------------------------------------------------------------- #
class SourceType(StrEnum):
    """Every citation names which kind of evidence it points to."""

    METRICS = "metrics"  # a metrics warehouse row (BigQuery / ad-platform export)
    AD_PLATFORM = "ad_platform"  # a paid-media platform report (spend / clicks / conv)
    TARGET = "target"  # a configured ROAS / CAC target or benchmark
    EXPERIMENT = "experiment"  # an A/B experiment result
    INTERNAL = "internal"  # an internal note / prior performance review
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Citation:
    """Provenance attached to every figure and finding in a performance report.

    An analyst must be able to trace every number (attributed conversions, ROAS, the
    recommended budget shift) back to its exact source: an auditable, replayable
    performance report is the whole point of D4.
    """

    source_id: str
    source_type: SourceType
    title: str
    url: str = ""
    page: int | None = None
    observed_date: str | None = None  # ISO date of the underlying metric, if known
    snippet: str = ""
    score: float | None = None


# --------------------------------------------------------------------------- #
# Generation (LLM) — the LLM only narrates / drafts; never decides the numbers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class WebCitation:
    """Provenance for a public-web grounded fact returned by the model."""

    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True, slots=True)
class LlmMessage:
    role: str  # "user" | "model" | "system"
    content: str


@dataclass(frozen=True, slots=True)
class LlmRequest:
    messages: tuple[LlmMessage, ...]
    system_instruction: str | None = None
    model: str | None = None  # None => adapter default from config
    thinking: ThinkingLevel = ThinkingLevel.MEDIUM
    temperature: float = 0.0  # omitted at a call site means this value; it must not sample
    max_output_tokens: int = 4096
    response_schema: dict | None = None  # JSON schema for structured output


# ``TokenUsage`` was declared here. It is now re-exported from
# ``hex_service_kit.observability`` at the top of this module: the three int fields were
# byte-identical in every repo that had copied it, which is a shared value type that had
# simply never been shared.


@dataclass(frozen=True, slots=True)
class LlmResponse:
    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)
    model: str = ""
    web_citations: tuple[WebCitation, ...] = ()
    raw: dict | None = None


# --------------------------------------------------------------------------- #
# Safety (guardrail) — A1 Guardrail Gateway concern
# --------------------------------------------------------------------------- #
class GuardrailCategory(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    SENSITIVE_DATA = "sensitive_data"
    MALICIOUS_URL = "malicious_url"
    OTHER = "other"


class Direction(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class GuardrailFinding:
    category: GuardrailCategory
    confidence: str  # "low" | "medium" | "high"
    detail: str = ""


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    direction: Direction
    findings: tuple[GuardrailFinding, ...] = ()
    sanitized_text: str | None = None
    reason: str = ""


# --------------------------------------------------------------------------- #
# Audit and observability — A5 Observability, Audit and FinOps concern
# --------------------------------------------------------------------------- #
class Decision(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    ESCALATED = "escalated"  # routed to a human (maker-checker)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """An immutable, WORM-stored record of one performance-marketing-optimisation interaction."""

    action: str  # "performance_report" | "attribution" | "budget_optimisation"
    actor: str  # authenticated analyst / service identity
    decision: Decision
    prompt: str = ""
    response: str = ""
    citations: tuple[Citation, ...] = ()
    resource: str = "performance-marketing-optimisation"
    trace_id: str | None = None
    timestamp: datetime = field(default_factory=utcnow)
    metadata: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Evaluation gate — A4 AI Quality and Model-Risk concern
# --------------------------------------------------------------------------- #
# ``EvalMetricResult`` and ``EvalReport`` were declared here. They are now re-exported from
# ``agent_eval_kit.report`` at the top of this module. The fail-closed ``passed`` rule this
# repo wrote (``n_examples > 0 and bool(results) and all(...)``, because the naive ``all(())``
# is vacuously True and certifies a promotion that scored nothing) is the commons rule too, so
# the move preserves it rather than weakening it; ``tests/unit/test_eval_report_gate.py`` still
# exercises every branch of it against the re-exported type.


# --------------------------------------------------------------------------- #
# Governance — A3 Agent Registry and the MCP tool catalog
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class AgentSkill:
    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentCard:
    """Minimal A2A-style agent card published at /.well-known/agent-card.json."""

    name: str
    description: str
    url: str
    version: str
    skills: tuple[AgentSkill, ...] = ()
    provider: str = "performance-marketing-optimisation"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A governed, least-privilege tool exposed to the agent (typically via MCP)."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Shared severity scale
# --------------------------------------------------------------------------- #
class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# --------------------------------------------------------------------------- #
# Core performance-marketing-optimisation domain objects
# --------------------------------------------------------------------------- #
class Channel(StrEnum):
    """A paid-media channel a touchpoint / campaign belongs to (generic, all verticals)."""

    SEARCH = "search"
    SOCIAL = "social"
    DISPLAY = "display"
    VIDEO = "video"
    AFFILIATE = "affiliate"
    EMAIL = "email"
    OTHER = "other"


class BidStrategyKind(StrEnum):
    """The bidding objective configured on an account / channel."""

    MAXIMISE_CONVERSIONS = "maximise_conversions"
    TARGET_ROAS = "target_roas"
    TARGET_CPA = "target_cpa"
    MANUAL_CPC = "manual_cpc"


@dataclass(frozen=True, slots=True)
class RoasTarget:
    """A configured ROAS / CAC target for an account, market and vertical.

    Targets are config + seed (per market + per vertical), never hard-coded: e.g. a
    banking account targets a CAC ceiling, an online-retail account a ROAS floor. The
    deterministic engines compare measured performance against these.
    """

    market: Market
    vertical: Vertical
    target_roas: float = 0.0  # revenue / spend floor (0 => not set)
    target_cac: float = 0.0  # cost-per-acquisition ceiling (0 => not set)
    currency: str = ""

    @property
    def has_roas(self) -> bool:
        return self.target_roas > 0.0

    @property
    def has_cac(self) -> bool:
        return self.target_cac > 0.0


@dataclass(frozen=True, slots=True)
class BidStrategy:
    """The bidding configuration on a channel within an account."""

    channel: Channel
    kind: BidStrategyKind
    target_value: float = 0.0  # target ROAS / CPA depending on kind (0 => none)
    daily_budget: float = 0.0


@dataclass(frozen=True, slots=True)
class Touchpoint:
    """One observed marketing touchpoint on a conversion journey, with provenance.

    The multi-touch attribution engine consumes ordered touchpoints per journey and
    distributes credit across the channels they belong to.
    """

    channel: Channel
    observed_date: str = ""  # ISO date of the interaction
    position: int = 0  # 0-based order within the journey
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class ConversionJourney:
    """An ordered set of touchpoints culminating (or not) in a conversion."""

    id: str
    touchpoints: tuple[Touchpoint, ...] = ()
    converted: bool = True
    revenue: float = 0.0  # conversion value (revenue) attributed to this journey


@dataclass(frozen=True, slots=True)
class ChannelMetrics:
    """Aggregated spend / clicks / conversions / revenue for one channel.

    The raw input to the ROAS / CAC, bid / budget and anomaly engines. Sourced from the
    metrics warehouse (BigQuery) or an ad-platform export; carries its provenance.
    """

    channel: Channel
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    conversions: float = 0.0
    revenue: float = 0.0
    observed_date: str = ""
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class MetricPoint:
    """One dated scalar observation of a metric (drives anomaly detection)."""

    metric: str  # e.g. "cpa", "ctr", "spend"
    observed_date: str  # ISO date
    value: float
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class AbVariant:
    """One arm of an A/B test (control or a variant), with observed outcomes."""

    name: str
    visitors: int = 0
    conversions: int = 0

    @property
    def rate(self) -> float:
        return self.conversions / self.visitors if self.visitors > 0 else 0.0


@dataclass(frozen=True, slots=True)
class AbTest:
    """An A/B test definition: a control variant and one challenger variant.

    The significance engine computes a two-proportion z-test deterministically; the LLM
    only narrates whether to ship, hold or stop.
    """

    id: str
    metric: str  # the conversion metric under test, e.g. "signup_rate"
    control: AbVariant
    variant: AbVariant
    market: Market | None = None
    vertical: Vertical | None = None
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class Account:
    """A performance-marketing-optimisation account: the unit a report is scoped to.

    Generic across verticals: a banking acquisition account or an online-retail store
    account. Holds the configured bid strategies and the per-account ROAS / CAC target.
    """

    id: str
    name: str
    market: Market
    vertical: Vertical
    bid_strategies: tuple[BidStrategy, ...] = ()
    roas_target: RoasTarget | None = None
    tenant: str = ""  # owning tenant; object-level authz gates this against the principal (C2)


# --------------------------------------------------------------------------- #
# 1. Multi-touch attribution
# --------------------------------------------------------------------------- #
class AttributionModel(StrEnum):
    """The credit-assignment rule used by the deterministic attribution engine."""

    LAST_TOUCH = "last_touch"
    FIRST_TOUCH = "first_touch"
    LINEAR = "linear"
    POSITION_BASED = "position_based"  # 40/20/40 first / middle / last


@dataclass(frozen=True, slots=True)
class ChannelAttribution:
    """Attributed conversions and revenue credited to one channel."""

    channel: Channel
    attributed_conversions: float
    attributed_revenue: float
    credit_share: float  # 0..1 share of total credit
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class AttributionView:
    """The deterministic multi-touch attribution result for a model.

    Distributes conversion + revenue credit across channels using ``model``; an analyst
    can re-run it and get the identical split, so it is code, not an LLM guess.
    """

    model: AttributionModel
    market: Market
    vertical: Vertical
    channels: tuple[ChannelAttribution, ...] = ()
    total_conversions: float = 0.0
    total_revenue: float = 0.0
    journeys_considered: int = 0

    def credit_for(self, channel: Channel) -> float:
        for c in self.channels:
            if c.channel is channel:
                return c.credit_share
        return 0.0


# --------------------------------------------------------------------------- #
# 2. ROAS / CAC efficiency
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ChannelEfficiency:
    """Deterministic ROAS / CAC for one channel, with target comparison."""

    channel: Channel
    spend: float
    revenue: float
    conversions: float
    roas: float  # revenue / spend (0 if no spend)
    cac: float  # spend / conversions (0 if no conversions)
    meets_roas_target: bool = True
    meets_cac_target: bool = True
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class EfficiencyReport:
    """Per-channel ROAS / CAC plus the blended account figures, vs the targets."""

    market: Market
    vertical: Vertical
    channels: tuple[ChannelEfficiency, ...] = ()
    blended_roas: float = 0.0
    blended_cac: float = 0.0
    target: RoasTarget | None = None

    @property
    def underperformers(self) -> tuple[ChannelEfficiency, ...]:
        """Channels missing the ROAS or CAC target (candidates for a budget cut)."""
        return tuple(c for c in self.channels if not (c.meets_roas_target and c.meets_cac_target))


# --------------------------------------------------------------------------- #
# 3. Bid / budget optimisation
# --------------------------------------------------------------------------- #
class ShiftDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class BudgetShift:
    """A proposed, deterministic budget reallocation for one channel.

    The recommended shift is computed by the optimisation engine (efficiency-weighted,
    bounded by a max step), not by the LLM. Nothing auto-executes: a human approves.
    """

    channel: Channel
    direction: ShiftDirection
    current_budget: float
    proposed_budget: float
    delta: float  # proposed - current (signed)
    rationale: str = ""
    severity: Severity = Severity.MEDIUM
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class BudgetPlan:
    """The deterministic budget-reallocation plan across channels (budget-neutral)."""

    market: Market
    vertical: Vertical
    shifts: tuple[BudgetShift, ...] = ()
    total_budget: float = 0.0

    @property
    def material_shifts(self) -> tuple[BudgetShift, ...]:
        return tuple(s for s in self.shifts if s.direction is not ShiftDirection.HOLD)

    @property
    def requires_human_review(self) -> bool:
        """A material reallocation is consequential: a human signs off before it runs."""
        return any(s.severity in (Severity.HIGH, Severity.CRITICAL) for s in self.material_shifts)


# --------------------------------------------------------------------------- #
# 4. A/B significance
# --------------------------------------------------------------------------- #
class AbVerdict(StrEnum):
    SHIP = "ship"  # variant significantly better
    STOP = "stop"  # variant significantly worse
    KEEP_RUNNING = "keep_running"  # not yet significant / underpowered


@dataclass(frozen=True, slots=True)
class AbResult:
    """The deterministic two-proportion significance result for an A/B test."""

    test_id: str
    metric: str
    control_rate: float
    variant_rate: float
    absolute_lift: float  # variant_rate - control_rate
    relative_lift: float  # absolute_lift / control_rate (0 if control_rate == 0)
    z_score: float
    p_value: float
    significant: bool
    verdict: AbVerdict
    rationale: str = ""
    citations: tuple[Citation, ...] = ()


# --------------------------------------------------------------------------- #
# 5. Anomaly detection
# --------------------------------------------------------------------------- #
class AnomalyKind(StrEnum):
    SPIKE = "spike"
    DROP = "drop"


@dataclass(frozen=True, slots=True)
class Anomaly:
    """A deterministic robust-z anomaly on a metric series, with provenance."""

    metric: str
    observed_date: str
    value: float
    baseline: float  # the robust centre (median) of the comparison window
    deviation: float  # robust z-score (signed)
    kind: AnomalyKind
    severity: Severity = Severity.MEDIUM
    rationale: str = ""
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    """The set of detected anomalies across the monitored metrics."""

    market: Market
    vertical: Vertical
    anomalies: tuple[Anomaly, ...] = ()

    @property
    def material(self) -> tuple[Anomaly, ...]:
        return tuple(a for a in self.anomalies if a.severity in (Severity.HIGH, Severity.CRITICAL))


# --------------------------------------------------------------------------- #
# The aggregates (top-level artifacts) — always require human review
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class ReportRequest:
    """The inbound request for a performance report."""

    account_id: str
    market: Market
    vertical: Vertical
    attribution_model: AttributionModel = AttributionModel.POSITION_BASED
    lookback_days: int = 30


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    """A single cited performance report bundling every artifact for an account.

    The top-level consequential output of D4. It bundles the attribution view, the
    efficiency (ROAS / CAC) report, the recommended budget plan, the A/B results and the
    anomaly report. It is acted on (spend is moved), so it **always** requires human
    review (maker-checker): a maker (the agent) proposes and a checker (a qualified
    performance lead) disposes before any budget shift is executed.
    """

    id: str
    account_id: str
    market: Market
    vertical: Vertical
    summary: str
    attribution: AttributionView | None = None
    efficiency: EfficiencyReport | None = None
    budget_plan: BudgetPlan | None = None
    ab_results: tuple[AbResult, ...] = ()
    anomalies: AnomalyReport | None = None
    citations: tuple[Citation, ...] = ()
    requires_human_review: bool = True
    generated_at: datetime = field(default_factory=utcnow)
