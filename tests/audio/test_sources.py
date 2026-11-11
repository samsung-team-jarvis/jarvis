"""마이크 입력 (STT-14): 16 kHz를 못 받는 마이크는 기본 샘플레이트로 열고 16 kHz로 줄인다."""

import sys
import threading
import types

import numpy as np
import pytest

from services.audio_svc.sources import Resampler, mic_chunks, mic_rate


def tone(freq: float, rate: int, seconds: float = 1.0) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    return (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def run_chunks(r: Resampler, x: np.ndarray, chunk: int) -> np.ndarray:
    return np.concatenate([r(x[i : i + chunk]) for i in range(0, len(x), chunk)])


def peak_hz(y: np.ndarray, rate: int) -> float:
    spec = np.abs(np.fft.rfft(y * np.hanning(len(y))))
    return float(np.fft.rfftfreq(len(y), 1 / rate)[spec.argmax()])


@pytest.mark.parametrize("src", [48000, 44100])
def test_resampled_speech_band_keeps_length_and_pitch(src: int) -> None:
    y = run_chunks(Resampler(src), tone(1000, src, 2.0), src // 10)  # 100 ms 청크
    assert abs(len(y) - 32000) <= 2  # 2초 → 16 kHz 32,000 샘플
    assert abs(peak_hz(y[1000:], 16000) - 1000) < 5
    steady = y[2000:-2000]
    assert 0.45 < np.abs(steady).max() < 0.55  # 크기 그대로


def test_chunk_boundaries_do_not_click() -> None:
    x = tone(440, 48000, 1.0)
    whole = Resampler(48000)(x)
    pieces = run_chunks(Resampler(48000), x, 4800)
    n = min(len(whole), len(pieces))
    assert np.max(np.abs(whole[:n] - pieces[:n])) < 1e-4  # 한 번에 넣은 것과 같다


def test_sound_above_8khz_is_filtered_not_folded() -> None:
    y = run_chunks(Resampler(48000), tone(12000, 48000, 1.0), 4800)
    # 그대로 뽑으면 4 kHz로 접혀 들어온다 — 저역 통과로 거의 없어져야 한다
    assert np.abs(y[2000:-2000]).max() < 0.02


def test_same_rate_passes_through() -> None:
    x = tone(440, 16000, 0.1)
    assert Resampler(16000)(x) is x


class FakeSd:
    """sounddevice 대역. ok_16k=False면 16 kHz 확인이 실패하는 USB 마이크."""

    def __init__(self, ok_16k: bool, default: int = 48000) -> None:
        self.ok_16k, self.default = ok_16k, default
        self.opened: dict = {}

    def check_input_settings(self, **kw) -> None:
        if not self.ok_16k:
            raise RuntimeError("Invalid sample rate [PaErrorCode -9997]")

    def query_devices(self, device, kind):
        return {"default_samplerate": float(self.default)}

    def InputStream(self, **kw):  # noqa: N802 (sounddevice 이름 그대로)
        self.opened = kw
        sd = self

        class Stream:
            def __enter__(self):
                block = kw["blocksize"]
                x = tone(1000, kw["samplerate"], 1.0)
                for i in range(0, len(x), block):
                    kw["callback"](x[i : i + block, None], block, None, None)
                return self

            def __exit__(self, *a):
                return False

        sd.stream = Stream()
        return sd.stream


@pytest.fixture
def fake_sd(monkeypatch):
    def install(ok_16k: bool) -> FakeSd:
        sd = FakeSd(ok_16k)
        monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(**{
            "check_input_settings": sd.check_input_settings,
            "query_devices": sd.query_devices,
            "InputStream": sd.InputStream,
        }))  # fmt: skip
        return sd

    return install


def take(gen, n: int, stop: threading.Event) -> list:
    out = [next(gen) for _ in range(n)]
    stop.set()
    return out


def test_mic_without_16k_opens_default_rate_and_yields_16k(fake_sd, capsys) -> None:
    sd = fake_sd(ok_16k=False)
    stop = threading.Event()
    chunks = take(mic_chunks(stop=stop), 10, stop)
    assert sd.opened["samplerate"] == 48000 and sd.opened["blocksize"] == 4800
    total = sum(len(c) for c, _ in chunks)
    assert abs(total - 16000) <= 2  # 1초 분량이 16 kHz로
    assert "48000 Hz로 열고 16000 Hz로 줄입니다" in capsys.readouterr().out


def test_mic_with_16k_is_unchanged(fake_sd) -> None:
    sd = fake_sd(ok_16k=True)
    stop = threading.Event()
    chunks = take(mic_chunks(stop=stop), 10, stop)
    assert sd.opened["samplerate"] == 16000
    assert [len(c) for c, _ in chunks] == [1600] * 10
    assert mic_rate(types.SimpleNamespace(check_input_settings=lambda **k: None), None) == 16000
