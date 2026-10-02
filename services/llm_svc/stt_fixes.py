"""STT 오인식 사전 (STT-10): 파서(·LLM)에 넣기 전에 자주 틀리는 받아쓰기를 고친다.

근거는 사람 음성 녹음의 **val 화자**에서만 찾는다
(test 화자를 보고 고치지 않는다 — experiment 원칙 2).
stt/text에는 원문이 그대로 남고, 고친 문장은 llm/function_call의 raw_text로 남는다.
"""

from __future__ import annotations

# (틀린 표현, 고친 표현) — 위에서부터 차례로 바꾼다 (긴 것 먼저).
# 출처: spk01 val 40문장, MacBook 마이크 30cm 이내, 2026-10-02 (#61)
FIXES: tuple[tuple[str, str], ...] = (
    ("타임머", "타이머"),  # "타이머 취소해줘" → "타임머 취소해줘" (2건)
    ("세개", "세게"),  # "2번 화구 세게" → "이번화구 세개"
    ("번구", "번 화구"),  # "1번 화구" → "일 번구"
    ("일본 번", "일번"),  # "1번 화구" → "일본 번 화국"
    ("일본", "1번"),
)


def normalize(text: str) -> str:
    for wrong, right in FIXES:
        text = text.replace(wrong, right)
    return text
