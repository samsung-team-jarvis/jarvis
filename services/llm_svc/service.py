"""llm_svc: `stt/text`(호출어 있음) → (LLM →) 규칙 파서 → `llm/function_call` 발행.

생성기(`generate`)가 없으면 규칙 파서만 쓴다: `valid: true`, `fallback: true`, `tokens: 0`,
`raw_text`는 파서에 넣은 명령 문장. 생성기가 있으면 LLM 출력을 먼저 쓰고, 검증에 실패하면
규칙 파서로 대체한다 (`valid: false`, `fallback: true`) — interpret.resolve, interfaces §2.
LLM에 주는 상황(context)은 `fusion/state`의 마지막 상태다. 받은 적이 없으면 IDLE로 넣는다
(학습 문장에 흔한 상태. 위험 판단은 Safety Guard가 따로 한다). `last_target`은 LLM-12에서.

`background=True`면 명령 해석을 작업 스레드 하나에서 차례로 한다. MQTT 구독 핸들러는 통신 스레드에서
도는데, 거기서 LLM을 돌리면 생성하는 동안 이 서비스의 송수신(발행·생존 신호)이 모두 멈춘다 (#120).
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from typing import Any

from common.bus import Bus
from common.messages import Envelope
from services.llm_svc.interpret import Generate, command_text, resolve
from services.llm_svc.stt_fixes import normalize

SOURCE = "llm_svc"
DEFAULT_STATE = "IDLE"


class LlmService:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        on_call: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        generate: Generate | None = None,
        background: bool = False,
    ) -> None:
        self.bus = bus
        self.session_id = session_id  # heartbeat용. 명령은 받은 stt/text의 session_id를 이어 쓴다
        self.on_call = on_call
        self.clock = clock
        self.generate = generate
        self.background = background
        self._queue: queue.Queue[Envelope] = queue.Queue()
        self.state = DEFAULT_STATE
        self.published = 0
        self.ignored = 0  # 호출어가 없어 처리하지 않은 stt/text
        self.fallbacks = 0  # LLM 출력이 검증에 실패해 규칙 파서로 대체한 수
        self._last_heartbeat: float | None = None

    def start(self) -> None:
        if self.background:
            threading.Thread(target=self._work, daemon=True, name="llm_svc-worker").start()
            self.bus.subscribe("stt/text", self._queue.put)
        else:
            self.bus.subscribe("stt/text", self.handle)
        self.bus.subscribe("fusion/state", self.on_state)

    def on_state(self, msg: Envelope) -> None:
        self.state = msg.payload["state"]

    def context(self) -> dict[str, Any]:
        return {"state": self.state, "last_target": None}

    def handle(self, msg: Envelope) -> None:
        if not msg.payload["wake"]:
            self.ignored += 1
            return
        text = msg.payload["text"]
        command = command_text(text)
        if command is None:  # wake=true인데 호출어를 못 찾음 (다른 판정을 쓰는 발행자)
            command = normalize(text)
        start = time.monotonic()
        r = resolve(command, self.context(), self.generate)
        gen_ms = round((time.monotonic() - start) * 1000, 3)
        if not r.valid:
            self.fallbacks += 1
        payload = {
            "call": r.call,
            "raw_text": r.raw_text,
            "valid": r.valid,
            "fallback": r.fallback,
            "gen_ms": gen_ms,
            "tokens": r.tokens,
        }
        out = Envelope.new("llm/function_call", SOURCE, payload, msg.session_id)
        self.bus.publish(out)
        self.published += 1
        if self.on_call:
            self.on_call(out)

    def _work(self) -> None:
        while True:
            msg = self._queue.get()
            try:
                self.handle(msg)
            finally:
                self._queue.task_done()

    def wait_idle(self) -> None:
        """받은 발화를 모두 처리할 때까지 기다린다 (background일 때, 확인·테스트용)."""
        self._queue.join()

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
