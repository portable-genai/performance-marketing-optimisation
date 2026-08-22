"""Local ad-platform adapter (AdPlatformPort) — deterministic seeded accounts.

The ``local`` profile's stand-in for the paid-media ad-platform export plus the **Vertex AI
forecasting** hook: a deterministic feed over the bundled fictional accounts (``_seed.py``),
with no SDK and no network. It returns the account with its bid strategies and per-account
ROAS / CAC target, and the running A/B experiments. SDK-free and unconditional.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.errors import UnknownAccountError
from ...domain.models import AbTest, Account, Market, Vertical
from ._seed import ACCOUNTS, ACCOUNTS_BY_KEY, EXPERIMENTS


class LocalAdPlatformAdapter:
    """Deterministic ad-platform feed over the seeded fictional accounts."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def account(self, account_id: str, market: Market, vertical: Vertical) -> Account:
        account = ACCOUNTS.get(account_id) or ACCOUNTS_BY_KEY.get((market, vertical))
        if account is None:
            raise UnknownAccountError(
                f"no seeded account '{account_id}' for {market.value}/{vertical.value}"
            )
        return account

    def experiments(
        self, account_id: str, market: Market, vertical: Vertical
    ) -> tuple[AbTest, ...]:
        return EXPERIMENTS.get((market, vertical), ())
