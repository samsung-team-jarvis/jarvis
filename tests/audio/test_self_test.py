import numpy as np
import pytest

from common.bus import MemoryBus
from common.messages import Envelope
from services.audio_svc.self_test import (
    LEVEL_PERIOD_S,
    MIC_TEST_S,
    SILENCE_DBFS,
    SPEAKER_TEXT,
    SelfTest,
    dbfs,
)
from services.audio_svc.service import AudioService

RATE = 16000
CHUNK_S = 0.1  # 마이크 청크 0.1초씩


class FakeSpeaker:
    def __init__(self) -> None:
        self.said: list[str] = []

    def say(self, text: str) -> None:
        self.said.append(text)


class Rig:
    def __init__(self, speaker: FakeSpeaker | None = None) -> None:
        self.now = 100.0
        self.bus = MemoryBus()
        self.levels: list[dict] = []
        self.events: list[str] = []
        self.bus.subscribe("audio/level", lambda m: self.levels.append(m.payload))
        self.test = SelfTest(
            self.bus, "s_t", speaker, clock=lambda: self.now, on_event=self.events.append
        )
        self.test.start()

    def request(self, kind: str) -> None:
        self.bus.publish(Envelope.new("audio/test", "webview", {"kind": kind}, "s_web"))

    def feed(self, seconds: float, amplitude: float) -> None:
        """amplitude 크기의 사인파를 CHUNK_S씩 seconds만큼 넣는다 (시계도 같이 간다)."""
        for _ in range(round(seconds / CHUNK_S)):
            self.now += CHUNK_S
            t = np.arange(int(RATE * CHUNK_S)) / RATE
            self.test.feed((amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32), self.now)


def test_dbfs() -> None:
    assert dbfs(np.ones(100, dtype=np.float32)) == 0.0
    assert dbfs(np.full(100, 0.1, dtype=np.float32)) == pytest.approx(-20.0)
    assert dbfs(np.zeros(100, dtype=np.float32)) == SILENCE_DBFS
    assert dbfs(np.zeros(0, dtype=np.float32)) == SILENCE_DBFS


def test_speaker_test_reads_test_sentence() -> None:
    speaker = FakeSpeaker()
    rig = Rig(speaker)
    rig.request("speaker")
    assert speaker.said == [SPEAKER_TEXT]
    assert rig.levels == []  # 마이크 음량은 내지 않는다


def test_speaker_test_without_tts_only_reports() -> None:
    rig = Rig(speaker=None)
    rig.request("speaker")
    assert "음성 응답이 꺼져" in rig.events[-1]


def test_no_levels_without_mic_test() -> None:
    rig = Rig()
    rig.feed(2.0, 0.3)
    assert rig.levels == []  # 테스트 중이 아니면 녹화에 쌓이지 않게 아무것도 내지 않는다


def test_mic_test_publishes_levels_until_done() -> None:
    rig = Rig()
    rig.request("mic")
    rig.feed(1.0, 0.001)  # 조용함
    rig.feed(1.0, 0.3)  # 말소리 크기
    rig.feed(MIC_TEST_S, 0.001)  # 끝날 때까지 + 더
    count = round(MIC_TEST_S / LEVEL_PERIOD_S)
    assert len(rig.levels) == count  # 0.2초마다, 5초 동안
    assert rig.levels[-1]["remaining_s"] == 0.0  # 마지막은 끝 표시
    assert all(
        a["remaining_s"] > b["remaining_s"]
        for a, b in zip(rig.levels, rig.levels[1:], strict=False)
    )
    quiet, loud = rig.levels[0]["dbfs"], rig.levels[7]["dbfs"]
    assert quiet < -50 and loud > -15
    assert rig.levels[-1]["peak_dbfs"] == pytest.approx(loud, abs=0.2)  # 최댓값은 끝까지 남는다
    assert "끝" in rig.events[-1]
    rig.feed(1.0, 0.3)
    assert len(rig.levels) == count  # 끝난 뒤에는 다시 안 낸다


def test_new_mic_test_resets_peak() -> None:
    rig = Rig()
    rig.request("mic")
    rig.feed(MIC_TEST_S, 0.3)
    rig.request("mic")
    rig.feed(MIC_TEST_S, 0.001)
    assert rig.levels[-1]["peak_dbfs"] < -50


class OneSegmenter:
    def feed(self, samples: np.ndarray, arrival_mono: float) -> list:
        return []

    def flush(self) -> list:
        return []


def test_audio_service_passes_every_chunk_to_on_chunk() -> None:
    seen: list[float] = []
    service = AudioService(
        stt=None,  # 구간이 없어 받아쓰지 않는다
        segmenter=OneSegmenter(),
        bus=MemoryBus(),
        session_id="s",
        on_chunk=lambda samples, at: seen.append(at),
    )
    chunks = [(np.zeros(1600, dtype=np.float32), 1.0 + i * 0.1) for i in range(3)]
    service.run(chunks)
    assert seen == [1.0, 1.1, 1.2]
