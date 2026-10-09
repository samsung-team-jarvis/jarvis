"""Safety Guard 판정 규칙 (안전 계층 L1, FUS-03). 결정론적 규칙만 쓴다.

명령(Function Call) + 지금 주방 상태(State) → ALLOW / REJECT (+ 읽어 줄 이유).
결정 근거: docs/decisions/2026-10-01-safety-layers.md, 2026-10-02-llm-literal-guard-decides.md
(LLM은 말 그대로 해석하고, 위험 판단은 여기서 한다).

| 명령 | 평소 상태 | 위험 상태·상태 모름 |
|---|---|---|
| 형식이 틀린 명령 | REJECT | REJECT |
| 가열 장치(화구 2개·튀김기) 켜기·세기 바꾸기 | ALLOW | REJECT |
| 결제 요청 | ASK | ASK |
| "네"·"아니요" (기다리는 질문이 없을 때) | REJECT | REJECT |
| 그 밖의 모든 명령 (끄기·후드·타이머·확인·긴급 정지·되묻기·지원 외) | ALLOW | ALLOW |

- 끄는 쪽(끄기·긴급 정지)은 어떤 상태에서도 막지 않는다. 막으면 더 위험해진다.
- 세기를 낮추는 명령도 위험 상태에서는 막는다. Guard는 지금 세기를 모르므로 "낮춤"과
  "꺼진 화구를 켜는 것"을 구분할 수 없다. 대신 이유에 "끄려면 꺼 달라고 말하라"를 안내한다.
- 상태를 아직 한 번도 받지 못했으면(상황 인식이 없거나 아직 안 뜸) 위험 상태와 같게 본다.
- 결제는 되돌리기 어려워서 상태와 무관하게 항상 확인(ASK)을 받는다. 확인을 기다리는 동안의
  "네"·"아니요"는 서비스(service.py)가 처리하고, 여기서는 기다리는 질문이 없는 경우만 판정한다.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from common.function_call import FunctionCallError, validate
from common.kitchen_link import HEATERS

# interfaces §2.3 State
STATES = ("IDLE", "PREHEAT", "COOKING", "UNATTENDED", "DANGER", "SAFE_STOP")
# 가열 장치를 새로 켜거나 세기를 바꾸면 안 되는 상태
RISKY_STATES = frozenset({"UNATTENDED", "DANGER", "SAFE_STOP"})
UNKNOWN_STATE = None  # fusion/state를 아직 받지 못함
# 가열 장치 (화구 2개·튀김기, interfaces §2.2)
HEATING_DEVICES = frozenset(HEATERS)
# 가열 장치에 대해 막는 Action
HEATING_UP_ACTIONS = frozenset({"TURN_ON", "SET_LEVEL"})
# 항상 확인을 받는 Action (되돌리기 어렵다)
ASK_ACTIONS = frozenset({"REQUEST_PAYMENT"})
# 확인 질문에 대한 대답
REPLY_ACTIONS = frozenset({"CONFIRM", "DENY"})

ALLOW, REJECT, ASK = "ALLOW", "REJECT", "ASK"

# REJECT 이유 — 음성 응답(audio_svc.responses)이 "지금은 ○○을 제어할 수 없어요." 뒤에 붙여 읽는다.
REASONS = {
    "DANGER": "온도가 너무 높아요. 끄려면 꺼 달라고 말해 주세요.",
    "UNATTENDED": "조리 구역에 사람이 없어요. 자리로 돌아온 뒤 다시 말해 주세요.",
    "SAFE_STOP": "긴급 정지 상태예요. 안전을 확인한 뒤 다시 말해 주세요.",
    UNKNOWN_STATE: "주방 상태를 아직 확인하지 못했어요.",
}
INVALID_REASON = "명령을 이해하지 못했어요."
ASK_REASON = "결제는 확인을 받은 뒤 실행해요."
NO_QUESTION_REASON = "확인할 질문이 없어요."


@dataclasses.dataclass(frozen=True)
class Decision:
    decision: str  # ALLOW | REJECT | ASK
    reason: str  # REJECT·ASK일 때 읽어 줄 이유, ALLOW면 ""


def judge(call: dict[str, Any], state: str | None) -> Decision:
    """명령과 지금 상태로 허용 여부를 정한다. state=None은 상태를 모르는 경우.

    "네"·"아니요"는 기다리는 질문이 없다고 보고 판정한다 (질문이 있으면 서비스가 먼저 처리한다).
    """
    try:
        validate(call)
    except FunctionCallError:
        return Decision(REJECT, INVALID_REASON)

    if call["action"] in ASK_ACTIONS:
        return Decision(ASK, ASK_REASON)
    if call["action"] in REPLY_ACTIONS:
        return Decision(REJECT, NO_QUESTION_REASON)
    heating_up = call["action"] in HEATING_UP_ACTIONS and call.get("target") in HEATING_DEVICES
    if heating_up and (state is UNKNOWN_STATE or state in RISKY_STATES):
        return Decision(REJECT, REASONS[state])
    return Decision(ALLOW, "")
