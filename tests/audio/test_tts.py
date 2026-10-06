import pathlib

import numpy as np
import pytest

from common.bus import MemoryBus
from services.audio_svc.responses import RiskWatcher, _obj, reply_for_decision
from services.audio_svc.service import AudioService
from services.audio_svc.speaker import Speaker
from services.audio_svc.stt import Transcript
from services.audio_svc.tts import DEFAULT_TTS_MODEL_DIR, KoreanTts, clean
from services.audio_svc.vad import SpeechSegment

TTS_DIR = pathlib.Path(DEFAULT_TTS_MODEL_DIR)


def allow(call: dict) -> str | None:
    return reply_for_decision({"call": call, "decision": "ALLOW", "reason": ""})


@pytest.mark.parametrize(
    ("call", "text"),
    [
        ({"action": "TURN_ON", "target": "hood"}, "후드를 켰습니다."),
        ({"action": "TURN_OFF", "target": "burner_1"}, "1번 화구를 껐습니다."),
        ({"action": "TURN_OFF", "target": "all"}, "모두 껐습니다."),
        (
            {"action": "SET_LEVEL", "target": "burner_2", "level": 3},
            "2번 화구 세기를 강으로 바꿨습니다.",
        ),
        ({"action": "SET_TIMER", "duration_s": 180}, "3분 타이머를 맞췄습니다."),
        (
            {"action": "SET_TIMER", "duration_s": 210, "target": "burner_1"},
            "3분 30초 뒤에 1번 화구를 끕니다.",
        ),
        ({"action": "CANCEL_TIMER"}, "타이머를 취소했습니다."),
        ({"action": "EMERGENCY_STOP", "target": "all"}, "긴급 정지했습니다. 모든 장치를 껐습니다."),
        (
            {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": ["target"]},
            "어느 장치를 켤까요?",
        ),
        (
            {"action": "ASK_CLARIFY", "for_action": "SET_TIMER", "missing": ["duration"]},
            "몇 분으로 맞출까요?",
        ),
        ({"action": "ASK_CLARIFY", "for_action": None, "missing": []}, "네, 말씀하세요."),
        ({"action": "UNSUPPORTED"}, "그건 아직 할 수 없어요."),
        # 스키마 v0.2 (LLM-13)
        ({"action": "TURN_ON", "target": "fryer"}, "튀김기를 켰습니다."),
        ({"action": "TURN_OFF", "target": "aircon"}, "에어컨을 껐습니다."),
        ({"action": "SET_LEVEL", "target": "fan", "level": 1}, "선풍기 세기를 약으로 바꿨습니다."),
        ({"action": "SET_LEVEL", "target": "light", "level": 3}, "조명 밝기를 밝게 바꿨습니다."),
        ({"action": "SET_LEVEL", "target": "music", "level": 1}, "음악 음량을 작게 바꿨습니다."),
        (
            {"action": "SET_TIMER", "duration_s": 300, "target": "fryer"},
            "5분 뒤에 튀김기를 끕니다.",
        ),
        ({"action": "REQUEST_PAYMENT"}, "결제를 요청했습니다."),
        ({"action": "CHECK_AMOUNT"}, "금액 확인은 아직 준비 중이에요."),
        ({"action": "DENY"}, "알겠습니다. 취소했습니다."),
        ({"action": "CONFIRM"}, None),
    ],
)
def test_allowed_command_replies(call: dict, text: str | None) -> None:
    assert allow(call) == text


def test_reject_and_ask_replies() -> None:
    call = {"action": "TURN_ON", "target": "burner_1"}
    reject = {"call": call, "decision": "REJECT", "reason": "화구 온도가 너무 높아요."}
    assert (
        reply_for_decision(reject) == "지금은 1번 화구를 제어할 수 없어요. 화구 온도가 너무 높아요."
    )
    assert reply_for_decision({"call": call, "decision": "ASK", "reason": ""}) == (
        "정말 1번 화구를 제어할까요?"
    )
    pay = {"call": {"action": "REQUEST_PAYMENT"}, "decision": "ASK", "reason": ""}
    assert reply_for_decision(pay) == "결제할까요?"


def test_object_particle() -> None:
    assert [_obj(w) for w in ["후드", "화구", "물", "냄비"]] == [
        "후드를",
        "화구를",
        "물을",
        "냄비를",
    ]


def test_risk_warning_only_when_rising() -> None:
    w = RiskWatcher()
    said = [
        w.update({"risk": r})
        for r in ["none", "warn", "warn", "danger", "danger", "none", "danger"]
    ]
    assert said == [None, "주의하세요. 조리 상태를 확인해 주세요.", None,
                    "위험 상황이에요. 불을 확인해 주세요.", None, None,
                    "위험 상황이에요. 불을 확인해 주세요."]  # fmt: skip


def test_clean_removes_unspeakable_marks() -> None:
    assert clean(" 어느 장치를 켤까요? ") == "어느 장치를 켤까요."


class FakeTts:
    def synthesize(self, text: str):
        return np.zeros(22050, dtype=np.float32), 22050  # 1초


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_speaker_mutes_while_playing_and_saves(tmp_path: pathlib.Path) -> None:
    clock = FakeClock()
    muted_during_play = []

    def player(samples, rate):
        muted_during_play.append(speaker.is_muted(clock.t + 0.5))  # 재생 중간
        clock.t += 1.0  # 1초 재생

    speaker = Speaker(
        FakeTts(), play=True, out_dir=tmp_path, tail_s=0.3, player=player, clock=clock
    )
    speaker.say("후드를 켰습니다.")
    speaker.close()
    assert speaker.spoken == ["후드를 켰습니다."]
    assert muted_during_play == [True]
    assert speaker.is_muted(clock.t + 0.2)  # 끝난 뒤 tail_s 안
    assert not speaker.is_muted(clock.t + 0.4)
    assert len(list(tmp_path.glob("tts_*.wav"))) == 1


def test_speaker_without_playback_never_mutes() -> None:
    speaker = Speaker(FakeTts(), play=False, player=lambda *a: pytest.fail("재생하면 안 됨"))
    speaker.say("후드를 켰습니다.")
    speaker.close()
    assert not speaker.is_muted()


class RecordingSegmenter:
    def __init__(self) -> None:
        self.fed: list[np.ndarray] = []

    def feed(self, samples, arrival_mono) -> list[SpeechSegment]:
        self.fed.append(samples)
        return []

    def flush(self) -> list[SpeechSegment]:
        return []


class NoStt:
    def transcribe(self, samples, sample_rate) -> Transcript:
        raise AssertionError("구간이 없으니 불리면 안 됨")


def test_audio_service_feeds_silence_while_muted() -> None:
    seg = RecordingSegmenter()
    service = AudioService(NoStt(), seg, MemoryBus(), "s", 1e9, mute=lambda t: 1.0 <= t < 2.0)
    loud = np.ones(1600, dtype=np.float32)
    service.run([(loud, 0.5), (loud, 1.5), (loud, 2.5)])
    assert [float(c.max()) for c in seg.fed] == [1.0, 0.0, 1.0]
    assert all(len(c) == 1600 for c in seg.fed)  # 길이는 그대로 (시각 계산 유지)


@pytest.mark.skipif(not (TTS_DIR / "tokens.txt").is_file(), reason="TTS 모델 없음")
def test_real_tts_synthesizes() -> None:
    """모델이 있을 때만. 발음 정확도는 합성마다 달라 여기서 보지 않는다 (README)."""
    samples, rate = KoreanTts(TTS_DIR).synthesize("후드를 켰습니다?")
    assert rate == 22050
    assert 0.5 < len(samples) / rate < 3
    assert np.abs(samples).max() > 0.05
