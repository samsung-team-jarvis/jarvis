"""받아쓴 문장 → 명령. llm_svc와 측정(bench.stt_eval·bench.llm_fallback)이 같은 경로를 쓴다.

호출어 분리(split_wake) → STT 오인식 사전(normalize) → (LLM →) 규칙 파서(parse).
LLM이 있으면 LLM 출력을 먼저 쓰고, 형식·스키마·범위 검증(parse_tokens)에 실패하면 규칙 파서로
대체한다 (decisions/2026-10-01-rule-parser-baseline.md, LLM-09).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from common.function_call import FunctionCallError, parse_tokens
from services.audio_svc.wake import split_wake
from services.llm_svc.rule_parser import compact, find_target, parse
from services.llm_svc.stt_fixes import normalize, numerals

# (명령 문장, context) → (LLM이 낸 문자열, 생성 토큰 수). Mac은 hf_engine, 보드는 LLM-08 뒤
Generate = Callable[[str, dict[str, Any]], tuple[str, int]]

_PUNCT = re.compile(r"[.,?!。]")  # 학습 문장에는 문장부호가 없다 (STT 출력에는 있다)


@dataclass
class Resolved:
    call: dict[str, Any]
    raw_text: str  # LLM을 쓰면 LLM 출력, 규칙 파서면 파서에 넣은 명령 문장
    valid: bool  # LLM 출력이 검증을 통과했는가 (LLM 없이 규칙 파서만 쓰면 True)
    fallback: bool  # 규칙 파서가 만든 명령인가
    tokens: int  # LLM이 생성한 토큰 수 (대체돼도 쓴 만큼 센다)


# LLM이 지원 외(UNSUPPORTED)라고 해도 규칙 파서가 이 동작 + 장치를 찾으면 규칙을 따른다
RULE_OVER_UNSUPPORTED = ("TURN_ON", "TURN_OFF", "SET_LEVEL", "SET_TIMER")
NEGATION = re.compile(r"지\s*마|지\s*말|말아|않|안\s*돼|하지")


def command_text(stt_text: str) -> str | None:
    """호출어가 있으면 파서에 넣을 명령 문장(오인식 사전·숫자 정규화 적용), 없으면 None."""
    command = split_wake(stt_text)
    return None if command is None else numerals(normalize(command))


def interpret(stt_text: str) -> dict[str, Any] | None:
    """호출어가 없으면 None (명령으로 처리하지 않음), 있으면 Function Call."""
    command = command_text(stt_text)
    return None if command is None else parse(command)


def llm_input(command: str) -> str:
    """LLM에 넣을 문장: 문장부호를 빼고 공백을 하나로."""
    return " ".join(_PUNCT.sub(" ", command).split())


def resolve(command: str, context: dict[str, Any], generate: Generate | None = None) -> Resolved:
    """명령 문장 → 명령. LLM 출력이 검증에 실패하면 규칙 파서 결과를 쓴다.

    호출어만 말한 경우(빈 문장)는 LLM에 넣지 않는다 — 규칙 파서가 의도 불명 되묻기를 낸다.
    """
    text = llm_input(command)
    if generate is None or not text:
        return Resolved(parse(command), command, valid=True, fallback=True, tokens=0)
    raw, tokens = generate(text, context)
    try:
        call = parse_tokens(raw)
    except FunctionCallError:
        return Resolved(parse(command), command, valid=False, fallback=True, tokens=tokens)
    if call["action"] == "UNSUPPORTED":
        # LLM은 지원 외라는데 규칙 파서가 장치와 동작을 분명히 찾으면 규칙을 따른다 (#STT-14).
        # 보드 실사용 "선풍기 틀어줘" → LLM 지원 외. 결정은 val로 했다 (METRICS)
        # 부정("끄지 마")은 규칙 파서가 반대로 읽어서 제외한다 (val 부정 8문장)
        rule = parse(command)
        if (
            rule["action"] in RULE_OVER_UNSUPPORTED
            and rule.get("target")
            and not NEGATION.search(command)
        ):
            return Resolved(rule, raw, valid=True, fallback=True, tokens=tokens)
    if (
        call["action"] == "TURN_OFF"
        and call.get("target") != "all"
        and find_target(compact(command)) == "all"
        and not NEGATION.search(command)
    ):
        # "전부 꺼 줘"인데 LLM이 직전 장치(context의 last_target)만 끈다 — 보드 시연 2026-11-25:
        # "튀김기 켜 줘" 바로 뒤 "전부 꺼죠" → TURN_OFF fryer (6번). 말에 전부·모두·전체가 있으면
        # 전체로 고친다. 더 많이 끄는 쪽이라 안전 쪽이다 (#182)
        all_off = {"action": "TURN_OFF", "target": "all"}
        return Resolved(all_off, raw, valid=True, fallback=True, tokens=tokens)
    return Resolved(call, raw, valid=True, fallback=False, tokens=tokens)
