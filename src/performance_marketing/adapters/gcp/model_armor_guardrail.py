"""Model Armor guardrail adapter (GuardrailPort) — A1 Guardrail Gateway, GCP backend.

Implements :class:`GuardrailPort` against **Model Armor**, the runtime AI-safety service of
the Gemini Enterprise Agent Platform. Inbound prompts are screened with
``:sanitizeUserPrompt`` and outbound model responses with ``:sanitizeModelResponse`` on the
regional endpoint (``modelarmor.<region>.rep.googleapis.com``) so all screening stays inside
the configured residency boundary.

The adapter parses ``sanitizationResult.filterResults`` (the prompt-injection / jailbreak,
Sensitive Data Protection and malicious-URI filters) into :class:`GuardrailFinding` records.

FAIL CLOSED. The verdict is ALLOWED only when ``sanitizationResult.filterMatchState`` is the
literal ``"NO_MATCH_FOUND"`` AND ``sanitizationResult.invocationResult`` is the literal
``"SUCCESS"``. Everything else blocks: ``MATCH_FOUND``; a missing or empty
``sanitizationResult`` (proto3 JSON omits a default field, so an ``UNSPECIFIED`` state arrives
as no key at all); and ``PARTIAL`` / ``FAILURE``, which Model Armor sets independently of the
match state and which arrive WITH ``NO_MATCH_FOUND``, because a filter that was skipped (input
past its token limit, an unsupported language, a detector error) reports no match. "No match"
from a screen that did not run is refused, not passed. Every call carries a deadline
(``model_armor.timeout_seconds``), and an HTTP error or timeout propagates to the caller,
which audits the refusal.

All Google Cloud / auth / HTTP SDK imports are LAZY (inside methods) so the on-prem / local
/ test profile imports this module with no GCP SDK installed.
"""

from __future__ import annotations

from typing import Any, TypeGuard

from ...config import Settings
from ...domain.models import Direction, GuardrailCategory, GuardrailFinding, GuardrailVerdict

_MATCH_FOUND = "MATCH_FOUND"
_NO_MATCH_FOUND = "NO_MATCH_FOUND"
_SUCCESS = "SUCCESS"


class ModelArmorGuardrailAdapter:
    """Screen prompts and responses through Model Armor's REST API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._armor = settings.model_armor
        self._project = settings.project_id
        self._region = settings.region
        self._client: Any | None = None
        self._credentials: Any | None = None
        self._auth_request: Any | None = None

    # ------------------------------------------------------------------ #
    # GuardrailPort
    # ------------------------------------------------------------------ #
    def screen(self, text: str, direction: Direction) -> GuardrailVerdict:
        """Screen ``text``: allowed only on a complete, clean screen; raises if unanswered."""
        verb = "sanitizeUserPrompt" if direction is Direction.INPUT else "sanitizeModelResponse"
        payload = self._build_payload(text, direction)
        url = (
            f"https://{self._armor.host}/v1/projects/{self._project}"
            f"/locations/{self._region}/templates/{self._armor.template_id}:{verb}"
        )
        response = self._post(url, payload)
        return self._parse(response, direction, text)

    # ------------------------------------------------------------------ #
    # Request construction (lazy httpx + google-auth)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_payload(text: str, direction: Direction) -> dict[str, Any]:
        # verify: https://docs.cloud.google.com/model-armor/sanitize-prompts-responses
        if direction is Direction.INPUT:
            return {"userPromptData": {"text": text}}
        return {"modelResponseData": {"text": text}}

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        client = self._http_client()
        headers = {
            "Authorization": f"Bearer {self._bearer_token()}",
            "Content-Type": "application/json",
        }
        resp = client.post(url, json=payload, headers=headers, timeout=self._armor.timeout_seconds)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data

    def _http_client(self) -> Any:
        import httpx  # noqa: PLC0415 — lazy

        if self._client is None:
            self._client = httpx.Client()
        return self._client

    def _bearer_token(self) -> str:
        import google.auth  # noqa: PLC0415 — lazy
        from google.auth.transport.requests import Request  # noqa: PLC0415 — lazy

        if self._credentials is None:
            self._credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._auth_request = Request()
        if not self._credentials.valid:
            self._credentials.refresh(self._auth_request)
        token: str = self._credentials.token
        return token

    # ------------------------------------------------------------------ #
    # Response parsing
    # ------------------------------------------------------------------ #
    def _parse(
        self, response: dict[str, Any], direction: Direction, original_text: str
    ) -> GuardrailVerdict:
        """Map a sanitize response to a verdict: allowed ONLY on a complete, clean screen.

        Complete means ``invocationResult`` is ``"SUCCESS"``; clean means ``filterMatchState``
        is ``"NO_MATCH_FOUND"``. Both are compared as exact strings, so a missing key, an
        integer-encoded enum or any other shape blocks rather than slipping past a ``!=``.
        """
        result = response.get("sanitizationResult") if isinstance(response, dict) else None
        if not isinstance(result, dict):
            result = {}
        filter_results = result.get("filterResults")
        if not isinstance(filter_results, dict):
            filter_results = {}
        findings: list[GuardrailFinding] = []
        findings.extend(self._parse_pi_jailbreak(filter_results))
        findings.extend(self._parse_sensitive_data(filter_results))
        findings.extend(self._parse_malicious_uris(filter_results))

        match_state = result.get("filterMatchState")
        invocation = result.get("invocationResult")
        if match_state == _NO_MATCH_FOUND and invocation == _SUCCESS:
            return GuardrailVerdict(
                allowed=True,
                direction=direction,
                findings=tuple(findings),
                sanitized_text=self._extract_sanitized_text(filter_results, original_text),
                reason=self._reason(True, findings),
            )
        if match_state == _MATCH_FOUND:
            reason = self._reason(False, findings)
        elif match_state == _NO_MATCH_FOUND:
            reason = "Blocked: Model Armor returned no complete filter decision."
            findings.append(
                GuardrailFinding(
                    category=GuardrailCategory.OTHER,
                    confidence="high",
                    detail=f"invocationResult={invocation or 'absent'}: not every filter ran.",
                )
            )
        else:
            reason = "Blocked: Model Armor returned no usable verdict."
            findings.append(
                GuardrailFinding(
                    category=GuardrailCategory.OTHER,
                    confidence="high",
                    detail=f"filterMatchState={match_state or 'absent'}: no verdict to allow on.",
                )
            )
        return GuardrailVerdict(
            allowed=False,
            direction=direction,
            findings=tuple(findings),
            sanitized_text=None,
            reason=reason,
        )

    @staticmethod
    def _is_match(node: Any) -> TypeGuard[dict[str, Any]]:
        return isinstance(node, dict) and node.get("matchState") == _MATCH_FOUND

    def _parse_pi_jailbreak(self, filter_results: dict[str, Any]) -> list[GuardrailFinding]:
        node = (filter_results.get("pi_and_jailbreak") or {}).get("piAndJailbreakFilterResult")
        if not self._is_match(node):
            return []
        confidence = str(node.get("confidenceLevel", "")).lower() or "high"
        return [
            GuardrailFinding(
                category=GuardrailCategory.PROMPT_INJECTION,
                confidence=confidence,
                detail="Model Armor prompt-injection / jailbreak filter matched.",
            )
        ]

    def _parse_sensitive_data(self, filter_results: dict[str, Any]) -> list[GuardrailFinding]:
        inspect = (filter_results.get("sdp") or {}).get("sdpFilterResult", {}).get("inspectResult")
        if not self._is_match(inspect):
            return []
        info_types = sorted(
            {
                str(f.get("infoType", ""))
                for f in (inspect.get("findings") or [])
                if f.get("infoType")
            }
        )
        detail = (
            f"Sensitive data detected: {', '.join(info_types)}."
            if info_types
            else "Model Armor Sensitive Data Protection filter matched."
        )
        return [
            GuardrailFinding(
                category=GuardrailCategory.SENSITIVE_DATA, confidence="high", detail=detail
            )
        ]

    def _parse_malicious_uris(self, filter_results: dict[str, Any]) -> list[GuardrailFinding]:
        node = (filter_results.get("malicious_uris") or {}).get("maliciousUriFilterResult")
        if not self._is_match(node):
            return []
        return [
            GuardrailFinding(
                category=GuardrailCategory.MALICIOUS_URL,
                confidence="high",
                detail="Model Armor malicious-URI filter matched.",
            )
        ]

    def _extract_sanitized_text(
        self, filter_results: dict[str, Any], original_text: str
    ) -> str | None:
        deidentify = (
            (filter_results.get("sdp") or {}).get("sdpFilterResult", {}).get("deidentifyResult")
        )
        if isinstance(deidentify, dict):
            data = deidentify.get("data") or {}
            text = data.get("text")
            if isinstance(text, str) and text:
                return text
        return original_text

    @staticmethod
    def _reason(allowed: bool, findings: list[GuardrailFinding]) -> str:
        if allowed:
            return "No blocking Model Armor filter matched."
        categories = ", ".join(sorted({f.category.value for f in findings}))
        return f"Blocked by Model Armor: {categories}." if categories else "Blocked."
