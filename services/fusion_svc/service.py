"""fusion_svc v1: 근거 토픽 → State Machine → `fusion/state`.

    device/state     ─┐  가열 장치 켜짐·세기, 가상 주방의 자체 차단 (kitchen_gw)
    sensor/reading   ─┤  가열 장치 온도
    vision/objects   ─┼▶ StateMachine ─▶ fusion/state {state, prev_state, evidence, risk}
    stt/text         ─┤  긴급어 (Guard 빠른 경로와 같은 판단)
    guard/decision   ─┘  허용된 EMERGENCY_STOP

- 근거가 들어온 시각은 이 서비스의 단조 시계로 잰다 (모든 서비스가 같은 보드 시계).
- `fusion/state`는 State나 risk가 바뀌면 바로, 아니면 1초마다 낸다 (판정 기준이 1초 단위).
  `prev_state`는 지금 State 직전의 (다른) State다. 시작한 뒤 바뀐 적이 없으면 지금 State와 같다.
- `session_id`는 이 서비스의 것이다 (여러 토픽의 근거를 묶어 만든 메시지라 이어 쓸 하나가 없다).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from common.bus import Bus
from common.messages import Envelope
from services.fusion_svc.state_machine import StateMachine

SOURCE = "fusion_svc"
TOPICS = ("device/state", "sensor/reading", "vision/objects", "stt/text", "guard/decision")
PUBLISH_PERIOD_S = 1.0

log = logging.getLogger(__name__)


class FusionService:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        on_state: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.session_id = session_id
        self.on_state = on_state
        self.clock = clock
        self.machine = StateMachine()
        self.published = 0
        self.changes = 0
        self._state: str | None = None
        self._prev_state: str | None = None
        self._risk: str | None = None
        self._last_publish: float | None = None
        self._last_heartbeat: float | None = None
        self._lock = threading.RLock()  # 버스 콜백(수신 스레드)과 주기 tick(메인)이 함께 부른다

    def start(self) -> None:
        for topic in TOPICS:
            self.bus.subscribe(topic, self.on_message)

    def on_message(self, msg: Envelope) -> None:
        with self._lock:
            try:
                self.machine.update(self.clock(), msg.type, msg.payload)
            except (KeyError, TypeError, ValueError) as exc:  # 필수 필드는 있지만 값이 이상함
                log.warning("%s 근거를 읽지 못해 버림: %s", msg.type, exc)
                return
            self._tick()  # 근거가 바뀌면 바로 판정 (위험을 1초 늦게 알리지 않게)

    def tick(self) -> None:
        """지금 State를 판정하고, 바뀌었거나 1초가 지났으면 발행한다."""
        with self._lock:
            self._tick()

    def _tick(self) -> None:
        now = self.clock()
        state = self.machine.state(now)
        risk = self.machine.risk(now, state)
        changed = state != self._state or risk != self._risk
        due = self._last_publish is None or now - self._last_publish >= PUBLISH_PERIOD_S
        if not (changed or due):
            return
        if state != self._state:
            self._prev_state = self._state if self._state is not None else state
            self._state = state
            self.changes += 1
        self._risk = risk
        payload = {
            "state": state,
            "prev_state": self._prev_state,
            "evidence": self.machine.evidence(now),
            "risk": risk,
        }
        out = Envelope.new("fusion/state", SOURCE, payload, self.session_id)
        self.bus.publish(out)
        self._last_publish = now
        self.published += 1
        if self.on_state and changed:
            self.on_state(out)

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
