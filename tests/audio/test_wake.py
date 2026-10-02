import pytest

from services.audio_svc.wake import is_wake, split_wake


@pytest.mark.parametrize(
    ("text", "command"),
    [
        ("자비스 후드 켜 줘.", "후드 켜 줘."),
        (" 자비스, 긴급 정지", "긴급 정지"),
        ('"자비스" 후드', "후드"),
        # SenseVoice가 "자비스야"를 띄어 받아쓴 실제 출력 (Mac, 합성 음성)
        ("자비 스야 후드 켜 줘.", "후드 켜 줘."),
        ("자비스아 불 꺼", "불 꺼"),
        ("자비스야채 썰어", "야채 썰어"),  # '야'가 단어의 일부면 남긴다
        ("자비스.", ""),  # 호출만
        ("자비스야", ""),
    ],
)
def test_wake_utterance_gives_command_part(text: str, command: str) -> None:
    assert split_wake(text) == command
    assert is_wake(text)


@pytest.mark.parametrize(
    "text",
    [
        "저기 자비스 후드 켜 줘.",  # Q-08 v0: 시작할 때만
        "오늘 저녁 뭐 먹지?",
        "차비스.",  # 오인식 후보 — STT-05에서 확인 전까지는 허용하지 않음
        "자비",
        "",
    ],
)
def test_non_wake_utterance(text: str) -> None:
    assert split_wake(text) is None
    assert not is_wake(text)


def test_custom_wake_words() -> None:
    assert split_wake("차비스 후드 켜", wake_words=("자비스", "차비스")) == "후드 켜"
