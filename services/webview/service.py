"""webview (UI-03): 버스 → 브라우저 시연 화면 정보.

Unity 가상 주방(UI-02)이 없어도 보드에서 일어나는 일을 보여 주는 읽기 전용 화면이다.

    stt/text           ─┐  들은 말 · 받아쓰기 시간 · 말 끝 시각
    llm/function_call  ─┤  모델 출력(SUDA 함수 토큰) · 생성 시간
    guard/decision     ─┼▶ Feed ─▶ snapshot() ─▶ HTTP /view.json · /events (SSE)
    control/result     ─┤  가상 주방 확인 시간 → 말 끝 → 장치 확인 전체 시간
    device/state       ─┤  장치 8종
    fusion/state       ─┤  상황 인식 상태 · 가열 장치 온도 · 사람
    system/heartbeat   ─┤  살아 있는 서비스
    audio/level        ─┘  마이크 테스트 음량 (UI-04)

한 번의 말(또는 자동 차단)을 "턴" 하나로 묶는다. 응답 문장·경고 문장은 audio_svc.responses를
그대로 쓴다 — 화면 글자와 음성이 같은 말을 한다. 발행하는 것은 heartbeat와, 테스트 버튼을 눌렀을
때의 `audio/test`(마이크·스피커 테스트 요청, UI-04)뿐이다 — 장치를 제어하지 않는다.
"""

from __future__ import annotations

import pathlib
import platform
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from common.bus import Bus
from common.messages import Envelope
from services.audio_svc.responses import KitchenStatus, RiskWatcher, reply_for_decision
from services.audio_svc.wake import split_wake
from services.safety_guard.auto_stop import REASON_PREFIX
from services.safety_guard.emergency import is_emergency
from services.safety_guard.service import FAST_PATH_REASON, STATE_STALE_S

SOURCE = "webview"
TURN_S = 15.0  # 말 → 명령 → 판정 → 확인을 한 턴으로 묶는 시간
ALIVE_S = 3.0  # heartbeat(1초)가 이보다 오래 없으면 멈춘 서비스로 본다
LOG_SIZE = 8
TEST_KINDS = ("mic", "speaker")
HEARD_DBFS = -35.0  # 마이크 테스트에서 이보다 큰 소리가 한 번이라도 들어오면 "소리 들어옴"
# 근거: 보드 USB 마이크 시연(2026-11-24)에서 말소리 구간 -11~-34 dBFS, 잡음 -38~-60 dBFS (0.5초 RMS)
STATE_TEXT = {
    "IDLE": "대기",
    "PREHEAT": "예열 중",
    "COOKING": "조리 중",
    "UNATTENDED": "자리 비움",
    "DANGER": "과열 위험",
    "SAFE_STOP": "안전 정지",
}


def device_label() -> str:
    """실행 기기 이름. 보드면 device tree의 모델명, 아니면 OS·CPU와 '참고값'."""
    model = pathlib.Path("/proc/device-tree/model")
    if model.exists():
        name = model.read_bytes().rstrip(b"\0").decode(errors="replace")
        if "rk3588" in name.lower() or "orange pi" in name.lower():
            return f"{name} · 오프라인"
    return f"{platform.system()} {platform.machine()} · 참고값 (보드 아님)"


def _ms(later: float, earlier: float | None) -> float | None:
    return None if earlier is None else round((later - earlier) * 1000, 1)


class Feed:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        device: str = "",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.device = device  # 화면 머리의 실행 기기 표시 (보드인지 노트북 참고값인지)
        self.session_id = session_id
        self.clock = clock
        self.status = KitchenStatus(clock=clock)  # 상태 확인 응답 문장용
        self.turn: dict[str, Any] | None = None
        self.turns = 0
        self.devices: dict[str, Any] = {}
        self.safe_stop = False
        self.state: dict[str, Any] | None = None
        self.state_at: float | None = None
        self.alive: dict[str, float] = {}
        self.log: deque[dict[str, Any]] = deque(maxlen=LOG_SIZE)
        self.version = 0
        self.changed = threading.Condition()
        self._lock = threading.RLock()
        self._last_heartbeat: float | None = None
        self.mic: dict[str, Any] | None = None  # 마이크 테스트 (UI-04)
        self.speaker_at: float | None = None  # 스피커 테스트를 요청한 시각

    def start(self) -> None:
        handlers = {
            "stt/text": self.on_speech,
            "llm/function_call": self.on_call,
            "guard/decision": self.on_decision,
            "control/result": self.on_result,
            "device/state": self.on_devices,
            "fusion/state": self.on_state,
            "system/heartbeat": self.on_heartbeat,
            "audio/level": self.on_level,
        }
        for topic, handler in handlers.items():
            self.bus.subscribe(topic, handler)

    # ── 입력 ──────────────────────────────────────────────────────────

    def on_speech(self, msg: Envelope) -> None:
        p = msg.payload
        text, wake = p["text"], p["wake"]
        fast = is_emergency(text, wake)
        with self._lock:
            # 호출어 없는 말은 긴급어이거나, 물어본 질문("결제할까요?")에 대한 대답일 때만 보인다
            if not (wake or fast or self._asked()):
                return
            command = (split_wake(text) or text) if wake else text
            self._new_turn(
                "fast" if fast else "voice" if wake else "reply",
                said=text,
                command=command,
                wake=wake,
                audio_ms=p["audio_ms"],
                stt_ms=p["stt_ms"],
                speech_end=p["speech_end_mono"],
                publish_ms=_ms(msg.mono, p["speech_end_mono"]),
            )
            self._bump()

    def on_call(self, msg: Envelope) -> None:
        p = msg.payload
        with self._lock:
            turn = self._open_turn()
            if turn is None or turn["kind"] == "fast" or "raw_text" in turn:
                return  # 빠른 경로가 이미 처리한 긴급 정지의 LLM 결과 등
            turn.update(
                raw_text=p["raw_text"],
                call=p["call"],
                valid=p["valid"],
                fallback=p["fallback"],
                gen_ms=p["gen_ms"],
            )
            self._bump()

    def on_decision(self, msg: Envelope) -> None:
        p = msg.payload
        reason = p["reason"] or ""
        with self._lock:
            turn = self._open_turn()
            if reason.startswith(REASON_PREFIX):
                turn = self._new_turn("auto", said=None, command=None)
            elif turn is None or "decision" in turn:
                turn = self._new_turn("other", said=None, command=None)
            elif reason == FAST_PATH_REASON:
                turn["kind"] = "fast"
            turn.update(
                call=turn.get("call") or p["call"],
                decided_call=p["call"],
                decision=p["decision"],
                reason=reason or None,
                reply=reply_for_decision(p, self.status),
                decided_at=msg.mono,
            )
            self.log.append(
                {
                    "at": time.strftime("%H:%M:%S", time.localtime(msg.ts)),
                    "kind": turn["kind"],
                    "said": turn["command"],
                    "decision": p["decision"],
                    "reply": turn["reply"],
                }
            )
            self._bump()

    def on_result(self, msg: Envelope) -> None:
        p = msg.payload
        with self._lock:
            turn = self._open_turn()
            if turn is None or turn.get("decision") != "ALLOW" or "rtt_ms" in turn:
                return
            turn.update(
                ok=p["ok"],
                retries=p["retries"],
                rtt_ms=p["rtt_ms"],
                e2e_ms=_ms(msg.mono, turn.get("speech_end")),
            )
            self._bump()

    def on_devices(self, msg: Envelope) -> None:
        with self._lock:
            self.status.on_devices(msg.payload)
            self.devices = msg.payload["devices"]
            self.safe_stop = bool(msg.payload.get("safe_stop"))
            self._bump()

    def on_state(self, msg: Envelope) -> None:
        with self._lock:
            self.status.on_state(msg.payload)
            self.state, self.state_at = msg.payload, self.clock()
            self._bump()

    def on_heartbeat(self, msg: Envelope) -> None:
        with self._lock:
            self.alive[msg.source] = self.clock()

    def on_level(self, msg: Envelope) -> None:
        p = msg.payload
        with self._lock:
            self.mic = {
                "dbfs": p["dbfs"],
                "peak_dbfs": p["peak_dbfs"],
                "remaining_s": p["remaining_s"],
                "heard": p["peak_dbfs"] >= HEARD_DBFS,
                "waiting": False,
            }
            self._bump()

    # ── 버튼 (UI-04) ──────────────────────────────────────────────────

    def reset(self) -> None:
        """화면의 현재 턴과 최근 기록을 비운다 (장치·상황 인식 상태는 버스에서 다시 오므로 둔다)."""
        with self._lock:
            self.turn = None
            self.log.clear()
            self.mic = None
            self.speaker_at = None
            self._bump()

    def request_test(self, kind: str) -> None:
        """마이크·스피커 테스트를 audio_svc에 요청한다 (audio/test)."""
        if kind not in TEST_KINDS:
            raise ValueError(f"테스트 종류는 {TEST_KINDS} 중 하나: {kind!r}")
        with self._lock:  # 요청보다 먼저 표시를 바꾼다 (첫 음량이 덮어써지지 않게)
            if kind == "mic":
                self.mic = {
                    "dbfs": None,
                    "peak_dbfs": None,
                    "remaining_s": None,
                    "heard": False,
                    "waiting": True,
                }
            else:
                self.speaker_at = self.clock()
            self._bump()
        self.bus.publish(Envelope.new("audio/test", SOURCE, {"kind": kind}, self.session_id))

    # ── 턴 ────────────────────────────────────────────────────────────

    def _new_turn(self, kind: str, **fields: Any) -> dict[str, Any]:
        self.turns += 1
        self.turn = {"id": self.turns, "kind": kind, "at": self.clock(), **fields}
        return self.turn

    def _open_turn(self) -> dict[str, Any] | None:
        turn = self.turn
        if turn is None or self.clock() - turn["at"] > TURN_S:
            return None
        return turn

    def _asked(self) -> bool:
        turn = self._open_turn()
        return turn is not None and turn.get("decision") == "ASK"

    def _bump(self) -> None:
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    # ── 출력 ──────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """지금 화면에 그릴 정보 (README의 /view.json 형식)."""
        with self._lock:
            now = self.clock()
            stale = self.state_at is None or now - self.state_at > STATE_STALE_S
            state = None if stale else self.state
            evidence = (state or {}).get("evidence") or {}
            risk = state["risk"] if state else "none"
            warning = None
            if state and risk in ("warn", "danger"):
                warning = RiskWatcher.warning(risk, state["state"], state)
            turn = None
            if self.turn is not None:
                turn = {k: v for k, v in self.turn.items() if k not in ("at", "speech_end")}
                turn["age_s"] = round(now - self.turn["at"], 1)
            return {
                "version": self.version,
                "device": self.device,
                "turn": turn,
                "devices": self.devices,
                "safe_stop": self.safe_stop,
                "state": state["state"] if state else None,
                "state_text": STATE_TEXT.get(state["state"], "상태 모름") if state else "상태 모름",
                "risk": risk,
                "heaters": evidence.get("heaters") or {},
                "person": evidence.get("person"),
                "absent_s": evidence.get("absent_s") or 0.0,
                "warning": warning,
                "stale": stale,
                "alive": sorted(s for s, at in self.alive.items() if now - at <= ALIVE_S),
                "log": list(self.log),
                "mic": self.mic,
                "speaker_age_s": None
                if self.speaker_at is None
                else round(now - self.speaker_at, 1),
            }

    def wait(self, version: int, timeout_s: float) -> None:
        """version보다 새 정보가 생기거나 timeout_s가 지날 때까지 기다린다 (SSE용)."""
        with self.changed:
            self.changed.wait_for(lambda: self.version != version, timeout=timeout_s)

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
