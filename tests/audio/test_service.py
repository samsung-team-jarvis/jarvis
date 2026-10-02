import pathlib
import wave

import numpy as np
import pytest

from common.bus import MemoryBus
from common.messages import Envelope
from services.audio_svc.service import AudioService
from services.audio_svc.sources import wav_chunks
from services.audio_svc.stt import DEFAULT_MODEL_DIR, SenseVoice, Transcript, read_wav
from services.audio_svc.vad import (
    DEFAULT_VAD_MODEL,
    SAMPLE_RATE,
    Segmenter,
    SpeechSegment,
    end_mono,
)

MODEL_DIR = pathlib.Path(DEFAULT_MODEL_DIR)
VAD_MODEL = pathlib.Path(DEFAULT_VAD_MODEL)


def write_wav(path: pathlib.Path, samples: np.ndarray, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


class FakeClock:
    def __init__(self) -> None:
        self.t = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


class FakeSTT:
    def __init__(self, texts: list[str]) -> None:
        self.texts = list(texts)

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        return Transcript(self.texts.pop(0), audio_ms=len(samples) * 1000 // sample_rate, stt_ms=7)


class FakeSegmenter:
    """feed 호출마다 미리 정한 구간 목록을 하나씩 돌려준다."""

    def __init__(self, per_feed: list[list[SpeechSegment]], at_flush: list[SpeechSegment]):
        self.per_feed = list(per_feed)
        self.at_flush = at_flush

    def feed(self, samples: np.ndarray, arrival_mono: float) -> list[SpeechSegment]:
        return self.per_feed.pop(0) if self.per_feed else []

    def flush(self) -> list[SpeechSegment]:
        return self.at_flush


def seg(seconds: float, end: float) -> SpeechSegment:
    return SpeechSegment(np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32), end)


def test_end_mono_counts_back_from_last_arrival() -> None:
    # 받은 샘플 32000개(2초) 중 16000번째에서 발화가 끝났다 → 마지막 도착 1초 전
    assert end_mono(16000, 32000, 50.0) == 49.0
    assert end_mono(32000, 32000, 50.0) == 50.0


def test_wav_chunks_splits_into_chunks(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "a.wav"
    write_wav(path, np.zeros(4000, dtype=np.float32))  # 0.25초
    sizes = [len(c) for c, _ in wav_chunks(path, chunk_ms=100)]
    assert sizes == [1600, 1600, 800]


def test_wav_chunks_realtime_waits_like_a_microphone(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "a.wav"
    write_wav(path, np.zeros(3200, dtype=np.float32))  # 0.2초 = 100 ms 청크 2개
    clock = FakeClock()
    arrivals = [t for _, t in wav_chunks(path, 100, realtime=True, clock=clock, sleep=clock.sleep)]
    assert clock.slept == pytest.approx([0.1, 0.1])
    assert arrivals == pytest.approx([100.1, 100.2])


def test_wav_chunks_rejects_other_sample_rates(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "a.wav"
    write_wav(path, np.zeros(800, dtype=np.float32), rate=48000)
    with pytest.raises(ValueError, match="16000 Hz"):
        list(wav_chunks(path))


def test_publishes_stt_text_per_segment() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("stt/text", got.append)
    segmenter = FakeSegmenter([[], [seg(1.5, 10.0)], []], at_flush=[seg(0.5, 12.0)])
    stt = FakeSTT(["자비스 후드 켜 줘.", "오늘 날씨 좋다"])
    service = AudioService(stt, segmenter, bus, "s_test", heartbeat_s=1e9)

    chunk = (np.zeros(1600, dtype=np.float32), 0.0)
    assert service.run([chunk, chunk, chunk]) == 2

    assert [m.payload for m in got] == [
        {"text": "자비스 후드 켜 줘.", "wake": True, "audio_ms": 1500, "stt_ms": 7,
         "speech_end_mono": 10.0},
        {"text": "오늘 날씨 좋다", "wake": False, "audio_ms": 500, "stt_ms": 7,
         "speech_end_mono": 12.0},
    ]  # fmt: skip
    assert {(m.source, m.session_id) for m in got} == {("audio_svc", "s_test")}
    assert service.ignored == 1  # "오늘 날씨 좋다"는 호출어 없음


def test_empty_transcripts_are_skipped() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("stt/text", got.append)
    service = AudioService(FakeSTT([""]), FakeSegmenter([], [seg(0.3, 1.0)]), bus, "s", 1e9)
    assert service.run([]) == 0
    assert got == [] and service.skipped == 1


def test_heartbeat_follows_interval() -> None:
    bus, beats = MemoryBus(), []
    bus.subscribe("system/heartbeat", beats.append)
    clock = FakeClock()
    service = AudioService(FakeSTT([]), FakeSegmenter([], []), bus, "s", 1.0, clock=clock)
    for _ in range(25):  # 100 ms마다 → 2.5초
        service.heartbeat()
        clock.t += 0.1
    assert len(beats) == 3  # 0초, 1초, 2초
    assert all(isinstance(b, Envelope) and b.payload == {"alive": True} for b in beats)


@pytest.mark.skipif(
    not (MODEL_DIR / "model.int8.onnx").is_file() or not VAD_MODEL.is_file(),
    reason="SenseVoice·VAD 모델 없음",
)
def test_real_vad_and_stt_split_two_utterances(tmp_path: pathlib.Path) -> None:
    """모델이 있을 때만: ko.wav를 1초 무음 사이에 두 번 넣으면 stt/text 두 건."""
    speech, rate = read_wav(MODEL_DIR / "test_wavs/ko.wav")
    assert rate == SAMPLE_RATE
    silence = np.zeros(SAMPLE_RATE, dtype=np.float32)
    path = tmp_path / "two.wav"
    write_wav(path, np.concatenate([silence, speech, silence, speech, silence]))

    bus, got = MemoryBus(), []
    bus.subscribe("stt/text", got.append)
    service = AudioService(SenseVoice(MODEL_DIR), Segmenter(VAD_MODEL), bus, "s_real", 1e9)
    assert service.run(wav_chunks(path)) == 2
    assert all("생각" in m.payload["text"] for m in got)
    assert got[0].payload["speech_end_mono"] < got[1].payload["speech_end_mono"]
