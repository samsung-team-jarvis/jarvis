"""오디오 입력 소스. 마이크와 wav 파일을 같은 형태로 내보낸다: (float32 mono 16kHz 청크, 도착 시각).

도착 시각은 time.monotonic() 기준이고, 청크의 마지막 샘플이 들어온 시각이다.
"""

from __future__ import annotations

import pathlib
import queue
import threading
import time
from collections.abc import Callable, Iterator

import numpy as np

from services.audio_svc.stt import read_wav
from services.audio_svc.vad import SAMPLE_RATE

Chunk = tuple[np.ndarray, float]

SILENT_WARN_S = 3
MIC_SILENT_WARNING = (
    f"마이크 경고: 시작 후 {SILENT_WARN_S}초 동안 입력이 완전히 0입니다. "
    "Mac이면 시스템 설정 > 개인정보 보호 및 보안 > 마이크에서 터미널 앱을 허용하고 "
    "터미널을 다시 실행하세요. 보드면 --device로 마이크 장치를 지정하세요."
)


def wav_chunks(
    path: str | pathlib.Path,
    chunk_ms: int = 100,
    realtime: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[Chunk]:
    """wav 파일을 청크로 나눠 내보낸다.

    realtime=True면 마이크처럼 실제 재생 속도로 내보낸다 (지연 측정용).
    False면 기다리지 않는다 (테스트·일괄 받아쓰기용).
    """
    samples, rate = read_wav(path)
    if rate != SAMPLE_RATE:
        raise ValueError(
            f"{path}: {SAMPLE_RATE} Hz wav만 지원합니다 (현재 {rate} Hz). "
            "ffmpeg -i <입력> -ar 16000 -ac 1 -sample_fmt s16 <출력.wav>"
        )
    step = SAMPLE_RATE * chunk_ms // 1000
    start = clock()
    for i in range(0, len(samples), step):
        chunk = samples[i : i + step]
        if realtime:
            due = start + (i + len(chunk)) / SAMPLE_RATE
            wait = due - clock()
            if wait > 0:
                sleep(wait)
        yield chunk, clock()


def mic_chunks(
    device: int | str | None = None, chunk_ms: int = 100, stop: threading.Event | None = None
) -> Iterator[Chunk]:
    """마이크에서 16kHz mono로 녹음해 청크를 내보낸다. stop이 설정되거나 Ctrl+C로 끝난다.

    도착 시각은 콜백이 불린 시각이라 실제 녹음 시각보다 입력 지연(수십 ms 수준)만큼 늦다.
    """
    import sounddevice as sd  # 보드에는 libportaudio2가 필요해서 마이크를 쓸 때만 import

    stop = stop or threading.Event()
    q: queue.Queue[Chunk] = queue.Queue()

    def callback(indata, frames, time_info, status) -> None:
        if status:
            print(f"마이크 경고: {status}")
        q.put((indata[:, 0].copy(), time.monotonic()))

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=SAMPLE_RATE * chunk_ms // 1000,
        device=device,
        callback=callback,
    ):
        silent_samples = 0  # 시작부터 연속으로 정확히 0인 샘플 수 (-1이면 확인 끝)
        while not stop.is_set():
            try:
                chunk = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if silent_samples >= 0:
                silent_samples = silent_samples + len(chunk[0]) if not chunk[0].any() else -1
                if silent_samples >= SAMPLE_RATE * SILENT_WARN_S:
                    print(MIC_SILENT_WARNING)
                    silent_samples = -1
            yield chunk
