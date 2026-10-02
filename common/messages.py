"""메시지 봉투(Envelope) — 모든 서비스가 주고받는 메시지의 공통 형식.

규격: docs/architecture/interfaces.md §1(봉투), §2(토픽).
이 파일과 문서가 다르면 문서를 먼저 고친다.
서비스는 dict를 직접 조립하지 말고 `Envelope.new()`로 만들고 `Envelope.from_json()`으로 읽는다.
"""

from __future__ import annotations

import dataclasses
import json
import time
from typing import Any

ENVELOPE_VERSION = 1

# 토픽별 payload 필수 필드 (interfaces.md §2, v0.1). 선택 필드(`?`)는 넣지 않는다.
TOPIC_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "stt/text": frozenset({"text", "wake", "audio_ms", "stt_ms", "speech_end_mono"}),
    "vision/objects": frozenset({"objects", "frame_id", "pre_ms", "npu_ms", "post_ms"}),
    "sensor/reading": frozenset({"device_id", "temperature_c", "current_a"}),
    "fusion/state": frozenset({"state", "prev_state", "evidence", "risk"}),
    "llm/function_call": frozenset({"call", "raw_text", "valid", "fallback", "gen_ms", "tokens"}),
    "guard/decision": frozenset({"call", "decision", "reason"}),
    "control/command": frozenset({"seq", "cmd", "target", "value"}),
    "control/result": frozenset({"seq", "ok", "retries", "rtt_ms"}),
    "system/heartbeat": frozenset({"alive"}),
}


class MessageError(ValueError):
    """봉투 형식이나 토픽 payload가 규격에 맞지 않을 때."""


@dataclasses.dataclass(frozen=True)
class Envelope:
    type: str
    source: str
    session_id: str
    payload: dict[str, Any]
    ts: float
    mono: float
    v: int = ENVELOPE_VERSION

    @classmethod
    def new(cls, type: str, source: str, payload: dict[str, Any], session_id: str) -> Envelope:
        """지금 시각(ts: 유닉스, mono: 단조 시계)으로 봉투를 만들고 규격을 검사한다."""
        msg = cls(
            type=type,
            source=source,
            session_id=session_id,
            payload=payload,
            ts=time.time(),
            mono=time.monotonic(),
        )
        msg.validate()
        return msg

    def validate(self) -> None:
        if self.v != ENVELOPE_VERSION:
            raise MessageError(f"지원하지 않는 봉투 버전: {self.v}")
        for name in ("type", "source", "session_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise MessageError(f"{name}가 비어 있습니다")
        if not isinstance(self.payload, dict):
            raise MessageError("payload는 dict여야 합니다")
        required = TOPIC_REQUIRED_FIELDS.get(self.type)
        if required is None:
            raise MessageError(f"interfaces.md에 없는 토픽: {self.type}")
        missing = required - self.payload.keys()
        if missing:
            raise MessageError(f"{self.type} payload에 필수 필드 없음: {sorted(missing)}")

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, data: str | bytes) -> Envelope:
        try:
            raw = json.loads(data)
            msg = cls(**raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise MessageError(f"봉투를 읽을 수 없습니다: {exc}") from exc
        msg.validate()
        return msg
