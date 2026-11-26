"""텍스트 기반 호출어 (docs/decisions/open-questions.md Q-08 v0).

받아쓴 문장이 호출어로 시작하면 명령으로 본다. 비교할 때 띄어쓰기·문장부호는 무시한다
(SenseVoice가 "자비스야"를 "자비 스야"로 받아쓴 사례가 있다). 첫 자음 오인식 변형도 호출로 본다.

2026-11-17 보드 실사용(#STT-14): 다급하게 "자비스 멈춰 자비스 멈춰"처럼 이어 말하면 첫 "자"가 잘려
"비 멈춰 자비스 멈춰"가 된다. 그래서 문장 중간이라도 **단어로 떨어진** 호출어가 있으면 마지막 호출어
뒤를 명령으로 본다 (문장 중간의 "자비스한테"처럼 다른 말에 붙은 것은 아니다).
"""

from __future__ import annotations

# 첫 자음 오인식 변형 (Q-08): SenseVoice가 "자"의 ㅈ을 ㄷ·ㅂ·ㅊ 등으로 받아쓴다.
# 사람 음성(2026-10-02, MacBook 마이크)에서 다비스·바비스, 합성 음성에서 차비스 확인 (#57).
# "서비스"처럼 흔한 말과 겹치지 않게 모음이 ㅏ인 첫 글자만 허용한다.
WAKE_INITIAL_VARIANTS = "자다바차짜사타"
# "자비스야"에서 '스'가 빠지거나 띄어진 형태 (spk01 val: "자비야", "자비 쓰야", #61)
WAKE_VOCATIVE_FORMS = ("자비야", "자비쓰야")
# 보드 핀마이크 실사용 출력 (2026-11-17, #STT-14): "저비스 1번하고 켜줘", "잡비스 …", "자이스 …"
WAKE_OTHER_FORMS = ("저비스", "잡비스", "자이스")
# 보드 USB 마이크 실사용 출력 (2026-11-24, #182): "자베스 1번 허국 해줘", "자베이스 후드 캐죠",
# "제페스 후드켜죠?", "자벳의 1번 화국회죠", "자 위스트켜죠"·"자 위스드 해죠"(2회).
# "자위스"는 띄어쓰기를 무시하고 비교하므로 "자, 위스키 …"처럼 일상 말도 호출로 잡힌다 — 알고 넣는다
# (사용자 요청, #182). 잘못 잡혀도 명령 부분이 장치·동작이 아니면 되묻기로 끝난다.
WAKE_BOARD_USB_FORMS = ("자베스", "자베이스", "제페스", "자벳의", "자위스")
WAKE_WORDS: tuple[str, ...] = (
    tuple(f"{c}비스" for c in WAKE_INITIAL_VARIANTS)
    + WAKE_VOCATIVE_FORMS
    + WAKE_OTHER_FORMS
    + WAKE_BOARD_USB_FORMS
)
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


def _after_wake(rest: str) -> str:
    for v in _VOCATIVES:
        after = rest[len(v) :]
        if rest.startswith(v) and (not after or _skippable(after[0])):
            rest = after
            break
    return _strip_leading(rest).strip()


def split_wake(text: str, wake_words: tuple[str, ...] = WAKE_WORDS) -> str | None:
    """호출어가 있으면 (마지막) 호출어 뒤의 명령 부분을, 없으면 None을 돌려준다.

    "자비스, 후드 켜 줘." → "후드 켜 줘."   "자비 스야 후드 켜 줘." → "후드 켜 줘."
    "자비스." → "" (호출만 함)              "비 멈춰 자비스 멈춰." → "멈춰."
    "저기 자비스 후드 켜 줘" → "후드 켜 줘"  "그 자비스한테 시켜" → None (중간 호출어는 단어일 때만)
    """
    for word in wake_words:
        end = _match(text, word)
        if end is not None:
            return _after_wake(text[end:])
    # 문장 중간: 앞이 띄어쓰기·문장부호이고 뒤도 끝·띄어쓰기·문장부호·호격 조사인 마지막 호출어
    found: int | None = None
    for start in range(1, len(text)):
        if not _skippable(text[start - 1]) or _skippable(text[start]):
            continue
        for word in wake_words:
            end = _match(text[start:], word)
            if end is None:
                continue
            rest = text[start + end :]
            if not rest or _skippable(rest[0]) or rest[0] in _VOCATIVES:
                found = start + end
            break
    return None if found is None else _after_wake(text[found:])


def is_wake(text: str, wake_words: tuple[str, ...] = WAKE_WORDS) -> bool:
    return split_wake(text, wake_words) is not None
