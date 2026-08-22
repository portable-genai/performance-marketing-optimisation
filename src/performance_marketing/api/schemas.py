"""API request/response schemas (thin Pydantic models at the HTTP boundary)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..domain.models import AgentCard


class ReportRequestModel(BaseModel):
    account_id: str = Field(..., description="The account to report on.")
    market: str = Field("SG", description="Market: JP | AU | SG.")
    vertical: str = Field("banking", description="Vertical: banking | online_retail.")
    attribution_model: str = Field(
        "position_based",
        description="last_touch | first_touch | linear | position_based.",
    )
    lookback_days: int = 30


class HealthModel(BaseModel):
    status: str = "ok"
    profile: str
    market: str
    vertical: str


class AgentSkillModel(BaseModel):
    id: str
    name: str
    description: str


class AgentCardModel(BaseModel):
    """A2A AgentCard served at ``/.well-known/agent-card.json`` (Hrz3 discovery shape)."""

    name: str
    description: str
    url: str
    version: str
    skills: list[AgentSkillModel] = Field(default_factory=list)
    provider: str

    @classmethod
    def from_domain(cls, card: AgentCard) -> AgentCardModel:
        return cls(
            name=card.name,
            description=card.description,
            url=card.url,
            version=card.version,
            skills=[
                AgentSkillModel(id=s.id, name=s.name, description=s.description)
                for s in card.skills
            ],
            provider=card.provider,
        )
