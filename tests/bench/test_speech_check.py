import numpy as np
import pytest

from bench.speech_check import mix_at_snr, response_sentences


def snr_db(signal: np.ndarray, mixed: np.ndarray) -> float:
    noise = mixed.astype(np.float64) - signal
    return 10 * np.log10(np.mean(signal.astype(np.float64) ** 2) / np.mean(noise**2))


@pytest.mark.parametrize("target", [20.0, 10.0, 0.0])
def test_mix_hits_target_snr(target):
    rng = np.random.default_rng(1)
    signal = (0.1 * np.sin(np.linspace(0, 400 * np.pi, 16000))).astype(np.float32)
    noise = rng.standard_normal(16000).astype(np.float32)
    mixed = mix_at_snr(signal, noise, target)
    assert mixed.dtype == np.float32
    assert snr_db(signal, mixed) == pytest.approx(target, abs=0.1)


def test_mix_clips_to_valid_range_and_keeps_silence():
    loud = np.full(100, 0.9, dtype=np.float32)
    assert np.abs(mix_at_snr(loud, np.ones(100, np.float32), -10)).max() <= 1.0
    silence = np.zeros(100, dtype=np.float32)
    assert np.array_equal(mix_at_snr(silence, np.ones(100, np.float32), 10), silence)


def test_response_sentences_cover_demo_replies():
    sentences = response_sentences()
    assert len(sentences) == len(set(sentences)) == 23
    assert "후드를 켰습니다." in sentences
    assert "결제할까요?" in sentences
    assert any(s.startswith("지금은 튀김기를 제어할 수 없어요.") for s in sentences)
    assert "위험 상황이에요. 불을 확인해 주세요." in sentences
