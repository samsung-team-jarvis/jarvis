import json
import pathlib

import pytest

from services.safety_guard.rules import (
    ASK_REASON,
    INVALID_REASON,
    NO_QUESTION_REASON,
    REASONS,
    STATES,
    judge,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
HARD_NEGATIVE = {
    "v1": ROOT / "data" / "llm" / "hard_negative_v1.jsonl",
    "v2": ROOT / "data" / "llm" / "hard_negative_v2.jsonl",  # 장치 8종·결제 (LLM-14)
}

BURNER_ON = {"action": "TURN_ON", "target": "burner_1"}
BURNER_UP = {"action": "SET_LEVEL", "target": "burner_2", "level": 3}
BURNER_DOWN = {"action": "SET_LEVEL", "target": "burner_2", "level": 1}
FRYER_ON = {"action": "TURN_ON", "target": "fryer"}
FRYER_UP = {"action": "SET_LEVEL", "target": "fryer", "level": 2}
HEATING = [BURNER_ON, BURNER_UP, BURNER_DOWN, FRYER_ON, FRYER_UP]
SAFE_CALLS = [
    {"action": "TURN_OFF", "target": "burner_1"},
    {"action": "TURN_OFF", "target": "all"},
    {"action": "EMERGENCY_STOP", "target": "all"},
    {"action": "TURN_ON", "target": "hood"},
    {"action": "SET_LEVEL", "target": "hood", "level": 3},
    {"action": "SET_TIMER", "duration_s": 180, "target": "burner_1"},
    {"action": "CANCEL_TIMER"},
    {"action": "CHECK_STATUS"},
    {"action": "CHECK_RISK"},
    {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": ["target"]},
    {"action": "UNSUPPORTED"},
    {"action": "TURN_OFF", "target": "fryer"},
    {"action": "TURN_ON", "target": "light"},
    {"action": "SET_LEVEL", "target": "music", "level": 1},
    {"action": "TURN_ON", "target": "aircon"},
    {"action": "CHECK_AMOUNT"},
]


@pytest.mark.parametrize("state", ["IDLE", "PREHEAT", "COOKING"])
@pytest.mark.parametrize("call", HEATING)
def test_heating_allowed_in_normal_states(state: str, call: dict) -> None:
    assert judge(call, state).decision == "ALLOW"


@pytest.mark.parametrize("state", ["UNATTENDED", "DANGER", "SAFE_STOP", None])
@pytest.mark.parametrize("call", HEATING)
def test_heating_rejected_in_risky_or_unknown_state(state: str | None, call: dict) -> None:
    d = judge(call, state)
    assert (d.decision, d.reason) == ("REJECT", REASONS[state])


@pytest.mark.parametrize("state", [*STATES, None])
@pytest.mark.parametrize("call", SAFE_CALLS)
def test_turning_off_and_non_heating_always_allowed(state: str | None, call: dict) -> None:
    assert judge(call, state).decision == "ALLOW"


@pytest.mark.parametrize(
    "call",
    [
        {"action": "TURN_ON", "target": "oven"},  # 없는 장치
        {"action": "SET_LEVEL", "target": "hood", "level": 9},  # 범위 밖
        {"action": "SELF_DESTRUCT"},  # 없는 Action
        {"target": "hood"},  # action 없음
        {"action": "TURN_ON", "target": "hood", "level": 3},  # 없는 파라미터
    ],
)
def test_invalid_call_rejected_in_any_state(call: dict) -> None:
    d = judge(call, "IDLE")
    assert (d.decision, d.reason) == ("REJECT", INVALID_REASON)


@pytest.mark.parametrize("state", [*STATES, None])
def test_payment_always_asks(state: str | None) -> None:
    d = judge({"action": "REQUEST_PAYMENT"}, state)
    assert (d.decision, d.reason) == ("ASK", ASK_REASON)


@pytest.mark.parametrize("action", ["CONFIRM", "DENY"])
def test_reply_without_question_rejected(action: str) -> None:
    """기다리는 질문이 있을 때의 대답은 서비스가 먼저 처리한다. 여기 오면 질문이 없는 경우다."""
    d = judge({"action": action}, "IDLE")
    assert (d.decision, d.reason) == ("REJECT", NO_QUESTION_REASON)


def _danger_examples(version: str) -> list[dict]:
    lines = HARD_NEGATIVE[version].read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    return [r for r in rows if r["meta"].get("expect_guard")]


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_hard_negative_expect_guard_matches_rules(version: str) -> None:
    """LLM 데이터의 위험 상황 Hard Negative(LLM-03)와 Guard 규칙이 같은 판정을 내야 한다."""
    examples = _danger_examples(version)
    assert len(examples) == 34
    wrong = [
        (r["instruction"], r["context"]["state"], r["meta"]["expect_guard"])
        for r in examples
        if judge(r["output"], r["context"]["state"]).decision != r["meta"]["expect_guard"]
    ]
    assert wrong == []
