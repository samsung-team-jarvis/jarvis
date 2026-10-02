"""한국어 TTS (sherpa-onnx VITS) — STT-12.

학교 배포 이미지와 같은 구성: VITS model.onnx + tokens.txt + espeak-ng-data,
CPU 2스레드 (특강 p.34·38).
"""

from __future__ import annotations

import os
import pathlib
import re

import numpy as np

DEFAULT_TTS_MODEL_DIR = "models/vits-mimic3-ko_KO-kss_low"
# 이 모델은 ?·! 를 발음 기호로 바꾸지 못해 경고를 낸다 → 마침표로 바꾼다
_UNSPEAKABLE = re.compile(r"[?!？！]")


def tts_model_dir_from_env() -> str:
    return os.environ.get("JARVIS_TTS_MODEL_DIR", DEFAULT_TTS_MODEL_DIR)


def clean(text: str) -> str:
    return _UNSPEAKABLE.sub(".", text).strip()


class KoreanTts:
    """모델 폴더: *.onnx 1개 + tokens.txt + espeak-ng-data/."""

    def __init__(self, model_dir: str | pathlib.Path, num_threads: int = 2, speed: float = 1.0):
        model_dir = pathlib.Path(model_dir)
        models = sorted(model_dir.glob("*.onnx"))
        tokens, data = model_dir / "tokens.txt", model_dir / "espeak-ng-data"
        if len(models) != 1 or not tokens.is_file() or not data.is_dir():
            raise FileNotFoundError(
                f"{model_dir}에 TTS 모델(*.onnx 1개, tokens.txt, espeak-ng-data/)이 없습니다. "
                "services/audio_svc/README.md의 '모델 받기'를 따라 받으세요."
            )
        import sherpa_onnx

        self.speed = speed
        self._tts = sherpa_onnx.OfflineTts(
            sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=str(models[0]), tokens=str(tokens), lexicon="", data_dir=str(data)
                    ),
                    num_threads=num_threads,
                )
            )
        )

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        """문장 → (float32 mono 샘플, 샘플레이트)."""
        audio = self._tts.generate(clean(text), sid=0, speed=self.speed)
        return np.asarray(audio.samples, dtype=np.float32), audio.sample_rate
