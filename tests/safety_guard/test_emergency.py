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
        ("자비스 기름에 불 났어", True),  # 불이 났다는 말 (#164)
        ("자비스, 팬에 불 붙었어!", True),
        ("자비스 냄비에 불붙었어", True),
        ("자비스 타이머 쪽에 불났어", True),  # 타이머 말이 섞여도 불은 긴급
        ("불이야!", False),
        ("불났어!", False),
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
        ("자비스 불 꺼 줘", True),  # 조명 (#164: 불 + 끄기는 긴급 아님)
        ("자비스 불 켜 줘", True),
        ("자비스 1번 화구 불 붙여 줘", True),  # 점화 요청
        ("어제 옆 가게에 불 났대", False),  # 호출어 없는 대화
    ],
)
def test_not_emergency(text: str, wake: bool) -> None:
    assert not is_emergency(text, wake)


@pytest.mark.parametrize(
    "text",
    ["자비스 음악 멈춰", "자비스 선풍기 정지", "자비스 노래 그만 틀어", "자비스 에어컨 멈춰 줘"],
)
def test_store_device_stop_is_not_emergency(text: str) -> None:
    """매장 장치를 멈추라는 말은 그 장치 끄기다 (스키마 v0.2). 화구까지 끄는 긴급 정지가 아니다."""
    assert not is_emergency(text, wake=True)


def test_heater_or_plain_stop_is_still_emergency() -> None:
    assert is_emergency("자비스 1번 화구 멈춰", wake=True)
    assert is_emergency("자비스 다 멈춰", wake=True)
