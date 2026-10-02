"""발화 구간 자르기 (sherpa-onnx Silero VAD).

오디오 청크를 계속 넣으면, 발화가 끝났다고 판단된 구간(앞뒤 무음 제외)을 돌려준다.
발화 끝 판단은 `min_silence_duration`만큼 조용해진 뒤라서, 구간은 그만큼 늦게 나온다.
"""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

import numpy as np

SAMPLE_RATE = 16000  # Silero VAD는 16kHz만 받는다
DEFAULT_VAD_MODEL = "models/silero_vad.onnx"


@dataclass(frozen=True)
class VadConfig:
    """특강 p.36 예시값. 주방 소음에서의 조정은 STT-11."""

    threshold: float = 0.5  # 음성 확률 임계값
    min_silence_s: float = 0.5  # 이만큼 조용하면 발화 끝
    min_speech_s: float = 0.25  # 이보다 짧은 소리는 무시
    max_speech_s: float = 20.0  # 이보다 길면 강제로 끊음


@dataclass(frozen=True)
class SpeechSegment:
    samples: np.ndarray  # float32 mono 16kHz
    end_mono: float  # 발화가 끝난 샘플이 들어온 시각 (time.monotonic 기준)


def vad_model_from_env() -> str:
    return os.environ.get("JARVIS_VAD_MODEL", DEFAULT_VAD_MODEL)


def end_mono(segment_end: int, received: int, last_arrival_mono: float) -> float:
    """구간 끝 샘플의 도착 시각을 거꾸로 계산한다.

    지금까지 받은 마지막 샘플(번호 received)이 last_arrival_mono에 도착했으므로,
    그보다 (received - segment_end)개 앞선 샘플은 그만큼의 재생 시간 전에 도착했다.
    """
    return last_arrival_mono - (received - segment_end) / SAMPLE_RATE


class Segmenter:
    """오디오 청크 → 발화 구간. 청크 길이는 자유롭고, 내부에서 VAD 창(512 샘플) 단위로 넣는다."""

    def __init__(self, model: str | pathlib.Path, config: VadConfig | None = None) -> None:
        model = pathlib.Path(model)
        if not model.is_file():
            raise FileNotFoundError(
                f"VAD 모델이 없습니다: {model}. "
                "services/audio_svc/README.md의 '모델 받기'를 따라 받으세요."
            )
        import sherpa_onnx

        config = config or VadConfig()
        cfg = sherpa_onnx.VadModelConfig()
        cfg.sample_rate = SAMPLE_RATE
        cfg.silero_vad.model = str(model)
        cfg.silero_vad.threshold = config.threshold
        cfg.silero_vad.min_silence_duration = config.min_silence_s
        cfg.silero_vad.min_speech_duration = config.min_speech_s
        cfg.silero_vad.max_speech_duration = config.max_speech_s
        self._window = cfg.silero_vad.window_size
        self._vad = sherpa_onnx.VoiceActivityDetector(
            cfg, buffer_size_in_seconds=config.max_speech_s + 10
        )
        self._pending = np.zeros(0, dtype=np.float32)
        self._received = 0  # 지금까지 받은 샘플 수
        self._last_arrival = 0.0

    def feed(self, samples: np.ndarray, arrival_mono: float) -> list[SpeechSegment]:
        """청크를 넣고, 이번에 끝난 발화 구간들을 돌려준다.

        arrival_mono: 이 청크의 마지막 샘플이 들어온 시각 (마이크 콜백 시각 등).
        """
        self._pending = np.concatenate([self._pending, samples.astype(np.float32, copy=False)])
        self._received += len(samples)
        self._last_arrival = arrival_mono
        while len(self._pending) >= self._window:
            self._vad.accept_waveform(self._pending[: self._window])
            self._pending = self._pending[self._window :]
        return self._pop()

    def flush(self) -> list[SpeechSegment]:
        """입력이 끝났을 때 진행 중이던 발화까지 마무리해 돌려준다."""
        if len(self._pending):
            self._vad.accept_waveform(self._pending)
            self._pending = np.zeros(0, dtype=np.float32)
        self._vad.flush()
        return self._pop()

    def _pop(self) -> list[SpeechSegment]:
        out = []
        while not self._vad.empty():
            seg = self._vad.front
            samples = np.asarray(seg.samples, dtype=np.float32)
            end = end_mono(seg.start + len(samples), self._received, self._last_arrival)
            out.append(SpeechSegment(samples=samples, end_mono=end))
            self._vad.pop()
        return out
