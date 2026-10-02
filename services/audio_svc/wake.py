"""텍스트 기반 호출어 (docs/decisions/open-questions.md Q-08 v0).

받아쓴 문장이 호출어로 시작할 때만 명령으로 본다. 비교할 때 띄어쓰기·문장부호는 무시한다
(SenseVoice가 "자비스야"를 "자비 스야"로 받아쓴 사례가 있다).
"""

from __future__ import annotations

# 오인식 변형은 STT-05 사람 녹음에서 확인한 것만 추가한다 (후보는 README).
WAKE_WORDS: tuple[str, ...] = ("자비스",)
# 호출어 바로 뒤의 호격 조사 ("자비스야", "자비스아")
_VOCATIVES = ("야", "아")


def _skippable(ch: str) -> bool:
    return not ch.isalnum()


def _match(text: str, word: str) -> int | None:
    """text가 word로 시작하면(띄어쓰기·문장부호 무시) word가 끝나는 위치, 아니면 None."""
    i = matched = 0
    while i < len(text) and matched < len(word):
        if _skippable(text[i]):
            i += 1
        elif text[i] == word[matched]:
            i += 1
            matched += 1
        else:
            return None
    return i if matched == len(word) else None


def _strip_leading(text: str) -> str:
    i = 0
    while i < len(text) and _skippable(text[i]):
        i += 1
    return text[i:]


def split_wake(text: str, wake_words: tuple[str, ...] = WAKE_WORDS) -> str | None:
    """호출어로 시작하면 호출어 뒤의 명령 부분을, 아니면 None을 돌려준다.

    "자비스, 후드 켜 줘." → "후드 켜 줘."   "자비 스야 후드 켜 줘." → "후드 켜 줘."
    "자비스." → "" (호출만 함)              "저기 자비스 후드 켜 줘" → None
    """
    for word in wake_words:
        end = _match(text, word)
        if end is None:
            continue
        rest = text[end:]
        for v in _VOCATIVES:
            after = rest[len(v) :]
            if rest.startswith(v) and (not after or _skippable(after[0])):
                rest = after
                break
        return _strip_leading(rest).strip()
    return None


def is_wake(text: str, wake_words: tuple[str, ...] = WAKE_WORDS) -> bool:
    return split_wake(text, wake_words) is not None
