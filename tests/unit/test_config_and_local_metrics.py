"""Unit tests for config (vertical/market/region) and the local metrics warehouse."""

from __future__ import annotations

from performance_marketing.adapters.local.ad_platform import LocalAdPlatformAdapter
from performance_marketing.adapters.local.metrics import LocalMetricsAdapter
from performance_marketing.config import Settings
from performance_marketing.domain.models import Market, Vertical


def test_config_resolves_active_vertical_and_market(local_settings: Settings):
    assert local_settings.active_vertical is Vertical(local_settings.vertical)
    assert local_settings.active_market is Market(local_settings.market)


def test_market_profiles_carry_residency_regions(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).region == "asia-northeast1"
    assert local_settings.market_profile(Market.AU).region == "australia-southeast1"
    assert local_settings.market_profile(Market.SG).region == "asia-southeast1"


def test_jp_profile_is_bilingual(local_settings: Settings):
    assert local_settings.market_profile(Market.JP).locales == ("ja", "en")


def test_env_overrides_select_vertical_and_market(monkeypatch):
    monkeypatch.setenv("MKT_VERTICAL", "online_retail")
    monkeypatch.setenv("MKT_MARKET", "JP")
    settings = Settings.load("config/settings.yaml")
    assert settings.active_vertical is Vertical.ONLINE_RETAIL
    assert settings.active_market is Market.JP


def test_local_metrics_are_scoped_and_cited(local_settings: Settings):
    adapter = LocalMetricsAdapter(local_settings)
    rows = adapter.channel_metrics("acct-sg-banking", Market.SG, Vertical.BANKING, 30)
    assert rows, "local warehouse returned nothing for the seeded data"
    assert all(r.citation is not None for r in rows)
    assert all(r.spend >= 0 for r in rows)


def test_local_account_carries_target_and_strategies(local_settings: Settings):
    adapter = LocalAdPlatformAdapter(local_settings)
    account = adapter.account("acct-au-online_retail", Market.AU, Vertical.ONLINE_RETAIL)
    assert account.market is Market.AU
    assert account.vertical is Vertical.ONLINE_RETAIL
    assert account.roas_target is not None
    assert account.roas_target.has_roas  # retail uses a ROAS floor
    assert account.bid_strategies


def test_local_account_unknown_id_falls_back_by_key(local_settings: Settings):
    adapter = LocalAdPlatformAdapter(local_settings)
    # An unknown id still resolves to the seeded (market, vertical) account.
    account = adapter.account("does-not-exist", Market.SG, Vertical.BANKING)
    assert account.vertical is Vertical.BANKING
