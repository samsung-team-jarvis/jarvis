"""받아쓴 문장 → 명령. llm_svc와 측정 스크립트(bench.stt_eval)가 같은 경로를 쓴다.

호출어 분리(split_wake) → STT 오인식 사전(normalize) → 규칙 파서(parse).
"""

from __future__ import annotations

from typing import Any

from services.audio_svc.wake import split_wake
from services.llm_svc.rule_parser import parse
from services.llm_svc.stt_fixes import normalize


def command_text(stt_text: str) -> str | None:
    """호출어가 있으면 파서에 넣을 명령 문장(오인식 사전 적용), 없으면 None."""
    command = split_wake(stt_text)
    return None if command is None else normalize(command)


def interpret(stt_text: str) -> dict[str, Any] | None:
    """호출어가 없으면 None (명령으로 처리하지 않음), 있으면 Function Call."""
    command = command_text(stt_text)
    return None if command is None else parse(command)
