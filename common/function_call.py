"""Function Call(명령) 스키마 — LLM·규칙 파서 출력, Safety Guard 입력.

규격: docs/architecture/interfaces.md §3 (v0.2, LLM-13). 이 파일과 문서가 다르면 문서를 먼저 고친다.

두 가지 표현이 있다.
- 버스(JSON, dict): {"action": "SET_LEVEL", "target": "hood", "level": 3}
- LLM 출력(함수 토큰): <jarvis_3>(target=hood, level=3)<jarvis_end>
  값 자리의 `?`는 "말에 빠져 있음" → ASK_CLARIFY로 바뀐다 (SUDA 방식의 -1).
"""

from __future__ import annotations

import re
from typing import Any

# 개별 장치. 앞의 셋이 v0.1, 뒤의 다섯이 v0.2에서 추가됐다 (이름은 바꾸지 않고 덧붙인다)
DEVICES = ("hood", "burner_1", "burner_2", "fryer", "light", "aircon", "fan", "music")
TARGETS = (*DEVICES, "all")
TIMER_TARGETS = ("hood", "burner_1", "burner_2", "fryer", "all")  # 타이머로 끌 수 있는 것
LEVELS = (1, 2, 3)  # 약 / 중 / 강 (조명은 밝기, 음악은 음량)
MAX_DURATION_S = 3600  # 타이머 최대 60분

# 함수 토큰 번호 → Action (번호는 바꾸지 않는다. 학습 데이터·변환 모델이 이 번호를 쓴다)
ACTION_IDS: dict[int, str] = {
    1: "TURN_ON",
    2: "TURN_OFF",
    3: "SET_LEVEL",
    4: "SET_TIMER",
    5: "CANCEL_TIMER",
    6: "CHECK_STATUS",
    7: "CHECK_RISK",
    8: "EMERGENCY_STOP",
    9: "ASK_CLARIFY",
    10: "UNSUPPORTED",
    11: "CHECK_AMOUNT",  # 금액 확인 — 금액은 가상 결제 단말이 가진 값을 쓴다 (말로 받지 않는다)
    12: "REQUEST_PAYMENT",  # 결제 요청 — Safety Guard가 확인을 받은 뒤 실행한다
    13: "CONFIRM",  # "네" — 확인을 기다리는 질문에 대한 답
    14: "DENY",  # "아니요"
}
ACTIONS = tuple(ACTION_IDS.values())
V01_ACTIONS = ACTIONS[:10]  # 스키마 v0.1의 Action — LLM 데이터 v1이 다루는 범위
_ID_OF = {name: i for i, name in ACTION_IDS.items()}

# Action별 (필수 파라미터, 선택 파라미터). JSON 기준 이름.
PARAMS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "TURN_ON": (frozenset({"target"}), frozenset()),
    "TURN_OFF": (frozenset({"target"}), frozenset()),
    "SET_LEVEL": (frozenset({"target", "level"}), frozenset()),
    "SET_TIMER": (frozenset({"duration_s"}), frozenset({"target"})),
    "CANCEL_TIMER": (frozenset(), frozenset({"target"})),
    "CHECK_STATUS": (frozenset(), frozenset({"target"})),
    "CHECK_RISK": (frozenset(), frozenset()),
    "EMERGENCY_STOP": (frozenset({"target"}), frozenset()),  # target은 all 고정
    "ASK_CLARIFY": (frozenset({"for_action", "missing"}), frozenset()),
    "UNSUPPORTED": (frozenset(), frozenset()),
    "CHECK_AMOUNT": (frozenset(), frozenset()),
    "REQUEST_PAYMENT": (frozenset(), frozenset()),
    "CONFIRM": (frozenset(), frozenset()),
    "DENY": (frozenset(), frozenset()),
}
# Action별 target 허용값 (target을 받는 Action만)
_TARGETS_OF = {
    "TURN_ON": DEVICES,  # 한 번에 모두 켜기는 지원하지 않음
    "TURN_OFF": TARGETS,
    "SET_LEVEL": DEVICES,
    "SET_TIMER": TIMER_TARGETS,
    "CANCEL_TIMER": TIMER_TARGETS,
    "CHECK_STATUS": TARGETS,
    "EMERGENCY_STOP": ("all",),
}
MISSING_SLOTS = ("target", "level", "duration")  # ASK_CLARIFY가 되묻는 항목

START, END = "<jarvis_{}>", "<jarvis_end>"
_TOKEN = re.compile(r"^\s*<jarvis_(\d+)>\((.*)\)<jarvis_end>\s*$", re.DOTALL)
# LLM이 쓰는 키 → 버스 JSON 키 (시간은 분·초로 쓰고 초로 합친다)
_JSON_KEY = {"target": "target", "level": "level", "min": "duration_s", "sec": "duration_s"}


class FunctionCallError(ValueError):
    """스키마에 맞지 않는 명령."""


def validate(call: dict[str, Any]) -> None:
    """버스 JSON 명령이 interfaces §3에 맞는지 검사한다. 틀리면 FunctionCallError."""
    action = call.get("action")
    if action not in PARAMS:
        raise FunctionCallError(f"모르는 action: {action!r}")
    required, optional = PARAMS[action]
    keys = set(call) - {"action"}
    if missing := required - keys:
        raise FunctionCallError(f"{action}에 필수 파라미터 없음: {sorted(missing)}")
    if extra := keys - required - optional:
        raise FunctionCallError(f"{action}에 없는 파라미터: {sorted(extra)}")

    if "target" in call and call["target"] not in _TARGETS_OF[action]:
        raise FunctionCallError(
            f"{action}의 target은 {_TARGETS_OF[action]} 중 하나: {call['target']!r}"
        )
    if "level" in call and (type(call["level"]) is not int or call["level"] not in LEVELS):
        raise FunctionCallError(f"level은 {LEVELS} 중 하나: {call['level']!r}")
    if "duration_s" in call:
        d = call["duration_s"]
        if type(d) is not int or not 1 <= d <= MAX_DURATION_S:
            raise FunctionCallError(f"duration_s는 1~{MAX_DURATION_S} 정수: {d!r}")
    if action == "ASK_CLARIFY":
        fa, missing = call["for_action"], call["missing"]
        if fa is not None and fa not in PARAMS:
            raise FunctionCallError(f"for_action이 모르는 action: {fa!r}")
        if not isinstance(missing, list) or any(m not in MISSING_SLOTS for m in missing):
            raise FunctionCallError(f"missing은 {MISSING_SLOTS} 값의 목록: {missing!r}")
        if (fa is None) != (not missing):
            raise FunctionCallError(
                "for_action이 있으면 missing도 있어야 한다 (둘 다 없으면 의도 불명)"
            )


def _value(key: str, raw: str) -> str | int:
    if raw == "?" or key == "target":
        return raw
    if not raw.isdigit():
        raise FunctionCallError(f"{key} 값은 숫자 또는 ?: {raw!r}")
    return int(raw)


def parse_tokens(text: str) -> dict[str, Any]:
    """LLM 출력(함수 토큰)을 버스 JSON 명령으로 바꾼다. 틀리면 FunctionCallError.

    `?` 값이 있으면 ASK_CLARIFY {for_action, missing}으로 바꾼다.
    """
    m = _TOKEN.match(text)
    if not m:
        raise FunctionCallError(f"함수 토큰 형식이 아님: {text!r}")
    action = ACTION_IDS.get(int(m.group(1)))
    if action is None:
        raise FunctionCallError(f"모르는 함수 번호: jarvis_{m.group(1)}")

    args: dict[str, str | int] = {}
    body = m.group(2).strip()
    for part in body.split(",") if body else []:
        key, sep, raw = (s.strip() for s in part.partition("="))
        if not sep or key not in _JSON_KEY or key in args:
            raise FunctionCallError(f"인자 형식 오류: {part.strip()!r}")
        args[key] = _value(key, raw)

    required, optional = PARAMS[action]
    for key in args:
        if _JSON_KEY[key] not in required | optional:
            raise FunctionCallError(f"{action}에 없는 파라미터: {key}")

    missing = []
    if args.get("target") == "?":
        missing.append("target")
    if args.get("level") == "?":
        missing.append("level")
    if "?" in (args.get("min"), args.get("sec")):
        missing.append("duration")
    if missing:
        call: dict[str, Any] = {"action": "ASK_CLARIFY", "for_action": action, "missing": missing}
    elif action == "ASK_CLARIFY":
        call = {"action": "ASK_CLARIFY", "for_action": None, "missing": []}
    else:
        call = {"action": action}
        if "target" in args:
            call["target"] = args["target"]
        if "level" in args:
            call["level"] = args["level"]
        if "min" in args or "sec" in args:
            call["duration_s"] = int(args.get("min", 0)) * 60 + int(args.get("sec", 0))
        if action == "EMERGENCY_STOP":
            call.setdefault("target", "all")
    validate(call)
    return call


def to_tokens(call: dict[str, Any]) -> str:
    """버스 JSON 명령 → LLM 출력 형식 (학습 데이터의 정답 문자열 만들기용)."""
    validate(call)
    action = call["action"]
    if action == "ASK_CLARIFY":
        if call["for_action"] is None:
            return START.format(_ID_OF["ASK_CLARIFY"]) + "()" + END
        slots = {"target": "target=?", "level": "level=?", "duration": "min=?"}
        args = [slots[m] for m in call["missing"]]
        return START.format(_ID_OF[call["for_action"]]) + f"({', '.join(args)})" + END

    args = []
    if "target" in call and action != "EMERGENCY_STOP":
        args.append(f"target={call['target']}")
    if "level" in call:
        args.append(f"level={call['level']}")
    if "duration_s" in call:
        minutes, seconds = divmod(call["duration_s"], 60)
        if minutes:
            args.append(f"min={minutes}")
        if seconds:
            args.append(f"sec={seconds}")
    return START.format(_ID_OF[action]) + f"({', '.join(args)})" + END
