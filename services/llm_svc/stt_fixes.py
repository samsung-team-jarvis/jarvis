"""STT 오인식 사전 (STT-10): 파서(·LLM)에 넣기 전에 자주 틀리는 받아쓰기를 고친다.

근거는 사람 음성 녹음의 **val 화자**에서만 찾는다
(test 화자를 보고 고치지 않는다 — experiment 원칙 2).
stt/text에는 원문이 그대로 남고, 고친 문장은 llm/function_call의 raw_text로 남는다.
"""

from __future__ import annotations

import re

# (틀린 표현, 고친 표현) — 위에서부터 차례로 바꾼다 (긴 것 먼저).
# 출처: spk01 val 40문장, MacBook 마이크 30cm 이내, 2026-10-02 (#61)
FIXES: tuple[tuple[str, str], ...] = (
    ("타임머", "타이머"),  # "타이머 취소해줘" → "타임머 취소해줘" (2건)
    ("세개", "세게"),  # "2번 화구 세게" → "이번화구 세개"
    ("세 개 해", "세게 해"),  # 띄어 쓴 꼴 — 합성 음성 리허설(#128). "세 개"만은 그대로
    ("번구", "번 화구"),  # "1번 화구" → "일 번구"
    ("일본 번", "일번"),  # "1번 화구" → "일본 번 화국"
    ("일본", "1번"),
)


def normalize(text: str) -> str:
    for wrong, right in FIXES:
        text = text.replace(wrong, right)
    return text


# 한자어 숫자 + 단위 → 아라비아 숫자. 서비스 입력(command_text)에만 — 학습 데이터 생성엔 안 쓴다.
# 받아쓰기는 "1번"을 "일 번", "2번"을 "입 번", "10분"을 "십 분"으로 내고, LLM은 이런 꼴에서 틀렸다
# ("일 번 화구" → 2번 화구, "입 분" → 8분). 근거: spk01 val을 서비스 경로로 받아쓴 결과 (#130)
_DIGIT = {"일": 1, "이": 2, "입": 2, "삼": 3, "사": 4, "오": 5}
_DIGIT |= {"육": 6, "륙": 6, "칠": 7, "팔": 8, "구": 9}
_NUM = r"(?:[이입삼사오육륙칠팔구]?십[일이삼사오육칠팔구]?|[일이입삼사오육륙칠팔구])"
# 번은 장치 앞에서만 ("이번에"처럼 숫자가 아닌 말이 많다), 단은 "으로"·"계" 앞이나 끝에서만
# ("일단 후드 켜"의 일단은 세기가 아니다). 분·초는 뒤에 한글이 바로 붙지 않을 때
_COUNTED = re.compile(
    rf"(?<![가-힣])({_NUM})\s*(?:(번)(?=\s*(?:째|화구|불|버너|구))"
    rf"|(분|초)(?![가-힣])|(단)(?=으로|계|\s*[.,?!]|\s*$))"
)
_DIGIT_SPACE = re.compile(r"(\d)\s+(번|분|초|단)")  # "1 번" → "1번"


def _value(word: str) -> int:
    if "십" not in word:
        return _DIGIT[word]
    tens, _, ones = word.partition("십")
    return (_DIGIT[tens] if tens else 1) * 10 + (_DIGIT[ones] if ones else 0)


def numerals(text: str) -> str:
    """ "일 번 화구" → "1번 화구", "입 분" → "2분", "삼십 초" → "30초", "1 번" → "1번"."""

    def digits(m: re.Match[str]) -> str:
        return str(_value(m.group(1))) + (m.group(2) or m.group(3) or m.group(4))

    text = _COUNTED.sub(digits, text)
    return _DIGIT_SPACE.sub(r"\1\2", text)
