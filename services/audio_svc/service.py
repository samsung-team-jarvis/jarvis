"""audio_svc 본체: 오디오 청크 → VAD 구간 → 받아쓰기 → `stt/text` 발행.

입력 소스(마이크·wav)와 VAD·STT는 밖에서 넣어 준다. 그래서 테스트에서는 가짜로 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Protocol

import numpy as np

from common.bus import Bus
from common.messages import Envelope
from services.audio_svc.sources import Chunk
from services.audio_svc.stt import Transcript
from services.audio_svc.vad import SAMPLE_RATE, SpeechSegment
from services.audio_svc.wake import is_wake

SOURCE = "audio_svc"


class Transcriber(Protocol):
    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript: ...


class SegmenterLike(Protocol):
    def feed(self, samples: np.ndarray, arrival_mono: float) -> list[SpeechSegment]: ...
    def flush(self) -> list[SpeechSegment]: ...


class AudioService:
    def __init__(
        self,
        stt: Transcriber,
        segmenter: SegmenterLike,
        bus: Bus,
        session_id: str,
        heartbeat_s: float = 1.0,
        on_text: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        mute: Callable[[float], bool] | None = None,
    ) -> None:
        self.stt = stt
        self.segmenter = segmenter
        self.bus = bus
        self.session_id = session_id
        self.heartbeat_s = heartbeat_s
        self.on_text = on_text
        self.clock = clock
        self.mute = mute  # TTS 재생 중이면 True → 그 구간 입력을 무음으로 (에코 방지, STT-12)
        self.published = 0  # 발행한 stt/text 수
        self.ignored = 0  # 그중 호출어가 없어 명령으로 처리하지 않을 발화 수 (wake=false)
        self.skipped = 0  # 받아쓴 결과가 비어 버린 구간 수 (잡음 등)
        self._last_heartbeat: float | None = None

    def run(self, chunks: Iterable[Chunk]) -> int:
        """입력이 끝날 때까지 처리하고, 발행한 stt/text 수를 돌려준다."""
        for samples, arrival_mono in chunks:
            if self.mute and self.mute(arrival_mono):
                # 건너뛰지 않고 무음으로 넣는다: 샘플 수로 계산하는 발화 끝 시각이 어긋나지 않게
                samples = np.zeros_like(samples)
            self.handle(self.segmenter.feed(samples, arrival_mono))
            self.heartbeat()
        self.handle(self.segmenter.flush())
        return self.published

    def handle(self, segments: list[SpeechSegment]) -> None:
        for seg in segments:
            result = self.stt.transcribe(seg.samples, SAMPLE_RATE)
            if not result.text:
                self.skipped += 1
                continue
            wake = is_wake(result.text)
            payload = {
                "text": result.text,
                "wake": wake,
                "audio_ms": result.audio_ms,
                "stt_ms": result.stt_ms,
                "speech_end_mono": seg.end_mono,
            }
            msg = Envelope.new("stt/text", SOURCE, payload, self.session_id)
            self.bus.publish(msg)
            self.published += 1
            self.ignored += not wake
            if self.on_text:
                self.on_text(msg)

    def heartbeat(self) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= self.heartbeat_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
