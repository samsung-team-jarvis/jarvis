"""dashboard (UI-01): 버스의 상태·들은 말·판단 근거·경고 → `kitchen/overlay`.

가상 주방 화면에 겹쳐 띄울 정보를 모아 보낸다.

    fusion/state    ─┐  State·risk·근거(장치별 켜짐·온도, 사람)
    device/state    ─┤  상태 확인 응답 문장용 (audio_svc와 같은 문장)
    stt/text        ─┼▶ Overlay ─▶ kitchen/overlay (봉투 없는 JSON, 1초마다 + 바뀔 때)
    guard/decision  ─┤  응답 문장·판정·이유 (자동 차단 근거 포함)
    vision/objects  ─┘  AI가 본 화면 (사람 bbox)

규격: docs/architecture/interfaces.md §4.2 `kitchen/overlay`. 화면에 그리는 것은 Unity(UI-02)다.
문장은 audio_svc.responses를 그대로 쓴다 — 화면 글자와 음성이 같은 말을 한다.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from common import kitchen_link as link
from common.bus import Bus
from common.messages import Envelope
from services.audio_svc.responses import (
    NO_STATUS,
    STALE_STATUS,
    KitchenStatus,
    RiskWatcher,
    reply_for_decision,
)

SOURCE = "dashboard"
PERIOD_S = 1.0  # 바뀐 게 없어도 이 주기로 보낸다 (Unity가 중간에 붙어도 1초 안에 그린다)
HOLD_S = 10.0  # 들은 말·응답을 화면에 남겨 두는 시간
SEEN_S = 1.0  # 화면 인식 결과를 믿는 시간 (vision_svc는 3~5장/초)
STATE_STALE_S = (
    3.0  # fusion/state(1초마다)가 이보다 끊기면 상태 모름 (Safety Guard FUS-12와 같은 기준)
)
STATE_TEXT = {
    "IDLE": "대기",
    "PREHEAT": "예열 중",
    "COOKING": "조리 중",
    "UNATTENDED": "자리 비움",
    "DANGER": "과열 위험",
    "SAFE_STOP": "안전 정지",
}
UNKNOWN_TEXT = "상태 모름"

log = logging.getLogger(__name__)


class Overlay:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        on_overlay: Callable[[dict[str, Any]], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.session_id = session_id
        self.on_overlay = on_overlay
        self.clock = clock
        self.status = KitchenStatus(clock=clock)  # 상태 확인 응답 문장용
        self.published = 0
        self._state: dict[str, Any] | None = None
        self._state_at: float | None = None
        self._heard: tuple[str, float] | None = None
        self._decision: tuple[dict[str, Any], str | None, float] | None = None
        self._seen: tuple[list[dict[str, Any]], float] | None = None
        self._last: dict[str, Any] | None = None
        self._last_at: float | None = None
        self._last_heartbeat: float | None = None
        self._lock = threading.RLock()  # 버스 콜백(수신 스레드)과 주기 tick(메인)

    def start(self) -> None:
        handlers = {
            "fusion/state": self.on_state,
            "device/state": self.on_devices,
            "stt/text": self.on_speech,
            "guard/decision": self.on_decision,
            "vision/objects": self.on_vision,
        }
        for topic, handler in handlers.items():
            self.bus.subscribe(topic, handler)

    # ── 입력 ──────────────────────────────────────────────────────────

    def on_state(self, msg: Envelope) -> None:
        with self._lock:
            self._state, self._state_at = msg.payload, self.clock()
            self.status.on_state(msg.payload)
            self._tick()

    def on_devices(self, msg: Envelope) -> None:
        with self._lock:
            self.status.on_devices(msg.payload)

    def on_speech(self, msg: Envelope) -> None:
        if not msg.payload["wake"]:
            return  # 호출어 없는 말은 명령이 아니다 (혼잣말·손님과의 대화)
        with self._lock:
            self._heard = (msg.payload["text"], self.clock())
            self._tick()

    def on_decision(self, msg: Envelope) -> None:
        with self._lock:
            reply = reply_for_decision(msg.payload, self.status)
            self._decision = (msg.payload, reply, self.clock())
            self._tick()

    def on_vision(self, msg: Envelope) -> None:
        with self._lock:
            self._seen = (msg.payload["objects"], self.clock())

    # ── 출력 ──────────────────────────────────────────────────────────

    def build(self, now: float) -> dict[str, Any]:
        """지금 화면에 띄울 정보 (interfaces §4.2 `kitchen/overlay`)."""
        stale = self._state_at is None or now - self._state_at > STATE_STALE_S
        state = None if stale else self._state
        evidence = (state or {}).get("evidence") or {}
        risk = state["risk"] if state else "none"
        if stale:
            warning = NO_STATUS if self._state_at is None else STALE_STATUS
        elif risk in ("warn", "danger"):
            warning = RiskWatcher._warning(risk, state["state"], state)  # 음성 경고와 같은 문장
        else:
            warning = None

        heard = self._heard[0] if self._heard and now - self._heard[1] <= HOLD_S else None
        decision = self._decision if self._decision and now - self._decision[2] <= HOLD_S else None
        seen = self._seen[0] if self._seen and now - self._seen[1] <= SEEN_S else []
        return {
            "state": state["state"] if state else None,
            "state_text": STATE_TEXT.get(state["state"], UNKNOWN_TEXT) if state else UNKNOWN_TEXT,
            "risk": risk,
            "heaters": evidence.get("heaters") or {},
            "person": evidence.get("person"),
            "absent_s": evidence.get("absent_s") or 0.0,
            "heard": heard,
            "reply": decision[1] if decision else None,
            "decision": decision[0]["decision"] if decision else None,
            "reason": (decision[0]["reason"] or None) if decision else None,
            "warning": warning,
            "seen": [{k: o[k] for k in ("cls", "conf", "bbox")} for o in seen],
            "stale": stale,
        }

    def tick(self) -> None:
        with self._lock:
            self._tick()

    def _tick(self) -> None:
        now = self.clock()
        overlay = self.build(now)
        due = self._last_at is None or now - self._last_at >= PERIOD_S
        if overlay == self._last and not due:
            return
        self.bus.publish_raw(link.TOPIC_OVERLAY, link.encode(overlay))
        if self.on_overlay and overlay != self._last:
            self.on_overlay(overlay)
        self._last, self._last_at = overlay, now
        self.published += 1

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
