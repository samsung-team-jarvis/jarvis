"""발화 구간 앞여유 (#128): VAD가 늦게 잡은 첫 음절을 남겨 둔 오디오에서 붙인다."""

import numpy as np

from services.audio_svc.vad import with_pre_roll


def test_segment_gets_audio_before_its_start() -> None:
    history = np.arange(100, dtype=np.float32)  # 샘플 번호 1000~1099
    out = with_pre_roll(history, 1000, start=1050, length=20, pre_roll=10)
    assert out.tolist() == list(range(40, 70))  # 1040~1069


def test_pre_roll_stops_at_the_oldest_kept_sample() -> None:
    history = np.arange(100, dtype=np.float32)
    out = with_pre_roll(history, 1000, start=1005, length=10, pre_roll=30)
    assert out.tolist() == list(range(0, 15))  # 1000~1014 (그 앞은 버렸다)
