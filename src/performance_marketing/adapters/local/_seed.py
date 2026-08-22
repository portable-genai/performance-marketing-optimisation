"""Built-in, OBVIOUSLY-FICTIONAL synthetic seed for the ``local`` profile.

This is the offline metrics warehouse that makes a local run grounded out of the box:
per-channel spend / conversions / revenue, conversion journeys, dated metric series, the
account / bid-strategy state with per-account ROAS / CAC targets, and A/B experiments,
spanning BOTH verticals (banking AND online retail) across ALL THREE markets (JP, AU, SG).
Every account / brand name is invented (suffixed FICTIONAL) and every URL points at
``example.test``; nothing here is real data.

The data is keyed by (market, vertical) so the local MetricsPort and AdPlatformPort serve
vertical- and market-specific data, proving D4 is generic and APAC without any hard-coded
branch in the engines.
"""

from __future__ import annotations

from ...domain.models import (
    AbTest,
    AbVariant,
    Account,
    AttributionModel,
    BidStrategy,
    BidStrategyKind,
    Channel,
    ChannelMetrics,
    Citation,
    ConversionJourney,
    Market,
    MetricPoint,
    RoasTarget,
    SourceType,
    Touchpoint,
    Vertical,
)

_Key = tuple[Market, Vertical]


def _cit(
    sid: str, title: str, page: int, date: str, st: SourceType = SourceType.METRICS
) -> Citation:
    return Citation(
        source_id=sid,
        source_type=st,
        title=title,
        url=f"https://metrics.example.test/{sid}",
        page=page,
        observed_date=date,
        snippet=f"{title} (FICTIONAL synthetic metric).",
        score=0.9,
    )


# --------------------------------------------------------------------------- #
# Per-channel metrics, per (market, vertical). Spend / clicks / conv / revenue.
# The numbers are crafted so each (market, vertical) has at least one channel that
# misses its target (a donor) and at least one efficient channel (a receiver).
# --------------------------------------------------------------------------- #
CHANNEL_METRICS: dict[_Key, tuple[ChannelMetrics, ...]] = {
    (Market.SG, Vertical.BANKING): (
        ChannelMetrics(
            channel=Channel.SEARCH,
            spend=10000.0,
            impressions=500000,
            clicks=20000,
            conversions=500.0,
            revenue=45000.0,
            observed_date="2026-06-20",
            citation=_cit("sg-bank-search", "SG banking search metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.SOCIAL,
            spend=8000.0,
            impressions=900000,
            clicks=15000,
            conversions=120.0,
            revenue=7200.0,
            observed_date="2026-06-20",
            citation=_cit("sg-bank-social", "SG banking social metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.DISPLAY,
            spend=4000.0,
            impressions=1200000,
            clicks=6000,
            conversions=60.0,
            revenue=5400.0,
            observed_date="2026-06-20",
            citation=_cit("sg-bank-display", "SG banking display metrics", 1, "2026-06-20"),
        ),
    ),
    (Market.JP, Vertical.BANKING): (
        ChannelMetrics(
            channel=Channel.SEARCH,
            spend=1200000.0,
            impressions=4000000,
            clicks=160000,
            conversions=3200.0,
            revenue=5400000.0,
            observed_date="2026-06-20",
            citation=_cit("jp-bank-search", "JP banking search metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.VIDEO,
            spend=900000.0,
            impressions=8000000,
            clicks=90000,
            conversions=600.0,
            revenue=720000.0,
            observed_date="2026-06-20",
            citation=_cit("jp-bank-video", "JP banking video metrics", 1, "2026-06-20"),
        ),
    ),
    (Market.AU, Vertical.BANKING): (
        ChannelMetrics(
            channel=Channel.SEARCH,
            spend=15000.0,
            impressions=600000,
            clicks=24000,
            conversions=480.0,
            revenue=62400.0,
            observed_date="2026-06-20",
            citation=_cit("au-bank-search", "AU banking search metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.AFFILIATE,
            spend=6000.0,
            impressions=200000,
            clicks=5000,
            conversions=40.0,
            revenue=3200.0,
            observed_date="2026-06-20",
            citation=_cit("au-bank-affiliate", "AU banking affiliate metrics", 1, "2026-06-20"),
        ),
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): (
        ChannelMetrics(
            channel=Channel.SEARCH,
            spend=20000.0,
            impressions=800000,
            clicks=40000,
            conversions=2000.0,
            revenue=120000.0,
            observed_date="2026-06-20",
            citation=_cit("sg-retail-search", "SG retail search metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.SOCIAL,
            spend=18000.0,
            impressions=2000000,
            clicks=50000,
            conversions=900.0,
            revenue=45000.0,
            observed_date="2026-06-20",
            citation=_cit("sg-retail-social", "SG retail social metrics", 1, "2026-06-20"),
        ),
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): (
        ChannelMetrics(
            channel=Channel.SOCIAL,
            spend=3000000.0,
            impressions=20000000,
            clicks=400000,
            conversions=18000.0,
            revenue=27000000.0,
            observed_date="2026-06-20",
            citation=_cit("jp-retail-social", "JP retail social metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.DISPLAY,
            spend=2000000.0,
            impressions=30000000,
            clicks=180000,
            conversions=2000.0,
            revenue=3000000.0,
            observed_date="2026-06-20",
            citation=_cit("jp-retail-display", "JP retail display metrics", 1, "2026-06-20"),
        ),
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): (
        ChannelMetrics(
            channel=Channel.SEARCH,
            spend=25000.0,
            impressions=900000,
            clicks=45000,
            conversions=2500.0,
            revenue=175000.0,
            observed_date="2026-06-20",
            citation=_cit("au-retail-search", "AU retail search metrics", 1, "2026-06-20"),
        ),
        ChannelMetrics(
            channel=Channel.AFFILIATE,
            spend=12000.0,
            impressions=300000,
            clicks=9000,
            conversions=300.0,
            revenue=21000.0,
            observed_date="2026-06-20",
            citation=_cit("au-retail-affiliate", "AU retail affiliate metrics", 1, "2026-06-20"),
        ),
    ),
}


# --------------------------------------------------------------------------- #
# Conversion journeys, per (market, vertical) — for multi-touch attribution.
# Each journey is an ordered list of channel touchpoints ending in a conversion.
# --------------------------------------------------------------------------- #
def _tp(channel: Channel, date: str, pos: int, sid: str) -> Touchpoint:
    return Touchpoint(
        channel=channel,
        observed_date=date,
        position=pos,
        citation=_cit(sid, f"journey touchpoint {channel.value}", 1, date),
    )


def _journeys_for(key: _Key) -> tuple[ConversionJourney, ...]:
    market, vertical = key
    tag = f"{market.value.lower()}-{vertical.value}"
    channels = [m.channel for m in CHANNEL_METRICS.get(key, ())]
    if len(channels) < 2:
        channels = channels + [Channel.SEARCH]
    a, b = channels[0], channels[1]
    return (
        ConversionJourney(
            id=f"{tag}-j1",
            touchpoints=(
                _tp(a, "2026-06-10", 0, f"{tag}-j1-t0"),
                _tp(b, "2026-06-15", 1, f"{tag}-j1-t1"),
                _tp(a, "2026-06-20", 2, f"{tag}-j1-t2"),
            ),
            converted=True,
            revenue=1200.0,
        ),
        ConversionJourney(
            id=f"{tag}-j2",
            touchpoints=(
                _tp(b, "2026-06-12", 0, f"{tag}-j2-t0"),
                _tp(a, "2026-06-18", 1, f"{tag}-j2-t1"),
            ),
            converted=True,
            revenue=800.0,
        ),
        ConversionJourney(
            id=f"{tag}-j3",
            touchpoints=(_tp(a, "2026-06-19", 0, f"{tag}-j3-t0"),),
            converted=True,
            revenue=600.0,
        ),
    )


CONVERSION_JOURNEYS: dict[_Key, tuple[ConversionJourney, ...]] = {
    key: _journeys_for(key) for key in CHANNEL_METRICS
}


# --------------------------------------------------------------------------- #
# Metric series, per (market, vertical) — for anomaly detection. A flat CPA
# baseline with a deliberate spike at the latest point for some segments.
# --------------------------------------------------------------------------- #
def _series_for(key: _Key, *, spike: bool) -> tuple[MetricPoint, ...]:
    market, vertical = key
    tag = f"{market.value.lower()}-{vertical.value}"
    baseline = [20.0, 21.0, 19.0, 20.5, 20.0, 21.5, 19.5]
    last = 60.0 if spike else 20.0  # a clear spike vs a ~20 baseline
    values = baseline + [last]
    dates = [
        "2026-06-13",
        "2026-06-14",
        "2026-06-15",
        "2026-06-16",
        "2026-06-17",
        "2026-06-18",
        "2026-06-19",
        "2026-06-20",
    ]
    return tuple(
        MetricPoint(
            metric="cpa",
            observed_date=d,
            value=v,
            citation=_cit(f"{tag}-cpa-{d}", f"{tag} CPA on {d}", 1, d),
        )
        for d, v in zip(dates, values, strict=True)
    )


# Spike the banking-SG and retail-AU series so the anomaly engine has something to flag.
METRIC_SERIES: dict[_Key, tuple[MetricPoint, ...]] = {
    key: _series_for(
        key, spike=(key in ((Market.SG, Vertical.BANKING), (Market.AU, Vertical.ONLINE_RETAIL)))
    )
    for key in CHANNEL_METRICS
}


# --------------------------------------------------------------------------- #
# Per-account ROAS / CAC targets (config + seed, per market + per vertical).
# Banking accounts use a CAC ceiling; retail accounts use a ROAS floor.
# --------------------------------------------------------------------------- #
ROAS_TARGETS: dict[_Key, RoasTarget] = {
    (Market.SG, Vertical.BANKING): RoasTarget(
        market=Market.SG, vertical=Vertical.BANKING, target_cac=30.0, currency="SGD"
    ),
    (Market.JP, Vertical.BANKING): RoasTarget(
        market=Market.JP, vertical=Vertical.BANKING, target_cac=600.0, currency="JPY"
    ),
    (Market.AU, Vertical.BANKING): RoasTarget(
        market=Market.AU, vertical=Vertical.BANKING, target_cac=40.0, currency="AUD"
    ),
    (Market.SG, Vertical.ONLINE_RETAIL): RoasTarget(
        market=Market.SG, vertical=Vertical.ONLINE_RETAIL, target_roas=4.0, currency="SGD"
    ),
    (Market.JP, Vertical.ONLINE_RETAIL): RoasTarget(
        market=Market.JP, vertical=Vertical.ONLINE_RETAIL, target_roas=5.0, currency="JPY"
    ),
    (Market.AU, Vertical.ONLINE_RETAIL): RoasTarget(
        market=Market.AU, vertical=Vertical.ONLINE_RETAIL, target_roas=4.0, currency="AUD"
    ),
}


_DEFAULT_BUDGET: dict[Channel, float] = {
    Channel.SEARCH: 12000.0,
    Channel.SOCIAL: 9000.0,
    Channel.DISPLAY: 5000.0,
    Channel.VIDEO: 9000.0,
    Channel.AFFILIATE: 6000.0,
    Channel.EMAIL: 2000.0,
    Channel.OTHER: 1000.0,
}

_KIND_FOR_VERTICAL = {
    Vertical.BANKING: BidStrategyKind.TARGET_CPA,
    Vertical.ONLINE_RETAIL: BidStrategyKind.TARGET_ROAS,
}


def _account_for(key: _Key) -> Account:
    market, vertical = key
    target = ROAS_TARGETS.get(key)
    kind = _KIND_FOR_VERTICAL[vertical]
    target_value = (
        (target.target_cac if vertical is Vertical.BANKING else target.target_roas)
        if target
        else 0.0
    )
    strategies = tuple(
        BidStrategy(
            channel=m.channel,
            kind=kind,
            target_value=target_value,
            daily_budget=_DEFAULT_BUDGET.get(m.channel, 1000.0),
        )
        for m in CHANNEL_METRICS.get(key, ())
    )
    name_market = market.value
    name_vertical = "Bank" if vertical is Vertical.BANKING else "Store"
    return Account(
        id=f"acct-{market.value.lower()}-{vertical.value}",
        name=f"Acme {name_vertical} {name_market} (FICTIONAL)",
        market=market,
        vertical=vertical,
        bid_strategies=strategies,
        roas_target=target,
        tenant="demo-bank",
    )


ACCOUNTS: dict[str, Account] = {_account_for(key).id: _account_for(key) for key in CHANNEL_METRICS}
ACCOUNTS_BY_KEY: dict[_Key, Account] = {key: _account_for(key) for key in CHANNEL_METRICS}

# A second-tenant account, so the object-level-authz gate (C2) is demoable and testable: a
# demo-bank principal requesting this id is denied before any report is built. Obviously
# fictional; it carries no metrics (the tenant gate fires before metrics are fetched).
_OTHER_TENANT_ACCOUNT = Account(
    id="acct-other-bank",
    name="Rival Bank SG (FICTIONAL)",
    market=Market.SG,
    vertical=Vertical.BANKING,
    tenant="other-bank",
)
ACCOUNTS[_OTHER_TENANT_ACCOUNT.id] = _OTHER_TENANT_ACCOUNT


# --------------------------------------------------------------------------- #
# A/B experiments, per (market, vertical). One clearly-significant winner and
# one underpowered test so the significance engine exercises both verdicts.
# --------------------------------------------------------------------------- #
def _experiments_for(key: _Key) -> tuple[AbTest, ...]:
    market, vertical = key
    tag = f"{market.value.lower()}-{vertical.value}"
    metric = "signup_rate" if vertical is Vertical.BANKING else "purchase_rate"
    return (
        AbTest(
            id=f"{tag}-exp-hero",
            metric=metric,
            control=AbVariant(name="control", visitors=10000, conversions=500),
            variant=AbVariant(name="variant", visitors=10000, conversions=620),
            market=market,
            vertical=vertical,
            citation=_cit(
                f"{tag}-exp-hero",
                f"{tag} hero CTA experiment",
                1,
                "2026-06-20",
                SourceType.EXPERIMENT,
            ),
        ),
        AbTest(
            id=f"{tag}-exp-copy",
            metric=metric,
            control=AbVariant(name="control", visitors=80, conversions=8),
            variant=AbVariant(name="variant", visitors=80, conversions=10),
            market=market,
            vertical=vertical,
            citation=_cit(
                f"{tag}-exp-copy", f"{tag} copy experiment", 1, "2026-06-20", SourceType.EXPERIMENT
            ),
        ),
    )


EXPERIMENTS: dict[_Key, tuple[AbTest, ...]] = {
    key: _experiments_for(key) for key in CHANNEL_METRICS
}


# Convenience: default attribution model and the set of seeded (market, vertical) keys.
DEFAULT_ATTRIBUTION_MODEL = AttributionModel.POSITION_BASED
SEEDED_KEYS: tuple[_Key, ...] = tuple(CHANNEL_METRICS)
