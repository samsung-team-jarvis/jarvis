"""긴급 빠른 경로 (FUS-04): "멈춰·그만·정지"는 명령 해석(LLM)을 기다리지 않고 바로 긴급 정지.

받아쓴 문장(`stt/text`)만 보고 결정론적으로 판단한다. 명령 해석 쪽(llm_svc)도 같은 말을
EMERGENCY_STOP으로 내지만, 그쪽은 LLM이 붙으면 수백 ms~수 초가 걸릴 수 있어 따로 둔다.

- 호출어가 있으면("자비스 멈춰") 명령 부분에 긴급어가 들어 있으면 긴급 정지.
  단 타이머 이야기("타이머 정지", "알람 그만")는 타이머 취소라서 제외한다.
- 호출어가 없으면 문장 전체가 짧은 긴급 표현일 때만("멈춰!", "그만 그만") 긴급 정지.
  다급할 때 호출어를 빼고 말할 수 있어서다. 대화 속 "그만 먹을래" 같은 말은 잡지 않는다.
"""

from __future__ import annotations

import re

from services.audio_svc.wake import split_wake

# 명령 부분에 들어 있으면 긴급 정지 (호출어가 있을 때)
# "위험해?"는 위험 확인(CHECK_RISK)이라 넣지 않는다. 규칙 파서(llm_svc)의 긴급어와 같은 목록이다.
EMERGENCY_WORDS = re.compile(r"긴급|비상|정지|멈춰|그만|스톱|스탑")
# 이런 말이 같이 있으면 타이머 이야기다 (타이머 취소는 명령 해석이 맡는다)
TIMER_WORDS = re.compile(r"타이머|알람|알림")
# 호출어 없이도 긴급 정지하는 표현 (띄어쓰기·문장부호를 뺀 문장 전체가 이것들의 반복이어야 한다)
BARE_PHRASES = ("긴급정지", "비상정지", "멈춰줘", "멈춰", "그만", "정지", "스톱", "스탑", "비상")
_BARE = re.compile(rf"^(?:{'|'.join(BARE_PHRASES)})+$")


def _squash(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def is_emergency(text: str, wake: bool) -> bool:
    """받아쓴 문장이 긴급 정지 요청이면 True."""
    if wake:
        command = split_wake(text)
        command = _squash(command if command is not None else text)
        return bool(EMERGENCY_WORDS.search(command)) and not TIMER_WORDS.search(command)
    return bool(_BARE.match(_squash(text)))
