import pytest

from services.safety_guard.emergency import is_emergency


@pytest.mark.parametrize(
    ("text", "wake"),
    [
        ("자비스 멈춰!", True),
        ("자비스, 긴급 정지.", True),
        ("자비스 그만 그만", True),
        ("자비스 큰일 났어 비상이야", True),
        ("멈춰!", False),  # 다급하면 호출어를 빼고 말한다
        ("그만 그만.", False),
        ("긴급 정지", False),
        ("스톱", False),
    ],
)
def test_emergency(text: str, wake: bool) -> None:
    assert is_emergency(text, wake)


@pytest.mark.parametrize(
    ("text", "wake"),
    [
        ("자비스 타이머 정지", True),  # 타이머 취소 (명령 해석이 맡는다)
        ("자비스 알람 그만", True),
        ("자비스 지금 위험해?", True),  # 위험 확인
        ("자비스 후드 꺼 줘", True),
        ("그만 먹을래", False),  # 호출어 없는 대화 속 긴급어
        ("이제 멈춰야겠다", False),
        ("오늘 저녁 뭐 먹지", False),
    ],
)
def test_not_emergency(text: str, wake: bool) -> None:
    assert not is_emergency(text, wake)
