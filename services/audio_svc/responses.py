"""음성 응답 문장 (STT-12·13): guard/decision · fusion/state → 읽어 줄 문장.

결정론적 템플릿만 쓴다. 숫자는 아라비아 숫자로 쓴다 (TTS가 더 정확히 읽음).
상태·위험 확인(CHECK_STATUS·CHECK_RISK)은 마지막으로 받은 `fusion/state`의 근거(interfaces §2.3)와
`device/state`(후드·조명 등 가열 장치가 아닌 장치)로 답한다. 오래된 상태로는 답하지 않는다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from services.safety_guard.auto_stop import REASON_PREFIX, UNATTENDED_GRACE_S

DEVICE_NAMES = {
    "hood": "후드",
    "burner_1": "1번 화구",
    "burner_2": "2번 화구",
    "fryer": "튀김기",
    "light": "조명",
    "aircon": "에어컨",
    "fan": "선풍기",
    "music": "음악",
    "all": "전체",
}
LEVEL_NAMES = {1: "약", 2: "중", 3: "강"}
# 세기를 다른 말로 부르는 장치: (무엇을, 1·2·3을 읽는 말)
LEVEL_PHRASES = {
    "light": ("밝기", {1: "어둡게", 2: "보통으로", 3: "밝게"}),
    "music": ("음량", {1: "작게", 2: "보통으로", 3: "크게"}),
}
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
HEATERS = ("burner_1", "burner_2", "fryer")
STATE_SENTENCES = {
    "IDLE": "지금은 가열 장치가 모두 꺼져 있어요.",
    "PREHEAT": "지금은 예열 중이에요.",
    "COOKING": "지금은 조리 중이에요.",
    "UNATTENDED": "가열 장치가 켜진 채 자리를 비운 상태예요.",
    "DANGER": "과열 위험 상태예요.",
    "SAFE_STOP": "안전 정지 상태예요.",
}
STATUS_STALE_S = 5.0  # fusion/state는 1초마다 온다 — 이보다 오래됐으면 지금 상태로 말하지 않는다
NO_STATUS = "상태 정보를 아직 받지 못했어요."
STALE_STATUS = "상태 정보가 끊겨서 지금 상태를 알 수 없어요."
HOT_C, DANGER_C, ABSENT_WARN_S = 200.0, 240.0, 10.0  # interfaces §2.3 risk 기준


def _obj(word: str) -> str:
    """목적격 조사 을/를."""
    last = word[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("을" if has_final else "를")


def _subj(word: str) -> str:
    """주격 조사 이/가."""
    last = word[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("이" if has_final else "가")


def _topic(word: str) -> str:
    """보조사 은/는."""
    last = word[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("은" if has_final else "는")


def _is(word: str) -> str:
    """서술격 조사: 받침이 있으면 "이에요", 없으면 "예요"."""
    last = word[-1]
    has_final = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("이에요" if has_final else "예요")


def _duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return " ".join(p for p in (f"{m}분" if m else "", f"{s}초" if s else "") if p)


def describe(call: dict[str, Any], status: KitchenStatus | None = None) -> str | None:
    """허용된 명령의 결과 문장. 상태·위험 확인은 `status`(마지막 fusion/state)로 답한다."""
    action = call["action"]
    device = DEVICE_NAMES.get(call.get("target", ""), "")
    if action == "TURN_ON":
        return f"{_obj(device)} 켰습니다."
    if action == "TURN_OFF":
        return "모두 껐습니다." if call["target"] == "all" else f"{_obj(device)} 껐습니다."
    if action == "SET_LEVEL":
        if call["target"] in LEVEL_PHRASES:
            what, words = LEVEL_PHRASES[call["target"]]
            return f"{device} {_obj(what)} {words[call['level']]} 바꿨습니다."
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
    if action == "CHECK_STATUS":
        return status.status(call.get("target")) if status else NO_STATUS
    if action == "CHECK_RISK":
        return status.risk() if status else NO_STATUS
    if action == "CHECK_AMOUNT":
        return "금액 확인은 아직 준비 중이에요."  # 가상 결제 단말의 금액을 받아 오는 연결이 생긴 뒤
    if action == "REQUEST_PAYMENT":
        return "결제를 요청했습니다."
    if action == "DENY":
        return "알겠습니다. 취소했습니다."
    return None  # CONFIRM: 확인받은 명령의 결과 문장이 따로 나온다


def reply_for_decision(payload: dict[str, Any], status: KitchenStatus | None = None) -> str | None:
    """guard/decision payload → 읽어 줄 문장."""
    call, decision = payload["call"], payload["decision"]
    device = DEVICE_NAMES.get(call.get("target", ""), "")
    reason = payload.get("reason") or ""
    if decision == "ALLOW" and reason.startswith(REASON_PREFIX):  # Guard의 자동 차단 (FUS-09)
        if "과열" in reason:
            return f"온도가 너무 높아 {_obj(device)} 껐습니다."
        if "방치" in reason:
            return f"자리를 오래 비우셔서 {_obj(device)} 껐습니다."
        return f"위험해서 {_obj(device)} 껐습니다."
    if decision == "ALLOW":
        return describe(call, status)
    if decision == "REJECT":
        head = f"지금은 {_obj(device)} 제어할 수 없어요." if device else "지금은 할 수 없어요."
        return f"{head} {reason}".strip()
    if decision == "ASK":
        if call["action"] == "REQUEST_PAYMENT":
            return "결제할까요?"
        return f"정말 {_obj(device)} 제어할까요?" if device else "정말 할까요?"
    return None


def _temp(value: float) -> str:
    return f"{value:.0f}도"


def _risk_reasons(payload: dict[str, Any]) -> list[str]:
    """`fusion/state`의 근거 → 위험·주의인 이유 (뜨거운 장치, 사람 없는 시간, 모르는 온도)."""
    evidence = payload.get("evidence") or {}
    heaters = evidence.get("heaters") or {}
    out = []
    for name in HEATERS:
        h = heaters.get(name) or {}
        t = h.get("temperature_c")
        if t is not None and t >= DANGER_C:
            out.append(f"{_subj(DEVICE_NAMES[name])} {_temp(t)}로 너무 뜨거워요.")
        elif t is not None and t >= HOT_C:
            out.append(f"{_subj(DEVICE_NAMES[name])} {_is(_temp(t))}.")
        elif h.get("on") and t is None:
            out.append(f"{DEVICE_NAMES[name]} 온도를 알 수 없어요.")
    absent = evidence.get("absent_s") or 0
    if absent >= ABSENT_WARN_S:
        out.append(f"사람 없이 {absent:.0f}초째 켜져 있어요.")
    if evidence.get("safe_stop"):
        out.append("안전 정지 중이에요.")
    return out


class KitchenStatus:
    """마지막 `fusion/state`와 `device/state`를 기억해 상태·위험 확인에 답한다 (STT-13)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.state: dict[str, Any] | None = None  # fusion/state payload
        self.state_at: float | None = None
        self.devices: dict[str, dict[str, Any]] = {}  # device/state의 devices

    def on_state(self, payload: dict[str, Any]) -> None:
        self.state, self.state_at = payload, self.clock()

    def on_devices(self, payload: dict[str, Any]) -> None:
        self.devices = dict(payload.get("devices") or {})

    def _fresh(self) -> str | None:
        """믿을 수 있는 상태가 없으면 그 이유 문장."""
        if self.state is None or self.state_at is None:
            return NO_STATUS
        if self.clock() - self.state_at > STATUS_STALE_S:
            return STALE_STATUS
        return None

    def _heater(self, name: str) -> dict[str, Any]:
        return ((self.state or {}).get("evidence") or {}).get("heaters", {}).get(name) or {}

    def _level(self, name: str) -> str:
        """켜진 장치의 세기 말: "강", 조명·음악은 세기 대신 "켜짐"."""
        level = (self._heater(name) if name in HEATERS else self.devices.get(name, {})).get("level")
        if name in LEVEL_PHRASES:
            return "켜짐"
        return LEVEL_NAMES.get(level, "켜짐")

    def _device_phrase(self, name: str) -> str | None:
        """켜진 장치 한 개: "1번 화구 강 182도", "후드 중", "조명 켜짐". 꺼졌으면 None."""
        dev = self._heater(name) if name in HEATERS else self.devices.get(name) or {}
        if not dev.get("on"):
            return None
        phrase = f"{DEVICE_NAMES[name]} {self._level(name)}"
        if name in HEATERS:
            t = dev.get("temperature_c")
            phrase += " 온도 모름" if t is None else f" {_temp(t)}"
        return phrase

    def status(self, target: str | None = None) -> str:
        if why := self._fresh():
            return why
        if target and target != "all":
            return self._one(target)
        order = [*HEATERS, *(n for n in DEVICE_NAMES if n not in HEATERS and n != "all")]
        on = [p for n in order if (p := self._device_phrase(n))]  # 가열 장치 먼저
        head = STATE_SENTENCES.get(self.state["state"], "")
        if not on:
            return "지금은 켜진 장치가 없어요."
        return f"{head} 켜진 장치는 {_is(', '.join(on))}."

    def _one(self, target: str) -> str:
        name = DEVICE_NAMES.get(target, target)
        if target in HEATERS:
            h = self._heater(target)
            t = h.get("temperature_c")
            if h.get("on"):
                temp = "온도는 알 수 없어요." if t is None else f"{_is(_temp(t))}."
                return f"{_topic(name)} 켜져 있어요. 세기 {self._level(target)}, {temp}"
            hot = f" 아직 {_temp(t)}라 뜨거워요." if t is not None and t >= 100 else ""
            return f"{_topic(name)} 꺼져 있어요.{hot}"
        if target not in self.devices:
            return f"{name} 상태를 아직 받지 못했어요."
        if not self.devices[target].get("on"):
            return f"{_topic(name)} 꺼져 있어요."
        if target in LEVEL_PHRASES:
            return f"{_topic(name)} 켜져 있어요."
        return f"{_topic(name)} 켜져 있어요. 세기 {_is(self._level(target))}."

    def risk(self) -> str:
        if why := self._fresh():
            return why
        level = self.state.get("risk", "none")
        reasons = " ".join(_risk_reasons(self.state))
        if level == "danger":
            return f"위험해요. {reasons}".strip()
        if level == "warn":
            return f"주의가 필요해요. {reasons}".strip()
        return "지금은 위험하지 않아요."


class RiskWatcher:
    """fusion/state의 risk가 올라갈 때(또는 위험의 종류가 바뀔 때)만 경고한다.

    같은 위험을 반복해 말하지 않는다. 경고는 State별로 무엇이 위험한지 말한다:
    DANGER는 어느 장치가 몇 도인지, UNATTENDED는 곧 자동으로 끈다는 것 (FUS-09 유예).
    """

    _ORDER = {"none": 0, "warn": 1, "danger": 2}

    def __init__(self) -> None:
        self.risk = "none"
        self.state: str | None = None

    def update(self, payload: dict[str, Any]) -> str | None:
        risk, state = payload["risk"], payload.get("state")
        rising = self._ORDER.get(risk, 0) > self._ORDER.get(self.risk, 0)
        changed_danger = risk == "danger" and self.risk == "danger" and state != self.state
        self.risk, self.state = risk, state
        if not (rising or changed_danger):
            return None
        return self._warning(risk, state, payload)

    @staticmethod
    def _warning(risk: str, state: str | None, payload: dict[str, Any]) -> str | None:
        reasons = _risk_reasons(payload)
        if risk == "danger" and state == "UNATTENDED":
            return (
                "가열 장치가 켜진 채 자리를 비우셨어요. "
                f"{UNATTENDED_GRACE_S:.0f}초 안에 돌아오지 않으면 불을 끕니다."
            )
        if risk == "danger" and state == "DANGER" and reasons:
            return f"위험해요. {reasons[0]}"
        if risk == "warn" and reasons:
            return f"주의하세요. {reasons[0]}"
        return RISK_WARNINGS.get(risk)
