"""safety_guard v0: 명령(`llm/function_call`) → 판정(`guard/decision`) → 제어(`control/command`).

- 지금 주방 상태는 `fusion/state`의 마지막 값을 쓴다. 받은 적이 없으면 "모름"(위험 상태처럼 판정).
- 긴급 빠른 경로(FUS-04): `stt/text`에서 긴급어를 찾으면 명령 해석을 기다리지 않고 바로 긴급 정지.
  뒤이어 명령 해석이 같은 긴급 정지를 보내면 두 번 실행하지 않는다.
- `control/command`는 이 서비스만 발행한다 (LLM 출력이 Guard를 건너뛰는 경로가 없게).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from common.bus import Bus
from common.messages import Envelope
from services.safety_guard.emergency import is_emergency
from services.safety_guard.rules import ALLOW, STATES, Decision, judge

SOURCE = "safety_guard"
EMERGENCY_CALL = {"action": "EMERGENCY_STOP", "target": "all"}
FAST_PATH_REASON = "긴급 빠른 경로"
# 빠른 경로로 긴급 정지한 뒤 이 시간 안에 온 긴급 정지 명령은 같은 요청으로 본다
EMERGENCY_DEDUP_S = 3.0
# 제어 명령으로 바뀌는 Action. 나머지(확인·타이머·되묻기·지원 외)는 장치를 움직이지 않는다.
# 타이머 실행(끝나면 장치 끄기)은 v0에 없다 — 타이머 담당을 정한 뒤 붙인다.
CONTROL_ACTIONS = frozenset({"TURN_ON", "TURN_OFF", "SET_LEVEL", "EMERGENCY_STOP"})

log = logging.getLogger(__name__)


def to_command(call: dict[str, Any], seq: int) -> dict[str, Any]:
    """허용된 명령 → `control/command` payload. value는 세기(켜기는 1, 끄기·정지는 0)."""
    action = call["action"]
    value = {"TURN_ON": 1, "SET_LEVEL": call.get("level")}.get(action, 0)
    return {"seq": seq, "cmd": action, "target": call["target"], "value": value}


class SafetyGuard:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        assume_state: str | None = None,
        on_decision: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        # heartbeat용. 판정·제어는 받은 메시지의 session_id를 이어 쓴다
        self.session_id = session_id
        self.state: str | None = assume_state  # 개발용 가정 상태 (상황 인식 전). 운영에서는 None
        self.on_decision = on_decision
        self.clock = clock
        self.seq = 0
        self.counts = {"ALLOW": 0, "REJECT": 0, "ASK": 0, "fast_path": 0, "duplicate": 0}
        self._last_emergency: float | None = None
        self._last_heartbeat: float | None = None

    def start(self) -> None:
        self.bus.subscribe("fusion/state", self.on_state)
        self.bus.subscribe("stt/text", self.on_speech)
        self.bus.subscribe("llm/function_call", self.on_call)

    def on_state(self, msg: Envelope) -> None:
        state = msg.payload["state"]
        if state not in STATES:
            log.warning("모르는 State 무시: %r", state)
            return
        self.state = state

    def on_speech(self, msg: Envelope) -> None:
        if not is_emergency(msg.payload["text"], msg.payload["wake"]):
            return
        self.counts["fast_path"] += 1
        self._last_emergency = self.clock()
        self._publish(dict(EMERGENCY_CALL), Decision(ALLOW, FAST_PATH_REASON), msg.session_id)

    def on_call(self, msg: Envelope) -> None:
        call = msg.payload["call"]
        if call.get("action") == "EMERGENCY_STOP" and self._recent_emergency():
            self.counts["duplicate"] += 1  # 빠른 경로가 이미 처리한 같은 요청
            return
        decision = judge(call, self.state)
        if decision.decision == ALLOW and call.get("action") == "EMERGENCY_STOP":
            self._last_emergency = self.clock()
        self._publish(call, decision, msg.session_id)

    def _recent_emergency(self) -> bool:
        last = self._last_emergency
        return last is not None and self.clock() - last <= EMERGENCY_DEDUP_S

    def _publish(self, call: dict[str, Any], decision: Decision, session_id: str) -> None:
        payload = {"call": call, "decision": decision.decision, "reason": decision.reason}
        out = Envelope.new("guard/decision", SOURCE, payload, session_id)
        self.bus.publish(out)
        self.counts[decision.decision] += 1
        if decision.decision == ALLOW and call.get("action") in CONTROL_ACTIONS:
            self.seq += 1
            command = to_command(call, self.seq)
            self.bus.publish(Envelope.new("control/command", SOURCE, command, session_id))
        if self.on_decision:
            self.on_decision(out)

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
