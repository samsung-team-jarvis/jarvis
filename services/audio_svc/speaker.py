"""음성 응답 재생기 (STT-12): 문장을 순서대로 합성·재생하고, 재생 중에는 마이크를 막는다.

합성·재생은 별도 스레드에서 한다 (버스 콜백·마이크 루프를 막지 않게).
재생하는 동안과 끝난 뒤 tail_s 동안 `is_muted()`가 True
→ AudioService가 마이크 입력을 무음으로 바꾼다
(스피커 소리를 다시 명령으로 받아쓰는 에코 방지, 특강 p.38).
"""

from __future__ import annotations

import datetime
import pathlib
import queue
import threading
import time
import wave
from collections.abc import Callable
from typing import Protocol

import numpy as np

Player = Callable[[np.ndarray, int], None]


class Synthesizer(Protocol):
    def synthesize(self, text: str) -> tuple[np.ndarray, int]: ...


def sounddevice_player(samples: np.ndarray, sample_rate: int) -> None:
    import sounddevice as sd

    sd.play(samples, sample_rate)
    sd.wait()


def save_wav(path: pathlib.Path, samples: np.ndarray, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


class Speaker:
    def __init__(
        self,
        tts: Synthesizer,
        play: bool = True,
        out_dir: str | pathlib.Path | None = None,
        tail_s: float = 0.3,
        player: Player = sounddevice_player,
        clock: Callable[[], float] = time.monotonic,
        on_spoken: Callable[[str, float], None] | None = None,
    ) -> None:
        self.tts = tts
        self.play = play
        self.out_dir = pathlib.Path(out_dir) if out_dir else None
        self.tail_s = tail_s
        self.player = player
        self.clock = clock
        self.on_spoken = on_spoken
        self.spoken: list[str] = []
        self._muted_until = 0.0
        self._lock = threading.Lock()
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        self._queue.put(text)

    def is_muted(self, now: float | None = None) -> bool:
        with self._lock:
            return (self.clock() if now is None else now) < self._muted_until

    def close(self, timeout: float = 10.0) -> None:
        """남은 문장을 마저 처리하고 끝낸다."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _mute_for(self, seconds: float) -> None:
        with self._lock:
            self._muted_until = max(self._muted_until, self.clock() + seconds)

    def _work(self) -> None:
        while (text := self._queue.get()) is not None:
            samples, rate = self.tts.synthesize(text)
            seconds = len(samples) / rate
            if self.out_dir:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.datetime.now().strftime("%H%M%S_%f")
                save_wav(self.out_dir / f"tts_{stamp}.wav", samples, rate)
            if self.play:
                self._mute_for(seconds + self.tail_s)
                self.player(samples, rate)
                self._mute_for(self.tail_s)  # 재생이 예상보다 길어졌어도 끝난 뒤 tail_s는 막는다
            self.spoken.append(text)
            if self.on_spoken:
                self.on_spoken(text, seconds)
