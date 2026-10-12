"""safety_guard v0: 명령(`llm/function_call`) → 판정(`guard/decision`) → 제어(`control/command`).

- 지금 주방 상태는 `fusion/state`의 마지막 값을 쓴다. 받은 적이 없으면 "모름"(위험 상태처럼 판정).
- 긴급 빠른 경로(FUS-04): `stt/text`에서 긴급어를 찾으면 명령 해석을 기다리지 않고 바로 긴급 정지.
  뒤이어 명령 해석이 같은 긴급 정지를 보내면 두 번 실행하지 않는다.
- 확인 흐름: 결제 요청은 ASK로 묻고 CONFIRM_TIMEOUT_S 동안 대답을 기다린다.
  "네"(CONFIRM)면 결제 요청을 허용하고, "아니요"(DENY)·다른 명령·시간 초과면 버린다.
  기다리는 동안에는 호출어 없이 말한 "네"·"아니요"도 받는다
  (`stt/text`의 wake=false 문장을 규칙 파서로 읽어 CONFIRM·DENY일 때만).
- `control/command`는 이 서비스만 발행한다 (LLM 출력이 Guard를 건너뛰는 경로가 없게).
"""

from __future__ import annotations

import dataclasses
import logging
import time
from collections.abc import Callable
from typing import Any

from common.bus import Bus
from common.kitchen_link import command_for
from common.messages import Envelope
from services.llm_svc.rule_parser import parse
from services.safety_guard.emergency import is_emergency
from services.safety_guard.rules import ALLOW, ASK, REPLY_ACTIONS, STATES, Decision, judge

SOURCE = "safety_guard"
EMERGENCY_CALL = {"action": "EMERGENCY_STOP", "target": "all"}
FAST_PATH_REASON = "긴급 빠른 경로"
# 빠른 경로로 긴급 정지한 뒤 이 시간 안에 온 긴급 정지 명령은 같은 요청으로 본다
EMERGENCY_DEDUP_S = 3.0
# ASK로 물은 뒤 대답을 기다리는 시간 (v0 값 — 써 보고 조정한다)
CONFIRM_TIMEOUT_S = 10.0

log = logging.getLogger(__name__)


@dataclasses.dataclass
class Pending:
    """대답을 기다리는 질문."""

    call: dict[str, Any]
    session_id: str
    deadline: float


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
        self.pending: Pending | None = None
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
        text, wake = msg.payload["text"], msg.payload["wake"]
        if is_emergency(text, wake):
            self.counts["fast_path"] += 1
            self._last_emergency = self.clock()
            self.pending = None  # 긴급 정지하면 기다리던 질문(결제)은 버린다
            self._publish(dict(EMERGENCY_CALL), Decision(ALLOW, FAST_PATH_REASON), msg.session_id)
            return
        # 호출어가 있는 말은 명령 해석(llm_svc)을 거쳐 on_call로 온다
        if not wake and self._waiting():
            reply = parse(text)
            if reply["action"] in REPLY_ACTIONS:
                self._answer(reply, msg.session_id)

    def on_call(self, msg: Envelope) -> None:
        call = msg.payload["call"]
        action = call.get("action")
        if action == "EMERGENCY_STOP" and self._recent_emergency():
            self.counts["duplicate"] += 1  # 빠른 경로가 이미 처리한 같은 요청
            return
        if action in REPLY_ACTIONS and self._waiting():
            self._answer(call, msg.session_id)
            return
        # 다른 명령이 오면 기다리던 질문은 버린다 (나중의 "네"가 엉뚱하게 실행되지 않게)
        self.pending = None
        decision = judge(call, self.state)
        if decision.decision == ALLOW and action == "EMERGENCY_STOP":
            self._last_emergency = self.clock()
        if decision.decision == ASK:
            self.pending = Pending(call, msg.session_id, self.clock() + CONFIRM_TIMEOUT_S)
        self._publish(call, decision, msg.session_id)

    def _waiting(self) -> bool:
        if self.pending is not None and self.clock() > self.pending.deadline:
            self.pending = None  # 시간 초과
        return self.pending is not None

    def _answer(self, reply: dict[str, Any], session_id: str) -> None:
        """기다리던 질문에 대한 대답. 네 → 물었던 명령을 허용, 아니요 → 취소를 알림."""
        assert self.pending is not None
        asked, self.pending = self.pending.call, None
        if reply["action"] == "CONFIRM":
            self._publish(asked, Decision(ALLOW, ""), session_id)
        else:
            self._publish({"action": "DENY"}, Decision(ALLOW, ""), session_id)

    def _recent_emergency(self) -> bool:
        last = self._last_emergency
        return last is not None and self.clock() - last <= EMERGENCY_DEDUP_S

    def _publish(self, call: dict[str, Any], decision: Decision, session_id: str) -> None:
        payload = {"call": call, "decision": decision.decision, "reason": decision.reason}
        out = Envelope.new("guard/decision", SOURCE, payload, session_id)
        self.bus.publish(out)
        self.counts[decision.decision] += 1
        if decision.decision == ALLOW:
            # 장치를 바꾸는 Action만 제어 명령이 된다. 타이머 실행(끝나면 장치 끄기)과
            # 결제 실행(가상 결제 단말 연결, HW-23)은 v0에 없다.
            command = command_for(call, self.seq + 1)
            if command is not None:
                self.seq += 1
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
