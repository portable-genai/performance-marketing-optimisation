"""On-prem placeholder for ``AdPlatformPort`` — the sovereign migration target.

Constructs cleanly with no external dependencies and structurally satisfies the same
Protocol as the managed ad-platform adapter, so the contract tests prove interface parity.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import AbTest, Account, Market, Vertical

_MESSAGE = (
    "On-prem AdPlatformPort adapter is a migration placeholder; implement against your "
    "on-premise ad-platform integration. Core domain logic is unchanged."
)


class OnPremAdPlatformAdapter:
    """Placeholder ad-platform adapter for the on-prem profile."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def account(self, account_id: str, market: Market, vertical: Vertical) -> Account:
        raise NotImplementedError(_MESSAGE)

    def experiments(
        self, account_id: str, market: Market, vertical: Vertical
    ) -> tuple[AbTest, ...]:
        raise NotImplementedError(_MESSAGE)
