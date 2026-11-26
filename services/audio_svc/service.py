"""audio_svc 본체: 오디오 청크 → VAD 구간 → 받아쓰기 → `stt/text` 발행.

입력 소스(마이크·wav)와 VAD·STT는 밖에서 넣어 준다. 그래서 테스트에서는 가짜로 바꿔 끼울 수 있다.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable, Iterable
from typing import Protocol

import numpy as np

from common.bus import Bus
from common.messages import Envelope
from services.audio_svc.sources import Chunk
from services.audio_svc.stt import Transcript
from services.audio_svc.vad import SAMPLE_RATE, SpeechSegment
from services.audio_svc.wake import is_wake, split_wake
from services.safety_guard.emergency import is_emergency

SOURCE = "audio_svc"
CHUNK_MARGIN_S = 0.2  # 청크가 도착한 시각과 그 소리 사이의 여유
MIN_TAIL_S = 0.4  # 응답 뒤에 이만큼은 남아야 다시 받아쓴다


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
        followup_s: float = 12.0,
        on_chunk: Callable[[np.ndarray, float], None] | None = None,
    ) -> None:
        self.stt = stt
        self.segmenter = segmenter
        self.bus = bus
        self.session_id = session_id
        self.heartbeat_s = heartbeat_s
        self.on_text = on_text
        self.clock = clock
        # TTS 재생 중이면 True. 그 구간에 걸친 말은 긴급 정지만 받는다
        # (에코가 명령이 되지 않게, STT-12). 예전에는 무음으로 바꿨는데,
        # 경고를 읽는 동안 외친 "멈춰"를 못 들었다 (보드 리허설, #STT-14)
        self.mute = mute
        self.on_chunk = on_chunk  # 받은 소리 그대로 (마이크 테스트 음량, UI-04)
        self.published = 0  # 발행한 stt/text 수
        self.ignored = 0  # 그중 호출어가 없어 명령으로 처리하지 않을 발화 수 (wake=false)
        self.skipped = 0  # 받아쓴 결과가 비어 버린 구간 수 (잡음 등)
        self.echo = 0  # 음성 응답 중에 들어와 버린 구간 수 (긴급 정지가 아니라서)
        self._muted_at: deque[float] = deque(maxlen=2000)  # 재생 중에 받은 청크 시각
        self._last_heartbeat: float | None = None
        # 되묻기 뒤 대답·대화 모드 (#STT-14): 응답 뒤 followup_s 동안은 호출어 없는 말 한 번을
        # 명령으로 낸다. 되묻기면 앞 명령과 합친다 ("켜줘" + "후드" → "자비스 후드 켜줘")
        self.followup_s = followup_s
        self._last_command = ""
        self._reply_until: float | None = None
        self._reply_prefix = ""

    def run(self, chunks: Iterable[Chunk]) -> int:
        """입력이 끝날 때까지 처리하고, 발행한 stt/text 수를 돌려준다."""
        for samples, arrival_mono in chunks:
            if self.mute and self.mute(arrival_mono):
                self._muted_at.append(arrival_mono)
            if self.on_chunk:
                self.on_chunk(samples, arrival_mono)
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
            if (tail := self._after_tts(seg)) is not None:
                wake = is_wake(result.text)
                if is_emergency(result.text, wake):
                    text = result.text  # 경고 중에도 "멈춰"는 받는다
                else:
                    self.echo += 1
                    # 응답 직후 이어 말하면 한 구간으로 붙는다 → 응답 뒤 부분만 다시 받아쓴다
                    if len(tail) < MIN_TAIL_S * SAMPLE_RATE:
                        continue
                    result = self.stt.transcribe(tail, SAMPLE_RATE)
                    if not result.text:
                        continue
                    text, wake = self._with_followup(result.text)
            else:
                text, wake = self._with_followup(result.text)
            payload = {
                "text": text,
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

    def _after_tts(self, seg: SpeechSegment) -> np.ndarray | None:
        """구간이 음성 응답 재생과 겹치면 재생이 끝난 뒤의 소리, 안 겹치면 None."""
        start = seg.end_mono - len(seg.samples) / SAMPLE_RATE
        muted = [t for t in self._muted_at if start - CHUNK_MARGIN_S <= t <= seg.end_mono]
        if not muted:
            return None
        cut = int((max(muted) + CHUNK_MARGIN_S - start) * SAMPLE_RATE)
        return seg.samples[max(cut, 0) :]

    def expect_reply(self, merge: bool = True) -> None:
        """응답을 읽어 줄 때 부른다: followup_s 동안 다음 한 번은 호출어 없이 받는다.

        merge=True(되묻기): 대답을 앞 명령과 합친다 ("켜줘" + "후드" → "후드 켜줘").
        merge=False(대화 모드): 명령을 실행한 뒤 이어 말하는 새 명령 ("후드도 켜줘").
        """
        self._reply_until = self.clock() + self.followup_s
        self._reply_prefix = self._last_command if merge else ""

    def _with_followup(self, text: str) -> tuple[str, bool]:
        if is_wake(text):
            self._last_command = split_wake(text) or ""
            self._reply_until = None
            return text, True
        if self._reply_until is None or self.clock() > self._reply_until:
            return text, False
        self._reply_until = None
        if self._reply_prefix:
            reply = text.strip().rstrip(".。!?,")
            merged = f"자비스 {reply} {self._reply_prefix}".strip()
        else:
            merged = f"자비스 {text.strip()}"
        self._last_command = split_wake(merged) or ""
        return merged, True

    def heartbeat(self) -> None:
        now = self.clock()
        if self._last_heartbeat is None or now - self._last_heartbeat >= self.heartbeat_s:
            self.bus.publish(
                Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id)
            )
            self._last_heartbeat = now
