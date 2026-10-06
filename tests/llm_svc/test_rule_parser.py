import pytest

from common.function_call import validate
from services.llm_svc.rule_parser import duration_s, korean_number, parse


def ask(for_action, *missing):
    return {"action": "ASK_CLARIFY", "for_action": for_action, "missing": list(missing)}


CASES = [
    # SenseVoice 실제 출력 (Mac, 합성 음성 — audio_svc README·PR #34/#36)
    ("후드 켜 줘.", {"action": "TURN_ON", "target": "hood"}),
    ("2 화국 꺼줘.", {"action": "TURN_OFF", "target": "burner_2"}),
    ("타이머 3분 맞춰줘.", {"action": "SET_TIMER", "duration_s": 180}),
    ("긴급 정지.", {"action": "EMERGENCY_STOP", "target": "all"}),
    ("불꺼줘.", ask("TURN_OFF", "target")),
    # 켜기·끄기·장치
    ("1번 화구 켜", {"action": "TURN_ON", "target": "burner_1"}),
    ("두 번째 불 꺼 줘", {"action": "TURN_OFF", "target": "burner_2"}),
    ("화구 1번 켜 줘", {"action": "TURN_ON", "target": "burner_1"}),
    ("환풍기 틀어 줘", {"action": "TURN_ON", "target": "hood"}),
    ("다 꺼 줘", {"action": "TURN_OFF", "target": "all"}),
    ("다 켜 줘", ask("TURN_ON", "target")),  # 모두 켜기는 지원 안 함
    ("3번 화구 켜", ask("TURN_ON", "target")),  # 없는 화구
    # 세기
    ("후드 세게", {"action": "SET_LEVEL", "target": "hood", "level": 3}),
    ("2번 화구 약하게 해줘", {"action": "SET_LEVEL", "target": "burner_2", "level": 1}),
    ("후드 2단", {"action": "SET_LEVEL", "target": "hood", "level": 2}),
    ("1번 불 중간으로", {"action": "SET_LEVEL", "target": "burner_1", "level": 2}),
    ("후드 조금 더", ask("SET_LEVEL", "level")),  # 상대 조절은 v0에서 되묻기
    ("세게 해 줘", ask("SET_LEVEL", "target")),
    ("불 좀 약하게", ask("SET_LEVEL", "target")),
    # 타이머
    ("3분 뒤에 1번 화구 꺼 줘", {"action": "SET_TIMER", "target": "burner_1", "duration_s": 180}),
    ("타이머 삼 분 삼십 초", {"action": "SET_TIMER", "duration_s": 210}),
    ("타이머 1분 반", {"action": "SET_TIMER", "duration_s": 90}),
    ("타이머 열다섯 분", {"action": "SET_TIMER", "duration_s": 900}),
    ("타이머 맞춰 줘", ask("SET_TIMER", "duration")),
    ("타이머 90분 맞춰줘", ask("SET_TIMER", "duration")),  # 최대 60분 초과
    # 띄어쓰기를 지우면 "화구"의 '구'가 숫자에 붙던 버그 (#67)
    ("2번 화구 이십 분 뒤에 꺼", {"action": "SET_TIMER", "target": "burner_2", "duration_s": 1200}),
    (
        "첫 번째 화구 사십오 초만 켜 두고 꺼줘",
        {"action": "SET_TIMER", "target": "burner_1", "duration_s": 45},
    ),
    ("타이머 취소", {"action": "CANCEL_TIMER"}),
    ("타이머 정지", {"action": "CANCEL_TIMER"}),  # 긴급 정지가 아니라 타이머 끄기
    ("후드 타이머 꺼", {"action": "CANCEL_TIMER", "target": "hood"}),
    # 확인
    ("1번 화구 켜져 있어?", {"action": "CHECK_STATUS", "target": "burner_1"}),
    ("후드 어때?", {"action": "CHECK_STATUS", "target": "hood"}),
    ("상태 알려줘", {"action": "CHECK_STATUS"}),
    ("지금 위험해?", {"action": "CHECK_RISK"}),
    # 긴급
    ("멈춰", {"action": "EMERGENCY_STOP", "target": "all"}),
    ("그만!", {"action": "EMERGENCY_STOP", "target": "all"}),
    # 의도 불명·지원 외
    ("", ask(None)),  # 호출어만 말함
    ("후드", ask(None)),
    ("오늘 날씨 어때?", {"action": "UNSUPPORTED"}),
    ("냉장고 문 닫았어?", {"action": "UNSUPPORTED"}),
    # 한계: 모르는 대상 + 켜기 동사는 장치를 되묻는다 (LLM과 비교할 지점, FUS-06)
    ("커피 머신 켜 줘", ask("TURN_ON", "target")),
    # 스키마 v0.2 — 새 장치 (LLM-13)
    ("튀김기 켜 줘", {"action": "TURN_ON", "target": "fryer"}),
    ("튀김기 세게", {"action": "SET_LEVEL", "target": "fryer", "level": 3}),
    ("튀김기 5분 뒤에 꺼 줘", {"action": "SET_TIMER", "target": "fryer", "duration_s": 300}),
    ("조명 켜줘", {"action": "TURN_ON", "target": "light"}),
    ("조명 좀 어둡게 해줘", {"action": "SET_LEVEL", "target": "light", "level": 1}),
    (
        "불빛 밝게",
        {"action": "SET_LEVEL", "target": "light", "level": 3},
    ),  # '불'이 화구로 읽히지 않는다
    ("에어컨 꺼줘", {"action": "TURN_OFF", "target": "aircon"}),
    ("에어컨 켜져 있어?", {"action": "CHECK_STATUS", "target": "aircon"}),
    ("에어컨 10분 뒤에 꺼 줘", {"action": "UNSUPPORTED"}),  # 타이머는 가열 장치·후드에만
    ("선풍기 약하게", {"action": "SET_LEVEL", "target": "fan", "level": 1}),
    ("선풍기 정지", {"action": "TURN_OFF", "target": "fan"}),  # 긴급 정지가 아니라 선풍기 끄기
    ("노래 틀어 줘", {"action": "TURN_ON", "target": "music"}),
    ("음악 멈춰", {"action": "TURN_OFF", "target": "music"}),
    ("소리 크게 해 줘", {"action": "SET_LEVEL", "target": "music", "level": 3}),
    ("볼륨 줄여 줘", ask("SET_LEVEL", "level")),  # 상대 조절은 되묻기
    ("환풍기 세게", {"action": "SET_LEVEL", "target": "hood", "level": 3}),  # 환풍기 = 후드
    ("전부 정지", {"action": "EMERGENCY_STOP", "target": "all"}),
    # 결제 — 금액은 말로 받지 않는다
    ("얼마야?", {"action": "CHECK_AMOUNT"}),
    ("결제 금액 확인해 줘", {"action": "CHECK_AMOUNT"}),
    ("결제해 줘", {"action": "REQUEST_PAYMENT"}),
    ("카드로 계산해 줘", {"action": "REQUEST_PAYMENT"}),
    ("결제 취소", {"action": "DENY"}),
    ("칼로리 계산해 줘", {"action": "UNSUPPORTED"}),  # 문장 맨 앞의 "계산"만 결제로 본다
    # 확인에 대한 답 — 그 말만 했을 때
    ("네", {"action": "CONFIRM"}),
    ("그래요.", {"action": "CONFIRM"}),
    ("아니요", {"action": "DENY"}),
    ("취소", {"action": "DENY"}),
    ("아니 후드 꺼", {"action": "TURN_OFF", "target": "hood"}),  # 다른 말이 붙으면 그 명령
]


@pytest.mark.parametrize(("text", "call"), CASES)
def test_parse(text: str, call: dict) -> None:
    result = parse(text)
    assert result == call
    validate(result)


@pytest.mark.parametrize(
    ("word", "n"),
    [("3", 3), ("삼", 3), ("십", 10), ("십오", 15), ("이십오", 25), ("삼십", 30),
     ("한", 1), ("열", 10), ("열다섯", 15), ("스무", 20), ("서른두", 32), ("뭐", None),
     ("구이십", None), ("이삼십", None)],
)  # fmt: skip
def test_korean_number(word: str, n: int | None) -> None:
    assert korean_number(word) == n


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("3분", 180), ("3분30초", 210), ("1분반", 90), ("삼십초", 30), ("후드켜", None)],
)
def test_duration(text: str, seconds: int | None) -> None:
    assert duration_s(text) == seconds
