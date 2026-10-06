"""LLM에 넣는 입력 (학습·평가·보드 추론이 모두 같은 것을 쓴다, LLM-07).

학습한 모델은 짧은 지시문 하나와 사용자 메시지 하나만 받는다. 함수 설명과 예시는 데이터로 배웠으므로
넣지 않는다 (입력이 짧을수록 보드에서 첫 토큰이 빨리 나온다). 여기 문장을 바꾸면 다시 학습해야 한다.
chat template·끝 토큰: docs/decisions/2026-10-06-llm-input-format.md
"""

from __future__ import annotations

from typing import Any

FINETUNED_SYSTEM_PROMPT = "가게 음성 명령을 함수 토큰 한 줄로 바꾼다."


def user_message(instruction: str, context: dict[str, Any]) -> str:
    """호출어를 뺀 명령 문장 + 상황(interfaces §3.4의 context) → 사용자 메시지."""
    last = context.get("last_target") or "없음"
    return f"상황: state={context['state']}, 마지막 장치={last}\n말: {instruction}"
