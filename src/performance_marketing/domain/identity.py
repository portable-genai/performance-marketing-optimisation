"""Identity value objects for server-side, verified principals — RE-EXPORTED, not declared.

The agent never trusts a client-asserted ``actor`` or ACL. A :class:`Principal` is resolved
server-side by an :class:`~performance_marketing.ports.identity.IdentityPort` adapter (local
dev persona, GCP IAP-verified assertion, or an on-prem client IdP) from the inbound transport
context, and becomes the audit actor plus the entitlement principals fed into governed
retrieval.

These four names come from :mod:`hex_service_kit.identity`, which declares them once, so this
module's ``Principal`` and the commons ``Principal`` are the SAME object rather than two that
agree today. The alternative, declaring them here as a hand copy of the same source every
other repo reads, is what that prevents. ``tests/contract/test_port_parity.py`` asserts it with
``is``: a structural look-alike passes every isinstance check right up to the day one copy is
edited.

The re-export leaves the types intact: same fields, same defaults, same frozen/slots dataclass,
same ``actor`` property (the verified subject, for non-repudiation under MAS TRM / CPS 234).
Still pure standard library, so the domain core stays framework-free.
"""

from __future__ import annotations

from hex_service_kit.identity import ANONYMOUS as ANONYMOUS
from hex_service_kit.identity import IdentityError as IdentityError
from hex_service_kit.identity import Principal as Principal
from hex_service_kit.identity import RequestContext as RequestContext

__all__ = ["ANONYMOUS", "IdentityError", "Principal", "RequestContext"]
