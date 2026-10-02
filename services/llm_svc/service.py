"""llm_svc v0: `stt/text`(호출어 있음) → 규칙 파서 → `llm/function_call` 발행.

LLM 연결(LLM-09) 전까지는 규칙 파서만 쓴다. 그래서 발행하는 메시지는 항상 `fallback: true`
(규칙 파서가 만든 명령), `tokens: 0`, `raw_text`는 파서에 넣은 명령 문장이다.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from common.bus import Bus
from common.messages import Envelope
from services.llm_svc.interpret import command_text
from services.llm_svc.rule_parser import parse
from services.llm_svc.stt_fixes import normalize

SOURCE = "llm_svc"


class LlmService:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        on_call: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.session_id = session_id  # heartbeat용. 명령은 받은 stt/text의 session_id를 이어 쓴다
        self.on_call = on_call
        self.clock = clock
        self.published = 0
        self.ignored = 0  # 호출어가 없어 처리하지 않은 stt/text
        self._last_heartbeat: float | None = None

    def start(self) -> None:
        self.bus.subscribe("stt/text", self.handle)

    def handle(self, msg: Envelope) -> None:
        if not msg.payload["wake"]:
            self.ignored += 1
            return
        text = msg.payload["text"]
        command = command_text(text)
        if command is None:  # wake=true인데 호출어를 못 찾음 (다른 판정을 쓰는 발행자)
            command = normalize(text)
        start = time.monotonic()
        call = parse(command)
        gen_ms = round((time.monotonic() - start) * 1000, 3)
        payload = {
            "call": call,
            "raw_text": command,
            "valid": True,
            "fallback": True,
            "gen_ms": gen_ms,
            "tokens": 0,
        }
        out = Envelope.new("llm/function_call", SOURCE, payload, msg.session_id)
        self.bus.publish(out)
        self.published += 1
        if self.on_call:
            self.on_call(out)

    def heartbeat(self, interval_s: float = 1.0) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= interval_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
