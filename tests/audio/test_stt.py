import os
import pathlib
import wave

import numpy as np
import pytest

from services.audio_svc.stt import DEFAULT_MODEL_DIR, SenseVoice, Transcript, read_wav

MODEL_DIR = pathlib.Path(os.environ.get("JARVIS_STT_MODEL_DIR", DEFAULT_MODEL_DIR))


def write_wav(path: pathlib.Path, frames: np.ndarray, channels: int, rate: int, width: int = 2):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(width)
        f.setframerate(rate)
        f.writeframes(frames.tobytes())


def test_read_wav_mono_scales_to_float(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "mono.wav"
    write_wav(path, np.array([0, 16384, -32768], dtype="<i2"), channels=1, rate=16000)
    samples, rate = read_wav(path)
    assert rate == 16000
    assert samples.dtype == np.float32
    assert samples.tolist() == [0.0, 0.5, -1.0]


def test_read_wav_stereo_averages_channels(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "stereo.wav"
    # 프레임 2개: (L, R) = (16384, 0), (-16384, -16384)
    write_wav(path, np.array([16384, 0, -16384, -16384], dtype="<i2"), channels=2, rate=48000)
    samples, rate = read_wav(path)
    assert rate == 48000
    assert samples.tolist() == [0.25, -0.5]


def test_read_wav_rejects_non_16bit(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "u8.wav"
    write_wav(path, np.array([128, 128], dtype=np.uint8), channels=1, rate=16000, width=1)
    with pytest.raises(ValueError, match="16-bit"):
        read_wav(path)


def test_read_wav_rejects_broken_file(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "broken.wav"
    path.write_bytes(b"hi")
    with pytest.raises(ValueError, match="깨졌습니다"):
        read_wav(path)


def test_rtf() -> None:
    assert Transcript("x", audio_ms=2000, stt_ms=50).rtf == 0.025
    assert Transcript("", audio_ms=0, stt_ms=5).rtf == 0.0


def test_missing_model_names_files(tmp_path: pathlib.Path) -> None:
    (tmp_path / "tokens.txt").write_text("")
    with pytest.raises(FileNotFoundError, match="model.int8.onnx"):
        SenseVoice(tmp_path)


def test_unknown_language_rejected(tmp_path: pathlib.Path) -> None:
    with pytest.raises(ValueError, match="language"):
        SenseVoice(tmp_path, language="kr")


@pytest.mark.skipif(not (MODEL_DIR / "model.int8.onnx").is_file(), reason="SenseVoice 모델 없음")
def test_transcribes_bundled_korean_sample() -> None:
    """모델을 받아 둔 경우에만 실행. 모델 압축 파일에 들어 있는 test_wavs/ko.wav를 쓴다."""
    result = SenseVoice(MODEL_DIR, language="ko").transcribe_file(MODEL_DIR / "test_wavs/ko.wav")
    assert "생각" in result.text
    assert result.audio_ms == 4608
    assert result.stt_ms > 0
