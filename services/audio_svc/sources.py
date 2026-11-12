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


class Resampler:
    """스트리밍 리샘플러: src Hz → dst Hz (mono float32). numpy만 쓴다.

    저역 통과(창 씌운 sinc FIR, dst 나이퀴스트의 90%)로 접힘을 막은 뒤 선형 보간한다.
    청크 경계에서 끊기지 않게 필터 꼬리와 보간 위치를 다음 청크로 넘긴다.
    필터 지연은 (taps-1)/2 샘플(48 kHz에서 약 1 ms)이다.
    """

    def __init__(self, src: int, dst: int = SAMPLE_RATE, taps: int = 129) -> None:
        self.src, self.dst = src, dst
        self.step = src / dst  # 출력 한 샘플마다 입력에서 나아가는 거리
        # 입력 샘플 단위 주파수: 낮은 쪽 나이퀴스트(0.5)의 90% — 줄일 때는 dst 기준
        cutoff = 0.45 * min(1.0, dst / src)
        n = np.arange(taps) - (taps - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hamming(taps)
        self.h = (h / h.sum()).astype(np.float32)
        self.tail = np.zeros(taps - 1, dtype=np.float32)
        self.buf = np.zeros(0, dtype=np.float32)
        self.pos = 0.0  # buf 안에서 다음 출력 샘플의 위치

    def __call__(self, x: np.ndarray) -> np.ndarray:
        if self.src == self.dst:
            return x
        padded = np.concatenate([self.tail, x.astype(np.float32)])
        self.tail = padded[len(padded) - len(self.tail) :]
        self.buf = np.concatenate([self.buf, np.convolve(padded, self.h, mode="valid")])
        last = len(self.buf) - 1
        if last < self.pos:
            return np.zeros(0, dtype=np.float32)
        count = int((last - self.pos) // self.step) + 1
        t = self.pos + np.arange(count) * self.step
        out = np.interp(t, np.arange(len(self.buf)), self.buf).astype(np.float32)
        nxt = self.pos + count * self.step
        drop = int(nxt)
        self.buf, self.pos = self.buf[drop:], nxt - drop
        return out


def mic_rate(sd, device: int | str | None) -> int:
    """마이크를 열 샘플레이트: 16 kHz가 되면 16 kHz, 안 되면 장치 기본값 (16 kHz로 줄여 쓴다)."""
    try:
        sd.check_input_settings(device=device, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        return SAMPLE_RATE
    except Exception as exc:  # sounddevice.PortAudioError 등 — 장치마다 다르다
        rate = int(sd.query_devices(device, "input")["default_samplerate"])
        print(
            f"마이크: {SAMPLE_RATE} Hz로 열 수 없어 {rate} Hz로 열고 "
            f"{SAMPLE_RATE} Hz로 줄입니다 ({exc})"
        )
        return rate


def mic_chunks(
    device: int | str | None = None, chunk_ms: int = 100, stop: threading.Event | None = None
) -> Iterator[Chunk]:
    """마이크에서 16kHz mono로 녹음해 청크를 내보낸다. stop이 설정되거나 Ctrl+C로 끝난다.

    마이크가 16 kHz를 못 받으면(USB 마이크는 44.1·48 kHz만 받는 것이 많다) 기본 샘플레이트로 열고
    16 kHz로 줄인다 (`Resampler`).
    도착 시각은 콜백이 불린 시각이라 실제 녹음 시각보다 입력 지연(수십 ms 수준)만큼 늦다.
    """
    import sounddevice as sd  # 보드에는 libportaudio2가 필요해서 마이크를 쓸 때만 import

    stop = stop or threading.Event()
    q: queue.Queue[Chunk] = queue.Queue()
    rate = mic_rate(sd, device)
    resample = Resampler(rate)

    def callback(indata, frames, time_info, status) -> None:
        if status:
            print(f"마이크 경고: {status}")
        q.put((indata[:, 0].copy(), time.monotonic()))

    with sd.InputStream(
        samplerate=rate,
        channels=1,
        dtype="float32",
        blocksize=rate * chunk_ms // 1000,
        device=device,
        callback=callback,
    ):
        silent_samples = 0  # 시작부터 연속으로 정확히 0인 샘플 수 (-1이면 확인 끝)
        while not stop.is_set():
            try:
                samples, arrival = q.get(timeout=0.5)
            except queue.Empty:
                continue
            chunk = (resample(samples), arrival)
            if not len(chunk[0]):
                continue
            if silent_samples >= 0:
                silent_samples = silent_samples + len(chunk[0]) if not chunk[0].any() else -1
                if silent_samples >= SAMPLE_RATE * SILENT_WARN_S:
                    print(MIC_SILENT_WARNING)
                    silent_samples = -1
            yield chunk
