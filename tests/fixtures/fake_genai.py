"""A stand-in for ``google.genai`` just wide enough for the Gemini adapter, with no SDK installed.

The gate runs with no cloud SDK, so a test that drives :class:`GeminiLLMAdapter` for real
installs this in ``sys.modules`` (through ``monkeypatch``, so nothing leaks) and hands the
adapter a client that records every ``generate_content`` call. What it records is exactly what
the adapter would have sent: the model id and the generation-config keyword arguments.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


class _Config:
    """``types.GenerateContentConfig``: keeps the keyword arguments it was built with."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def _types() -> ModuleType:
    module = ModuleType("google.genai.types")
    module.Content = lambda role, parts: SimpleNamespace(role=role, parts=parts)  # type: ignore[attr-defined]
    module.Part = SimpleNamespace(from_text=lambda text: SimpleNamespace(text=text))  # type: ignore[attr-defined]
    module.GenerateContentConfig = _Config  # type: ignore[attr-defined]
    module.ThinkingConfig = lambda **kwargs: SimpleNamespace(**kwargs)  # type: ignore[attr-defined]
    module.ThinkingLevel = SimpleNamespace(LOW="LOW", HIGH="HIGH")  # type: ignore[attr-defined]
    return module


@dataclass
class RecordingClient:
    """A ``genai.Client`` whose ``models.generate_content`` records and answers ``reply``."""

    reply: str = '{"summary": "narrated", "used_source_ids": []}'
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def models(self) -> RecordingClient:
        return self

    def generate_content(self, *, model: str, contents: Any, config: _Config) -> Any:
        self.calls.append({"model": model, "config": dict(config.kwargs)})
        return SimpleNamespace(text=self.reply, usage_metadata=None)


def install(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``from google.genai import types`` resolve to the stand-in for this test only."""
    types = _types()
    genai = ModuleType("google.genai")
    genai.types = types  # type: ignore[attr-defined]
    google = sys.modules.get("google") or ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
