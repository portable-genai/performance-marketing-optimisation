"""Local LLM adapter (LlmPort) — a deterministic, schema-driven narrator.

The ``local`` profile's stand-in for **Gemini**: no model, no network, fully reproducible.
It reads ``request.response_schema`` (the JSON schema the calling service asks for) and
emits a deterministic JSON object whose keys match it, including ``used_source_ids`` mapped
from the ``[source_id p.N]`` headers in the rendered FIGURES block, so the narration cites
only sources that were actually computed over. There is no Google emulator for Gemini, so
this path is unconditional. The LLM never decides the numbers: the deterministic engines do.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ...config import Settings
from ...domain.models import LlmRequest, LlmResponse, TokenUsage

_SOURCE_HEADER_RE = re.compile(r"\[([a-z0-9][a-z0-9\-]*?)(?:\s+p\.[^\]]+)?\]")


def _schema_properties(schema: dict | None) -> dict[str, Any]:
    if not schema:
        return {}
    props = schema.get("properties")
    return props if isinstance(props, dict) else {}


class LocalDeterministicLLMAdapter:
    """Deterministic LLM whose ``generate`` returns JSON matching the request schema."""

    REASONING_MODEL = "gemini-3.5-flash"
    TRIAGE_MODEL = "gemini-3.5-flash"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._reasoning_model = settings.models.reasoning or self.REASONING_MODEL
        self._triage_model = settings.models.triage or self.TRIAGE_MODEL

    def generate(self, request: LlmRequest) -> LlmResponse:
        source_ids = self._source_ids_from_request(request)
        body = self._body_for_schema(request.response_schema, source_ids)
        return LlmResponse(
            text=json.dumps(body),
            usage=TokenUsage(input_tokens=128, output_tokens=64, thinking_tokens=32),
            model=request.model or self._reasoning_model,
            web_citations=(),
            raw=body,
        )

    def classify(self, text: str, labels: list[str]) -> str:
        return labels[0] if labels else ""

    # ------------------------------------------------------------------ #
    # Schema-driven body
    # ------------------------------------------------------------------ #
    def _source_ids_from_request(self, request: LlmRequest) -> list[str]:
        user = ""
        for message in reversed(request.messages):
            if message.role == "user":
                user = message.content
                break
        seen: list[str] = []
        for sid in _SOURCE_HEADER_RE.findall(user):
            if sid not in seen:
                seen.append(sid)
        return seen

    def _body_for_schema(self, schema: dict | None, source_ids: list[str]) -> dict[str, Any]:
        props = _schema_properties(schema)
        sid = list(source_ids)
        if "summary" in props:
            summary = (
                "Channel efficiency was scored deterministically against the configured ROAS / "
                "CAC target; under-performing channels are proposed for a bounded, budget-neutral "
                "spend shift onto the efficient channels. A/B significance and metric anomalies "
                "were computed by the statistical engines. This summary is grounded in the cited "
                "figures and requires human review before any budget is moved."
            )
            return {"summary": summary, "used_source_ids": sid}
        # Flat fallback object (self-critique style).
        return {"grounded": bool(sid), "confidence": 0.86 if sid else 0.2, "caveats": []}
