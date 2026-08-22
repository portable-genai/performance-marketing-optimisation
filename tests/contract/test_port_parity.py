"""Contract tests: the ``onprem`` and ``local`` adapters are structural parity of the ports.

For every port the catalog declares, this iterates the adapter map and, for both the
``onprem`` and ``local`` profiles, imports + constructs the bound class (which must build
cleanly with **no Google Cloud SDK** installed), then asserts:

  1. the constructed instance satisfies its runtime_checkable Protocol (isinstance), and
  2. every method/property the Protocol declares actually exists on the instance.

It additionally proves the two profiles' distinct contracts:

* ``onprem`` is the fail-fast migration target: every method raises ``NotImplementedError``
  (proven on a representative port), and
* ``local`` is a WORKING offline stack: the same ports construct and answer in-process.

This is the proof of the ports-and-adapters / no-lock-in promise: the on-prem migration
target and the offline local stack implement the exact same interface as the managed GCP
stack.
"""

from __future__ import annotations

import importlib
from typing import Protocol, get_type_hints

import pytest

from performance_marketing import config, ports
from performance_marketing.config import LocalSettings, Settings, instantiate

CONFIG_PATH = "config/settings.yaml"

PORT_PROTOCOLS: dict[str, type] = {
    "metrics": ports.MetricsPort,
    "ad_platform": ports.AdPlatformPort,
    "llm": ports.LlmPort,
    "guardrail": ports.GuardrailPort,
    "audit": ports.AuditSinkPort,
    "tracer": ports.ObservabilityTracerPort,
    "evaluation": ports.EvaluationGatePort,
    "agent_registry": ports.AgentRegistryPort,
    "tool_catalog": ports.ToolCatalogPort,
    "identity": ports.IdentityPort,
    "review_router": ports.ReviewRouterPort,
}

# Profiles whose adapters must construct + satisfy the Protocols with no GCP SDK.
SDK_FREE_PROFILES = ("onprem", "local")


def _settings(profile: str) -> Settings:
    base = Settings.load(CONFIG_PATH)
    return Settings(
        project_id=base.project_id,
        region=base.region,
        profile=profile,
        vertical=base.vertical,
        market=base.market,
        models=base.models,
        bigquery=base.bigquery,
        forecast=base.forecast,
        model_armor=base.model_armor,
        logging=base.logging,
        agent_engine=base.agent_engine,
        local=LocalSettings(audit_path=":memory:"),
        markets=base.markets,
        adapters=base.adapters,
    )


def _protocol_members(protocol: type) -> set[str]:
    members = set(getattr(protocol, "__protocol_attrs__", set()))
    if not members:
        members |= set(get_type_hints(protocol).keys())
        for name in dir(protocol):
            if name.startswith("_"):
                continue
            members.add(name)
    return {m for m in members if not m.startswith("_")}


def test_every_port_has_an_explicit_binding_for_every_profile():
    settings = Settings.load(CONFIG_PATH)
    for port_name in PORT_PROTOCOLS:
        binding = settings.adapters.get(port_name, {})
        missing = set(config.RUNTIME_PROFILES) - set(binding)
        assert not missing, f"port '{port_name}' has no explicit bindings for {sorted(missing)}"


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_satisfies_protocol(profile: str, port_name: str):
    settings = _settings(profile)
    protocol = PORT_PROTOCOLS[port_name]
    dotted = settings.adapters[port_name][profile]

    adapter = instantiate(dotted, settings)

    assert isinstance(adapter, protocol), (
        f"{dotted} does not structurally satisfy {protocol.__name__}"
    )

    members = _protocol_members(protocol)
    declared = set().union(*(vars(klass) for klass in type(adapter).__mro__))
    for member in members:
        assert member in declared, (
            f"{dotted} is missing port method/attr '{member}' of {protocol.__name__}"
        )


@pytest.mark.parametrize("profile", SDK_FREE_PROFILES)
@pytest.mark.parametrize("port_name", sorted(PORT_PROTOCOLS))
def test_adapter_constructs_with_single_settings_arg(profile: str, port_name: str):
    """The build contract: every adapter is ``Adapter(settings: Settings)``."""
    settings = _settings(profile)
    dotted = settings.adapters[port_name][profile]
    module_path, _, class_name = dotted.partition(":")

    cls = getattr(importlib.import_module(module_path), class_name)
    instance = cls(settings)
    assert instance is not None


def test_onprem_metrics_fails_fast():
    """The on-prem stubs are fail-fast: a representative port raises NotImplementedError."""
    from performance_marketing.domain.models import Market, Vertical

    settings = _settings("onprem")
    adapter = instantiate(settings.adapters["metrics"]["onprem"], settings)
    with pytest.raises(NotImplementedError):
        adapter.channel_metrics("acct-sg-banking", Market.SG, Vertical.BANKING, 30)


def test_local_metrics_returns_real_data():
    """The local stack is WORKING: metrics return real, cited rows offline."""
    from performance_marketing.domain.models import Market, Vertical

    settings = _settings("local")
    adapter = instantiate(settings.adapters["metrics"]["local"], settings)
    rows = adapter.channel_metrics("acct-sg-banking", Market.SG, Vertical.BANKING, 30)
    assert rows, "local metrics returned no rows for the seeded warehouse"
    assert all(r.citation is not None for r in rows)


def test_all_protocols_are_runtime_checkable():
    for protocol in PORT_PROTOCOLS.values():
        assert issubclass(protocol, Protocol)  # type: ignore[arg-type]
        assert getattr(protocol, "_is_runtime_protocol", False), (
            f"{protocol.__name__} must be @runtime_checkable"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))


# --------------------------------------------------------------------------- #
# Drift guard: the shared types must BE the commons objects, not look-alikes.
# --------------------------------------------------------------------------- #
# `isinstance` against a runtime_checkable Protocol is structural, so a hand-copied
# Protocol declared in this repo satisfies every test above while being a SECOND
# definition that drifts the moment one copy is edited. Sixteen repositories had already
# hand-copied `ports/observability.py` and by the time anyone compared them they
# disagreed. Object IDENTITY is the only assertion that can tell a re-export from a copy,
# so this asserts `is` and nothing weaker.
def test_shared_ports_are_the_commons_objects_not_hand_copies():
    import agent_eval_kit
    import hex_service_kit.identity as commons_identity
    import hex_service_kit.observability as commons_observability

    assert ports.ObservabilityTracerPort is commons_observability.ObservabilityTracerPort
    assert ports.TokenUsage is commons_observability.TokenUsage
    assert ports.EvaluationGatePort is agent_eval_kit.EvaluationGatePort
    assert ports.IdentityPort is commons_identity.IdentityPort


def test_shared_domain_value_types_are_the_commons_objects():
    import agent_eval_kit.report as commons_report
    import hex_service_kit.observability as commons_observability

    from performance_marketing.domain import models

    assert models.TokenUsage is commons_observability.TokenUsage
    assert models.EvalReport is commons_report.EvalReport
    assert models.EvalMetricResult is commons_report.EvalMetricResult
