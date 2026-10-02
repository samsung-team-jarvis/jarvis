"""SenseVoice(sherpa-onnx) 받아쓰기.

wav 파일이든 마이크 청크든 float32 mono 샘플을 넣으면 텍스트와 처리 시간을 돌려준다.
모델 폴더에는 `model.int8.onnx`와 `tokens.txt`가 있어야 한다 (README의 모델 받기 참고).
"""

from __future__ import annotations

import os
import pathlib
import time
import wave
from dataclasses import dataclass

import numpy as np

# 학교 보드 배포 이미지(~/voice/models)와 같은 int8 모델. 모델 파일은 git 제외(models/).
DEFAULT_MODEL_DIR = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
MODEL_FILE = "model.int8.onnx"
TOKENS_FILE = "tokens.txt"
LANGUAGES = ("auto", "ko", "zh", "en", "ja", "yue")


@dataclass(frozen=True)
class Transcript:
    """받아쓰기 결과. 필드 이름은 interfaces `stt/text` payload와 같다."""

    text: str
    audio_ms: int  # 입력 음성 길이
    stt_ms: int  # 인식에 걸린 시간 (모델 로드 제외)

    @property
    def rtf(self) -> float:
        """Real Time Factor = 처리 시간 / 음성 길이. 1보다 작아야 실시간."""
        return self.stt_ms / self.audio_ms if self.audio_ms else 0.0


def model_dir_from_env() -> str:
    return os.environ.get("JARVIS_STT_MODEL_DIR", DEFAULT_MODEL_DIR)


def read_wav(path: str | pathlib.Path) -> tuple[np.ndarray, int]:
    """16-bit PCM wav → (float32 mono 샘플 [-1, 1], 샘플레이트). 스테레오는 채널 평균.

    wav가 아니거나 깨진 파일, 16-bit가 아닌 파일은 ValueError.
    """
    try:
        with wave.open(str(path), "rb") as f:
            width = f.getsampwidth()
            channels = f.getnchannels()
            sample_rate = f.getframerate()
            frames = f.readframes(f.getnframes())
    except (wave.Error, EOFError) as e:
        raise ValueError(f"{path}: wav 파일이 아니거나 깨졌습니다 ({e!r})") from e
    if width != 2:
        raise ValueError(
            f"{path}: 16-bit PCM wav만 지원합니다 (현재 {width * 8}-bit). "
            "ffmpeg -i <입력> -ar 16000 -ac 1 -sample_fmt s16 <출력.wav>"
        )
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


class SenseVoice:
    """SenseVoice-Small 오프라인 인식기. 한 번 로드해 두고 transcribe()를 여러 번 부른다."""

    def __init__(
        self,
        model_dir: str | pathlib.Path,
        language: str = "ko",
        num_threads: int = 4,
        use_itn: bool = True,
    ) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"language는 {LANGUAGES} 중 하나여야 합니다: {language!r}")
        model_dir = pathlib.Path(model_dir)
        model, tokens = model_dir / MODEL_FILE, model_dir / TOKENS_FILE
        missing = [p.name for p in (model, tokens) if not p.is_file()]
        if missing:
            raise FileNotFoundError(
                f"{model_dir}에 {', '.join(missing)}이(가) 없습니다. "
                "services/audio_svc/README.md의 '모델 받기'를 따라 받으세요."
            )

        import sherpa_onnx  # 모델이 없을 때도 위 오류 메시지를 볼 수 있게 늦게 import

        self.language = language
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
            model=str(model),
            tokens=str(tokens),
            language=language,
            use_itn=use_itn,
            num_threads=num_threads,
        )

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> Transcript:
        """float32 mono 샘플을 받아쓴다. 16kHz가 아니면 sherpa-onnx가 내부에서 변환한다."""
        start = time.monotonic()
        stream = self._recognizer.create_stream()
        stream.accept_waveform(sample_rate, samples)
        self._recognizer.decode_stream(stream)
        stt_ms = round((time.monotonic() - start) * 1000)
        audio_ms = round(len(samples) * 1000 / sample_rate)
        return Transcript(text=stream.result.text.strip(), audio_ms=audio_ms, stt_ms=stt_ms)

    def transcribe_file(self, path: str | pathlib.Path) -> Transcript:
        samples, sample_rate = read_wav(path)
        return self.transcribe(samples, sample_rate)
