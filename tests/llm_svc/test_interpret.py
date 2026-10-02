import pytest

from services.llm_svc.interpret import command_text, interpret
from services.llm_svc.stt_fixes import normalize


@pytest.mark.parametrize(
    ("wrong", "right"),
    [
        ("타임머 취소해줘.", "타이머 취소해줘."),
        ("이번화구 세개.", "이번화구 세게."),
        ("십 분 뒤에 일 번구 꺼죠.", "십 분 뒤에 일 번 화구 꺼죠."),
        ("일본 번 화국 켜줘.", "일번 화국 켜줘."),
        ("후드 켜줘.", "후드 켜줘."),  # 고칠 것 없음
    ],
)
def test_normalize(wrong: str, right: str) -> None:
    assert normalize(wrong) == right


# spk01 val 녹음의 실제 SenseVoice 출력 (MacBook 마이크, 2026-10-02) — 사전·호출어 형태로 맞게 된 것
@pytest.mark.parametrize(
    ("stt", "call"),
    [
        ("자비스 타임머 취소해줘.", {"action": "CANCEL_TIMER"}),
        ("자비스 이번화구 세개.", {"action": "SET_LEVEL", "target": "burner_2", "level": 3}),
        ("자비스 십 분 뒤에 일 번구 꺼죠.",
         {"action": "SET_TIMER", "duration_s": 600, "target": "burner_1"}),
        ("자비스 일본 번 화국 켜줘.", {"action": "TURN_ON", "target": "burner_1"}),
        ("자비야 이번 불 켜줘.", {"action": "TURN_ON", "target": "burner_2"}),
        ("자비 쓰야.", {"action": "ASK_CLARIFY", "for_action": None, "missing": []}),
    ],
)  # fmt: skip
def test_interpret_real_outputs(stt: str, call: dict) -> None:
    assert interpret(stt) == call


def test_no_wake_is_not_a_command() -> None:
    assert interpret("타임머 취소해줘") is None
    assert command_text("오늘 저녁 뭐 먹지?") is None
    assert command_text("자비스 타임머 꺼") == "타이머 꺼"
