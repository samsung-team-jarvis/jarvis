"""규칙 기반 파서 (FUS-02, 스키마 v0.2): 호출어 뒤 명령 문장 → Function Call (interfaces §3).

키워드 규칙만 쓴다. LLM이 생기면 LLM 출력 검증 실패 시 대체 경로이자 비교 기준선이다
(docs/decisions/2026-10-01-rule-parser-baseline.md).

판단 순서 (앞에서 정해지면 끝):
  1. 빈 문장(호출어만)            → ASK_CLARIFY (의도 불명)
  2. "네"·"아니요"만 말함          → CONFIRM / DENY
  3. 긴급어 (타이머 이야기가 아닐 때) → EMERGENCY_STOP
     (조명·에어컨·선풍기·음악을 멈추라는 말이면 그 장치의 TURN_OFF)
  4. 결제                        → CHECK_AMOUNT (금액을 물음) / REQUEST_PAYMENT
  5. 타이머                      → CANCEL_TIMER / SET_TIMER / 시간 되묻기
  6. 위험 확인 → CHECK_RISK,  7. 상태 확인 → CHECK_STATUS
  8. 세기 → SET_LEVEL,  9. 켜기/끄기 → TURN_ON / TURN_OFF
  10. 장치만 말함 → ASK_CLARIFY (의도 불명),  그 외 → UNSUPPORTED
필요한 장치가 빠졌으면 ASK_CLARIFY {for_action, missing: ["target"]}.
"""

from __future__ import annotations

import re
from typing import Any

from common.function_call import DEVICES, MAX_DURATION_S, TARGETS, TIMER_TARGETS, validate

# 비교는 띄어쓰기·문장부호를 지운 문장으로 한다 ("2 화국 꺼줘." → "2화국꺼줘")
_NOT_WORD = re.compile(r"[^0-9A-Za-z가-힣]")

EMERGENCY = re.compile(r"긴급|비상|정지|멈춰|멈춰줘|그만|스톱|스탑")
TIMER = re.compile(r"타이머|알람")
TIMER_LATER = re.compile(
    r"뒤에|뒤|후에|후|있다가|이따가|지나면|두고"
)  # "N분만 켜 두고 꺼" (train 근거)
TIMER_CANCEL = re.compile(r"취소|꺼|끄|그만|멈춰|정지|없애|지워")
RISK = re.compile(r"위험|안전해|안전한")
STATUS = re.compile(r"(켜져|꺼져)있|상태")
STATUS_WITH_DEVICE = re.compile(
    r"어때|확인|어떻게됐"
)  # 장치 이름과 같이 나올 때만 ("날씨 어때"는 아님)
# 조명은 밝기(어둡게·밝게), 음악은 음량(작게·크게)으로 말한다 — 모두 세기 1~3
LEVEL_WORDS = [
    (re.compile(r"세게|강하게|강으로|강하|최대|제일세|밝게|환하게|크게"), 3),
    (re.compile(r"중간|보통|중으로"), 2),
    (re.compile(r"약하게|약으로|약하|최소|살살|약불|어둡게|작게|조용히"), 1),
]
LEVEL_NUMBER = re.compile(r"([1-3]|일|이|삼|한|두|세)단")
LEVEL_RELATIVE = re.compile(r"더|올려|높여|줄여|낮춰|내려|키워")
TURN_ON = re.compile(r"켜|틀어|작동|돌려|재생")
TURN_OFF = re.compile(r"꺼|끄|중지")
YES = re.compile(r"(네|예|응|그래|맞아|좋아|오케이|확인)+요?")
NO = re.compile(r"아니|아니요|아니오|아니야|아냐|싫어|하지마|안해|취소|취소해|취소해줘|됐어")
# "계산"은 문장 맨 앞에 올 때만 결제로 본다 ("칼로리 계산해 줘"는 결제가 아니다)
PAYMENT = re.compile(r"결제|^(?:손님|카드로|현금으로)?계산")
AMOUNT = re.compile(r"금액|가격|합계|총액|얼마(?!나)|얼마나?나왔")
PAYMENT_CANCEL = re.compile(r"취소|하지마|안해|말고")

HOOD = re.compile(r"후드|환풍기|환기|팬")  # 환풍기는 후드와 같은 장치다
FRYER = re.compile(r"튀김기|프라이어")
LIGHT = re.compile(r"조명|전등|형광등|불빛|라이트")
AIRCON = re.compile(r"에어컨|에어콘|냉방")
FAN = re.compile(r"선풍기")
MUSIC = re.compile(r"음악|노래|뮤직|볼륨|음량|소리")
# 긴급어("멈춰", "정지")와 같이 나와도 긴급 정지가 아니라 그 장치를 끄는 것으로 보는 장치
NOT_URGENT = ("light", "aircon", "fan", "music")
# "화국"은 SenseVoice가 "화구"를 받아쓴 실제 출력 (Mac, 합성 음성 — audio_svc README)
BURNER_WORD = r"(?:화구|화국|버너|가스|불)"
BURNER_NUMBERED = re.compile(
    rf"(\d|일|이|첫|한|두)(?:번째|번)?{BURNER_WORD}|{BURNER_WORD}(\d|일|이)번?"
)
BURNER = re.compile(BURNER_WORD)
ALL = re.compile(r"전부|모두|전체|싹|다(?=꺼|끄|켜|틀)")

_NUM_WORD = {"1": 1, "일": 1, "첫": 1, "한": 1, "2": 2, "이": 2, "두": 2, "3": 3, "삼": 3, "세": 3}

# 시간: 숫자 또는 한글 숫자 + 분/초. "1분 반" = 90초
_SINO = "일이삼사오육칠팔구"
_NATIVE = {
    "한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8,
    "아홉": 9, "열": 10, "스무": 20, "서른": 30, "마흔": 40, "쉰": 50,
}  # fmt: skip
_TENS = "열|스무|서른|마흔|쉰"
_ONES = "한|두|세|네|다섯|여섯|일곱|여덟|아홉"
_NUMBER = rf"(\d+|[{_SINO}십]+|(?:{_TENS})?(?:{_ONES})|{_TENS})"
DURATION = re.compile(rf"{_NUMBER}(분|초)(반)?")


def compact(text: str) -> str:
    return _NOT_WORD.sub("", text)


def korean_number(word: str) -> int | None:
    """'3', '삼십오', '열다섯', '스무' 같은 수 표현을 정수로. 모르면 None."""
    if word.isdigit():
        return int(word)
    if all(ch in _SINO + "십" for ch in word):  # 한자어 수: 이십오, 십, 삼십
        if "십" not in word:
            return _SINO.index(word) + 1 if len(word) == 1 else None
        tens, _, ones = word.rpartition("십")
        if len(tens) > 1 or len(ones) > 1 or "십" in tens:
            return None  # "구이십"처럼 앞 글자가 붙은 경우 — 호출한 쪽에서 앞 글자를 떼고 다시
        t = _SINO.index(tens) + 1 if tens else 1
        o = _SINO.index(ones) + 1 if ones else 0
        return t * 10 + o
    for tens_word in ("열", "스무", "서른", "마흔", "쉰"):  # 고유어 수: 열다섯, 스무, 서른두
        if word.startswith(tens_word):
            rest = word[len(tens_word) :]
            return _NATIVE[tens_word] + (_NATIVE.get(rest, 0) if rest else 0)
    return _NATIVE.get(word)


def duration_s(text: str) -> int | None:
    """문장 속 시간 표현의 합(초). 없으면 None. 예: '3분30초' → 210, '1분반' → 90."""
    total, found = 0, False
    for num, unit, half in DURATION.findall(text):
        # 띄어쓰기를 지운 문장에서는 "화구 이십 분"의 '구'가 숫자에 붙는다 ("구이십")
        # → 앞 글자를 하나씩 떼며 읽을 수 있는 가장 긴 수를 쓴다
        n = next((v for k in range(len(num)) if (v := korean_number(num[k:])) is not None), None)
        if n is None:
            continue
        found = True
        total += n * 60 if unit == "분" else n
        if half and unit == "분":
            total += 30
    return total if found else None


def find_target(text: str) -> str | None:
    """장치 이름. 화구인데 번호가 없거나 없는 번호면 '?' (되물어야 함)."""
    if ALL.search(text):
        return "all"
    # 조명은 화구보다 먼저 본다 ("불빛"의 '불'이 화구로 읽히지 않게)
    for pattern, name in (
        (LIGHT, "light"),
        (FRYER, "fryer"),
        (AIRCON, "aircon"),
        (FAN, "fan"),
        (MUSIC, "music"),
        (HOOD, "hood"),
    ):
        if pattern.search(text):
            return name
    m = BURNER_NUMBERED.search(text)
    if m:
        n = _NUM_WORD.get(m.group(1) or m.group(2))
        return f"burner_{n}" if f"burner_{n}" in DEVICES else "?"
    if BURNER.search(text):
        return "?"
    return None


def find_level(text: str) -> int | str | None:
    """세기 1~3, 상대 조절("더", "줄여")이면 '?', 세기 표현이 없으면 None."""
    m = LEVEL_NUMBER.search(text)
    if m:
        return _NUM_WORD.get(m.group(1))
    for pattern, level in LEVEL_WORDS:
        if pattern.search(text):
            return level
    if LEVEL_RELATIVE.search(text):
        return "?"
    return None


def _ask(for_action: str | None, *missing: str) -> dict[str, Any]:
    return {"action": "ASK_CLARIFY", "for_action": for_action, "missing": list(missing)}


def _with_target(action: str, target: str | None, allowed: tuple[str, ...]) -> dict[str, Any]:
    if target is None or target == "?" or target not in allowed:
        return _ask(action, "target")
    return {"action": action, "target": target}


def parse(command: str) -> dict[str, Any]:
    """호출어를 뺀 명령 문장 → Function Call (interfaces §3, validate 통과 보장)."""
    call = _parse(compact(command))
    validate(call)
    return call


def _parse(text: str) -> dict[str, Any]:
    if not text:
        return _ask(None)
    if YES.fullmatch(text):
        return {"action": "CONFIRM"}
    if NO.fullmatch(text):
        return {"action": "DENY"}

    timer = bool(TIMER.search(text))
    target = find_target(text)
    if EMERGENCY.search(text) and not timer:
        if target in NOT_URGENT:  # "음악 멈춰", "선풍기 정지"
            return {"action": "TURN_OFF", "target": target}
        return {"action": "EMERGENCY_STOP", "target": "all"}
    if not timer and (PAYMENT.search(text) or AMOUNT.search(text)):
        if PAYMENT_CANCEL.search(text):  # "결제 취소", "결제하지 마"
            return {"action": "DENY"}
        return {"action": "CHECK_AMOUNT" if AMOUNT.search(text) else "REQUEST_PAYMENT"}

    seconds = duration_s(text)
    if timer or (seconds is not None and TIMER_LATER.search(text)):
        if target not in (None, "?") and target not in TIMER_TARGETS:
            return {"action": "UNSUPPORTED"}  # 조명·에어컨·선풍기·음악에는 타이머가 없다
        if timer and TIMER_CANCEL.search(text) and seconds is None:
            call: dict[str, Any] = {"action": "CANCEL_TIMER"}
            if target not in (None, "?"):
                call["target"] = target
            return call
        if seconds is None or not 1 <= seconds <= MAX_DURATION_S:
            return _ask("SET_TIMER", "duration")  # 시간이 없거나 범위 밖(최대 60분)이면 되묻기
        call = {"action": "SET_TIMER", "duration_s": seconds}
        if target == "?":
            return _ask("SET_TIMER", "target")
        if target is not None:
            call["target"] = target
        return call

    if RISK.search(text):
        return {"action": "CHECK_RISK"}
    if STATUS.search(text) or (target is not None and STATUS_WITH_DEVICE.search(text)):
        call = {"action": "CHECK_STATUS"}
        if target not in (None, "?"):
            call["target"] = target
        return call

    level = find_level(text)
    if level is not None and target is not None:
        if target in ("?", "all"):
            return _ask("SET_LEVEL", "target")
        if level == "?":
            return _ask("SET_LEVEL", "level")
        return {"action": "SET_LEVEL", "target": target, "level": level}

    if TURN_OFF.search(text):
        return _with_target("TURN_OFF", target, TARGETS)
    if TURN_ON.search(text):
        return _with_target("TURN_ON", target, DEVICES)
    if level is not None:  # "세게 해 줘"처럼 장치 없이 세기만
        return _ask("SET_LEVEL", "target")
    if target is not None:  # "후드"처럼 장치만
        return _ask(None)
    return {"action": "UNSUPPORTED"}
