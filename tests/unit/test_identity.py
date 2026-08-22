"""Unit tests for the IdentityPort adapters (server-side, verified identity).

The local persona adapter is the offline (no IdP/AD/LDAP) identity source used for demos
and tests; the on-prem adapter is a fail-fast placeholder. These prove the identity seam
that supplies the audit actor and entitlement principals server-side, never trusting a
client-asserted ``actor``.
"""

from __future__ import annotations

import pytest

from performance_marketing.adapters.local.identity import LocalPersonaIdentityAdapter
from performance_marketing.adapters.onprem.identity import OnPremIdentityAdapter
from performance_marketing.config import Settings
from performance_marketing.domain.identity import IdentityError, RequestContext

_SETTINGS = Settings(profile="local")


def _adapter() -> LocalPersonaIdentityAdapter:
    return LocalPersonaIdentityAdapter(_SETTINGS)


def test_default_persona_when_no_header() -> None:
    principal = _adapter().resolve(RequestContext(headers={}))
    assert principal.subject == "demo.analyst@bank.example"
    assert principal.principals  # non-empty entitlements
    assert principal.tenant == "demo-bank"
    assert principal.actor == principal.subject  # audit actor is the verified subject


def test_persona_selected_by_header() -> None:
    principal = _adapter().resolve(RequestContext(headers={"x-dev-persona": "auditor"}))
    assert principal.subject == "demo.auditor@bank.example"
    assert principal.principals == ("group:audit",)


def test_persona_header_is_case_insensitive() -> None:
    # RequestContext lower-cases lookups, so a host that sends X-Dev-Persona still resolves.
    principal = _adapter().resolve(RequestContext(headers={"x-dev-persona": "other-tenant"}))
    assert principal.tenant == "other-bank"


def test_unknown_persona_raises() -> None:
    with pytest.raises(IdentityError):
        _adapter().resolve(RequestContext(headers={"x-dev-persona": "does-not-exist"}))


def test_personas_listing_for_picker() -> None:
    ids = {p["id"] for p in _adapter().personas()}
    assert {"analyst", "approver", "auditor", "other-tenant"} <= ids


def test_onprem_identity_fails_fast() -> None:
    adapter = OnPremIdentityAdapter(_SETTINGS)
    with pytest.raises(NotImplementedError):
        adapter.resolve(RequestContext(headers={}))


def test_personas_are_refused_when_the_local_profile_was_never_chosen() -> None:
    """Unset MKT_PERF_PROFILE is no choice, so the no-auth personas are not handed out."""
    with pytest.raises(IdentityError, match="MKT_PERF_PROFILE"):
        LocalPersonaIdentityAdapter(Settings(profile="local", profile_explicit=False))


def test_personas_are_refused_outside_the_local_profile() -> None:
    with pytest.raises(IdentityError, match="local-profile only"):
        LocalPersonaIdentityAdapter(Settings(profile="gcp"))
