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
        # 사람 음성 실제 출력 (2026-10-02, MacBook 마이크) — 첫 자음 오인식 (#57)
        ("다비스 후드 켜줘.", "후드 켜줘."),
        ("다비스 타이머 3분 맞춰줘.", "타이머 3분 맞춰줘."),
        ("바비스 긴급정지 아 물어볼까?", "긴급정지 아 물어볼까?"),
        ("차비스.", ""),  # 합성 음성 출력
        # spk01 val: "자비스야"에서 '스'가 빠지거나 띄어진 형태 (#61)
        ("자비야 이번 불 켜줘.", "이번 불 켜줘."),
        ("자비 쓰야.", ""),
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
        "다비 이번 화구 꺼줘.",  # '스'까지 빠지면 호출 아님 (사람 음성 실제 출력)
        "서비스 좋네",  # 흔한 말 — 첫 글자 모음이 ㅏ가 아님
        "바비큐 하자",
        "잡비야 후드 켜줘",  # 합성 음성 출력, 아직 허용 안 함
        "자비",
        "",
    ],
)
def test_non_wake_utterance(text: str) -> None:
    assert split_wake(text) is None
    assert not is_wake(text)


def test_custom_wake_words() -> None:
    assert split_wake("짜비스 후드 켜", wake_words=("자비스",)) is None
    assert split_wake("짜비스 후드 켜") == "후드 켜"
