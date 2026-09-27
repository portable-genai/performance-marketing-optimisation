"""The Model Armor adapter allows ONLY a complete, clean screen, and fails closed on the rest.

Allowed means ``sanitizationResult.filterMatchState`` is ``"NO_MATCH_FOUND"`` AND
``sanitizationResult.invocationResult`` is ``"SUCCESS"``. The mapping this replaces allowed
whenever the state was anything but ``MATCH_FOUND``, and fell back to "no parsed findings"
when the state was absent, so it passed:

* ``NO_MATCH_FOUND`` with ``PARTIAL`` or ``FAILURE``: a skipped filter (input past its token
  limit, an unsupported language, a detector error) reports no match, so padding a prompt past
  the prompt-injection filter's limit got it through unscreened;
* ``FILTER_MATCH_STATE_UNSPECIFIED``;
* a missing or empty ``sanitizationResult``. proto3 JSON omits a field at its default, so an
  unspecified state arrives on the wire as no key at all, which the old fallback read as clean.

The adapter speaks REST, so the wire shape IS the proto3 JSON encoding of the
``modelarmor_v1`` messages. This module tests at two levels:

* **SDK-free** (always runs, including CI's SDK-free offline gate): responses are hand-built
  JSON dicts with enum names taken from ``_MirrorState`` / ``_MirrorInvocation``, stdlib enums
  carrying the real member names and numbers, fed through ``screen()`` with a fake HTTP client.
* **Real SDK** (runs where ``google-cloud-modelarmor`` is installed, skips on the SDK-free
  profile): responses are REAL ``modelarmor_v1`` messages serialised to the JSON the REST API
  returns, fed through ``screen()`` the same way. The first of these tests pins the mirror to
  the real enums, so the SDK-free half cannot drift.

Nothing touches the network.
"""

from __future__ import annotations

import enum
import json as _json
from typing import Any

import httpx
import pytest

from performance_marketing.adapters.gcp.model_armor_guardrail import ModelArmorGuardrailAdapter
from performance_marketing.config import Settings
from performance_marketing.domain.models import Direction

TEXT = "Shift 40% of the paid-social budget into search for the SG launch."
DIRECTIONS = [Direction.INPUT, Direction.OUTPUT]


class _MirrorState(enum.IntEnum):
    """``modelarmor_v1.FilterMatchState``'s members, by name and number."""

    FILTER_MATCH_STATE_UNSPECIFIED = 0
    NO_MATCH_FOUND = 1
    MATCH_FOUND = 2


class _MirrorInvocation(enum.IntEnum):
    """``modelarmor_v1.InvocationResult``'s members, by name and number."""

    INVOCATION_RESULT_UNSPECIFIED = 0
    SUCCESS = 1
    PARTIAL = 2
    FAILURE = 3


class _FakeHttp:
    """Stands in for ``httpx.Client``: returns a canned JSON body, or raises a canned error."""

    def __init__(
        self, body: Any = None, *, status: int = 200, error: Exception | None = None
    ) -> None:
        self._body = body
        self._status = status
        self._error = error
        self.urls: list[str] = []
        self.timeouts: list[Any] = []

    def post(self, url: str, *, json: Any, headers: Any, timeout: Any) -> httpx.Response:
        self.urls.append(url)
        self.timeouts.append(timeout)
        if self._error is not None:
            raise self._error
        return httpx.Response(
            self._status,
            content=_json.dumps(self._body).encode(),
            headers={"Content-Type": "application/json"},
            request=httpx.Request("POST", url),
        )


def _adapter(http: _FakeHttp) -> ModelArmorGuardrailAdapter:
    adapter = ModelArmorGuardrailAdapter(Settings(project_id="p", profile="gcp"))
    adapter._client = http  # skip the real client; the mapping is what is under test
    adapter._bearer_token = lambda: "test-token"  # type: ignore[method-assign]
    return adapter


def _screen(body: Any, direction: Direction = Direction.INPUT) -> Any:
    return _adapter(_FakeHttp(body)).screen(TEXT, direction)


def _wire(
    state: _MirrorState | None,
    invocation: _MirrorInvocation | None = _MirrorInvocation.SUCCESS,
    *,
    skipped: bool = False,
) -> dict[str, Any]:
    """The REST body. proto3 JSON omits a field at its default, so UNSPECIFIED is no key."""
    result: dict[str, Any] = {}
    if state is not None and state.value:
        result["filterMatchState"] = state.name
    if invocation is not None and invocation.value:
        result["invocationResult"] = invocation.name
    if skipped:
        result["filterResults"] = {
            "pi_and_jailbreak": {
                "piAndJailbreakFilterResult": {
                    "executionState": "EXECUTION_SKIPPED",
                    "matchState": "NO_MATCH_FOUND",
                }
            }
        }
    return {"sanitizationResult": result}


# --------------------------------------------------------------------------- #
# SDK-free: the mapping itself, through screen()
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks_sdk_free(direction: Direction) -> None:
    verdict = _screen(_wire(_MirrorState.MATCH_FOUND), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows_sdk_free(direction: Direction) -> None:
    verdict = _screen(_wire(_MirrorState.NO_MATCH_FOUND), direction)
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT
    assert verdict.findings == ()


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation", list(_MirrorInvocation), ids=lambda m: m.name)
def test_match_found_blocks_however_many_filters_ran_sdk_free(
    direction: Direction, invocation: _MirrorInvocation
) -> None:
    verdict = _screen(_wire(_MirrorState.MATCH_FOUND, invocation), direction)
    assert verdict.allowed is False


@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "invocation",
    [
        _MirrorInvocation.PARTIAL,
        _MirrorInvocation.FAILURE,
        _MirrorInvocation.INVOCATION_RESULT_UNSPECIFIED,
        None,
    ],
    ids=["PARTIAL", "FAILURE", "UNSPECIFIED", "absent"],
)
def test_no_match_from_an_incomplete_screen_blocks_sdk_free(
    direction: Direction, invocation: _MirrorInvocation | None
) -> None:
    """A skipped filter reports no match. That is not a pass: the text was not screened."""
    verdict = _screen(_wire(_MirrorState.NO_MATCH_FOUND, invocation, skipped=True), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason


def test_exactly_one_combination_allows_sdk_free() -> None:
    allowed = [
        (state.name, invocation.name)
        for state in _MirrorState
        for invocation in _MirrorInvocation
        if _screen(_wire(state, invocation)).allowed
    ]
    assert allowed == [("NO_MATCH_FOUND", "SUCCESS")]


@pytest.mark.parametrize(
    "body",
    [
        _wire(_MirrorState.FILTER_MATCH_STATE_UNSPECIFIED),
        {"sanitizationResult": {"filterMatchState": "FILTER_MATCH_STATE_UNSPECIFIED"}},
        {"sanitizationResult": {}},
        {"sanitizationResult": None},
        {},
        None,
        [],
        # An integer-encoded enum is not the name; it must not slip past a comparison.
        {"sanitizationResult": {"filterMatchState": 1, "invocationResult": 1}},
    ],
    ids=[
        "unspecified-omitted",
        "unspecified-explicit",
        "empty-result",
        "null-result",
        "missing-result",
        "null-body",
        "non-object-body",
        "integer-enums",
    ],
)
def test_no_verdict_fails_closed_sdk_free(body: Any) -> None:
    verdict = _screen(body)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_call_carries_the_deadline(direction: Direction) -> None:
    http = _FakeHttp(_wire(_MirrorState.NO_MATCH_FOUND))
    _adapter(http).screen(TEXT, direction)
    assert http.timeouts == [Settings().model_armor.timeout_seconds]
    assert http.timeouts[0] > 0


@pytest.mark.parametrize(
    "http",
    [
        _FakeHttp(error=httpx.ReadTimeout("Model Armor timed out")),
        _FakeHttp(error=httpx.ConnectError("Model Armor unreachable")),
        _FakeHttp({"error": {"code": 503}}, status=503),
        _FakeHttp({"error": {"code": 403}}, status=403),
    ],
    ids=["timeout", "connect-error", "http-503", "http-403"],
)
def test_api_errors_propagate(http: _FakeHttp) -> None:
    """An API failure must not turn into an allow; it reaches the caller, which audits it."""
    with pytest.raises(httpx.HTTPError):
        _adapter(http).screen(TEXT, Direction.INPUT)


# --------------------------------------------------------------------------- #
# Real SDK: real modelarmor_v1 messages, serialised to the REST wire shape
# --------------------------------------------------------------------------- #
def _ma() -> Any:
    return pytest.importorskip("google.cloud.modelarmor_v1")


def _real_body(
    direction: Direction,
    state_name: str | None,
    invocation_name: str = "SUCCESS",
    *,
    skipped: bool = False,
    print_defaults: bool = False,
) -> Any:
    """A real sanitize response as REST returns it; ``state_name=None`` leaves the result unset.

    ``skipped`` adds the prompt-injection filter as not having run, the shape a prompt padded
    past that filter's token limit produces. The REST API omits fields at their default (so an
    UNSPECIFIED enum is no key); ``print_defaults`` emits them instead, and the verdict must
    not depend on which encoding arrives.
    """
    ma = _ma()
    cls = (
        ma.SanitizeUserPromptResponse
        if direction is Direction.INPUT
        else ma.SanitizeModelResponseResponse
    )
    if state_name is None:
        message = cls()
    else:
        filter_results = {}
        if skipped:
            filter_results["pi_and_jailbreak"] = ma.FilterResult(
                pi_and_jailbreak_filter_result=ma.PiAndJailbreakFilterResult(
                    execution_state=ma.FilterExecutionState.EXECUTION_SKIPPED,
                    match_state=ma.FilterMatchState.NO_MATCH_FOUND,
                )
            )
        message = cls(
            sanitization_result=ma.SanitizationResult(
                filter_match_state=ma.FilterMatchState[state_name],
                invocation_result=ma.InvocationResult[invocation_name],
                filter_results=filter_results,
            )
        )
    # The REST API encodes enums by name; proto-plus defaults to integers, so say so.
    return _json.loads(
        cls.to_json(
            message,
            use_integers_for_enums=False,
            always_print_fields_with_no_presence=print_defaults,
        )
    )


@pytest.mark.parametrize(
    ("mirror", "real_name"),
    [(_MirrorState, "FilterMatchState"), (_MirrorInvocation, "InvocationResult")],
    ids=["FilterMatchState", "InvocationResult"],
)
def test_the_mirror_matches_the_real_enum(mirror: Any, real_name: str) -> None:
    real = getattr(_ma(), real_name)
    assert {m.name: int(m) for m in real} == {m.name: int(m) for m in mirror}


def test_the_mirror_wire_shape_matches_the_real_serialisation() -> None:
    for direction in DIRECTIONS:
        for state in _MirrorState:
            for invocation in _MirrorInvocation:
                real = _real_body(direction, state.name, invocation.name)
                assert real == _wire(state, invocation), (state.name, invocation.name)


@pytest.mark.parametrize("print_defaults", [False, True], ids=["rest-omits-defaults", "defaults"])
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_match_found_blocks(direction: Direction, print_defaults: bool) -> None:
    verdict = _screen(
        _real_body(direction, "MATCH_FOUND", print_defaults=print_defaults), direction
    )
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("print_defaults", [False, True], ids=["rest-omits-defaults", "defaults"])
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_no_match_found_with_success_allows(direction: Direction, print_defaults: bool) -> None:
    verdict = _screen(
        _real_body(direction, "NO_MATCH_FOUND", print_defaults=print_defaults), direction
    )
    assert verdict.allowed is True
    assert verdict.sanitized_text == TEXT


@pytest.mark.parametrize("print_defaults", [False, True], ids=["rest-omits-defaults", "defaults"])
@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize(
    "state_name",
    [None, "FILTER_MATCH_STATE_UNSPECIFIED"],
    ids=["missing-result", "unspecified-state"],
)
def test_no_verdict_fails_closed(
    direction: Direction, state_name: str | None, print_defaults: bool
) -> None:
    verdict = _screen(_real_body(direction, state_name, print_defaults=print_defaults), direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None


@pytest.mark.parametrize("print_defaults", [False, True], ids=["rest-omits-defaults", "defaults"])
@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("invocation_name", ["PARTIAL", "FAILURE", "INVOCATION_RESULT_UNSPECIFIED"])
def test_no_match_from_a_screen_where_filters_did_not_run_blocks(
    direction: Direction, invocation_name: str, print_defaults: bool
) -> None:
    body = _real_body(
        direction, "NO_MATCH_FOUND", invocation_name, skipped=True, print_defaults=print_defaults
    )
    verdict = _screen(body, direction)
    assert verdict.allowed is False
    assert verdict.sanitized_text is None
    assert "no complete filter decision" in verdict.reason
