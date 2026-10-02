"""음성 응답 문장 (STT-12): guard/decision · fusion/state → 읽어 줄 문장.

결정론적 템플릿만 쓴다. 숫자는 아라비아 숫자로 쓴다 (TTS가 더 정확히 읽음).
"""

from __future__ import annotations

from typing import Any

DEVICE_NAMES = {"hood": "후드", "burner_1": "1번 화구", "burner_2": "2번 화구", "all": "전체"}
LEVEL_NAMES = {1: "약", 2: "중", 3: "강"}
ASK_QUESTIONS = {
    "target": "어느 장치를 말씀하시는지 다시 말해 주세요.",
    "level": "세기를 약, 중, 강 중에서 말해 주세요.",
    "duration": "몇 분으로 맞출까요?",
}
TARGET_QUESTIONS = {
    "TURN_ON": "어느 장치를 켤까요?",
    "TURN_OFF": "어느 장치를 끌까요?",
    "SET_LEVEL": "어느 장치의 세기를 바꿀까요?",
    "SET_TIMER": "어느 장치에 타이머를 맞출까요?",
}
RISK_WARNINGS = {
    "warn": "주의하세요. 조리 상태를 확인해 주세요.",
    "danger": "위험 상황이에요. 불을 확인해 주세요.",
}


def _obj(word: str) -> str:
    """목적격 조사 을/를."""
    last = word[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("을" if has_final else "를")


def _duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return " ".join(p for p in (f"{m}분" if m else "", f"{s}초" if s else "") if p)


def describe(call: dict[str, Any]) -> str | None:
    """허용된 명령의 결과 문장."""
    action = call["action"]
    device = DEVICE_NAMES.get(call.get("target", ""), "")
    if action == "TURN_ON":
        return f"{_obj(device)} 켰습니다."
    if action == "TURN_OFF":
        return "모두 껐습니다." if call["target"] == "all" else f"{_obj(device)} 껐습니다."
    if action == "SET_LEVEL":
        return f"{device} 세기를 {LEVEL_NAMES[call['level']]}으로 바꿨습니다."
    if action == "SET_TIMER":
        when = _duration(call["duration_s"])
        if "target" in call:
            what = "모두" if call["target"] == "all" else _obj(device)
            return f"{when} 뒤에 {what} 끕니다."
        return f"{when} 타이머를 맞췄습니다."
    if action == "CANCEL_TIMER":
        return "타이머를 취소했습니다."
    if action == "EMERGENCY_STOP":
        return "긴급 정지했습니다. 모든 장치를 껐습니다."
    if action == "ASK_CLARIFY":
        if not call["missing"]:
            return "네, 말씀하세요."
        if call["missing"] == ["target"] and call["for_action"] in TARGET_QUESTIONS:
            return TARGET_QUESTIONS[call["for_action"]]
        return ASK_QUESTIONS[call["missing"][0]]
    if action == "UNSUPPORTED":
        return "그건 아직 할 수 없어요."
    if action in ("CHECK_STATUS", "CHECK_RISK"):
        return "상태 확인은 아직 준비 중이에요."  # 장치 상태·위험도를 읽어 주는 건 FUS-08 이후
    return None


def reply_for_decision(payload: dict[str, Any]) -> str | None:
    """guard/decision payload → 읽어 줄 문장."""
    call, decision = payload["call"], payload["decision"]
    if decision == "ALLOW":
        return describe(call)
    device = DEVICE_NAMES.get(call.get("target", ""), "")
    if decision == "REJECT":
        reason = payload.get("reason") or ""
        head = f"지금은 {_obj(device)} 제어할 수 없어요." if device else "지금은 할 수 없어요."
        return f"{head} {reason}".strip()
    if decision == "ASK":
        return f"정말 {_obj(device)} 제어할까요?" if device else "정말 할까요?"
    return None


class RiskWatcher:
    """fusion/state의 risk가 올라갈 때만 경고한다 (같은 위험을 반복해 말하지 않음)."""

    _ORDER = {"none": 0, "warn": 1, "danger": 2}

    def __init__(self) -> None:
        self.risk = "none"

    def update(self, payload: dict[str, Any]) -> str | None:
        risk = payload["risk"]
        rising = self._ORDER.get(risk, 0) > self._ORDER.get(self.risk, 0)
        self.risk = risk
        return RISK_WARNINGS.get(risk) if rising else None
