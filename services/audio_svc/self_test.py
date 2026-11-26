"""마이크·스피커 테스트 (UI-04): 시연 화면의 버튼 → `audio/test` → 여기.

마이크·스피커는 audio_svc가 쥐고 있어서 webview가 직접 열지 않는다 (interfaces §2).

- `speaker`: 테스트 문장을 음성 응답과 같은 Speaker로 읽는다 (재생 중 마이크 막기가 그대로 적용).
- `mic`: MIC_TEST_S 동안 LEVEL_PERIOD_S마다 `audio/level`을 낸다. 테스트 중이 아니면 내지 않는다
  (녹화에 쌓이지 않게).
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Protocol

import numpy as np

from common.bus import Bus
from common.messages import Envelope

SOURCE = "audio_svc"
MIC_TEST_S = 5.0
LEVEL_PERIOD_S = 0.2
SPEAKER_TEXT = "스피커 테스트입니다. 이 말이 들리면 스피커는 정상입니다."
SILENCE_DBFS = -100.0  # 소리가 전혀 없을 때 (log 0 대신)


class Sayer(Protocol):
    def say(self, text: str) -> None: ...


def dbfs(samples: np.ndarray) -> float:
    """float(-1~1) 소리의 RMS를 dBFS로 (0이 최대). 비었거나 완전한 무음이면 SILENCE_DBFS."""
    if samples.size == 0:
        return SILENCE_DBFS
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return round(20 * math.log10(rms), 1) if rms > 0 else SILENCE_DBFS


class SelfTest:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        speaker: Sayer | None,
        clock: Callable[[], float] = time.monotonic,
        on_event: Callable[[str], None] | None = None,
    ) -> None:
        self.bus = bus
        self.session_id = session_id
        self.speaker = speaker
        self.clock = clock
        self.on_event = on_event
        self._lock = threading.Lock()
        self._until: float | None = None  # 마이크 테스트가 끝나는 시각
        self._window: list[np.ndarray] = []
        self._window_start = 0.0
        self._peak = SILENCE_DBFS

    def start(self) -> None:
        self.bus.subscribe("audio/test", self.on_request)

    def on_request(self, msg: Envelope) -> None:
        kind = msg.payload["kind"]
        if kind == "speaker":
            if self.speaker is None:
                self._say_event("스피커 테스트: 음성 응답이 꺼져 있어 재생하지 않습니다")
                return
            self.speaker.say(SPEAKER_TEXT)
            self._say_event("스피커 테스트 문장 재생")
        elif kind == "mic":
            with self._lock:
                now = self.clock()
                self._until = now + MIC_TEST_S
                self._window, self._window_start, self._peak = [], now, SILENCE_DBFS
            self._say_event(f"마이크 테스트 {MIC_TEST_S:.0f}초 시작")

    def feed(self, samples: np.ndarray, arrival_mono: float) -> None:
        """마이크 청크마다 부른다 (AudioService.run). 테스트 중이 아니면 아무것도 하지 않는다."""
        with self._lock:
            if self._until is None:
                return
            self._window.append(samples)
            elapsed = arrival_mono - self._window_start
            # 1e-6: 0.1초 청크 두 개가 부동소수점 오차로 0.2초에 못 미쳐 한 칸 밀리지 않게
            if elapsed < LEVEL_PERIOD_S - 1e-6 and arrival_mono < self._until:
                return
            level = dbfs(np.concatenate(self._window))
            self._peak = max(self._peak, level)
            remaining = max(round(self._until - arrival_mono, 1), 0.0)
            payload = {"dbfs": level, "peak_dbfs": self._peak, "remaining_s": remaining}
            self._window, self._window_start = [], arrival_mono
            if remaining == 0.0:
                self._until = None
        self.bus.publish(Envelope.new("audio/level", SOURCE, payload, self.session_id))
        if remaining == 0.0:
            self._say_event(f"마이크 테스트 끝: 최대 {payload['peak_dbfs']} dBFS")

    def _say_event(self, text: str) -> None:
        if self.on_event:
            self.on_event(text)
