import pytest

from services.llm_svc.interpret import command_text, interpret, resolve
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


class FakeLLM:
    """정해 둔 출력을 내는 생성기. 받은 입력을 기록한다."""

    def __init__(self, raw: str, tokens: int = 7) -> None:
        self.raw, self.tokens, self.seen = raw, tokens, []

    def __call__(self, text: str, context: dict) -> tuple[str, int]:
        self.seen.append((text, context))
        return self.raw, self.tokens


CTX = {"state": "COOKING", "last_target": None}


def test_resolve_uses_valid_llm_output() -> None:
    llm = FakeLLM("<jarvis_3>(target=hood, level=2)<jarvis_end>")
    r = resolve("환풍기 중간으로.", CTX, llm)
    assert r.call == {"action": "SET_LEVEL", "target": "hood", "level": 2}
    assert (r.raw_text, r.valid, r.fallback, r.tokens) == (llm.raw, True, False, 7)
    assert llm.seen == [("환풍기 중간으로", CTX)]  # 문장부호를 빼고 넣는다 (학습 문장과 같게)


@pytest.mark.parametrize(
    "raw",
    [
        "<jarvis_1>(target=volume)<jarvis_end>",  # 없는 장치 이름
        "<jarvis_4>(min=90)<jarvis_end>",  # 범위 밖 (타이머 최대 60분)
        "<jarvis_3>(target=hood)<jarvis_end>",  # 꼭 필요한 인자(level)가 빠짐
        "<jarvis_99>()<jarvis_end>",  # 없는 함수
        "후드를 켭니다",  # 함수 토큰 형식이 아님
        "",
    ],
)
def test_resolve_falls_back_to_rule_parser_when_llm_output_invalid(raw: str) -> None:
    r = resolve("후드 켜 줘.", CTX, FakeLLM(raw))
    assert r.call == {"action": "TURN_ON", "target": "hood"}  # 규칙 파서 결과
    assert (r.raw_text, r.valid, r.fallback, r.tokens) == ("후드 켜 줘.", False, True, 7)


def test_resolve_out_of_range_timer_falls_back_to_asking() -> None:
    r = resolve("타이머 90분 맞춰줘", CTX, FakeLLM("<jarvis_4>(min=90)<jarvis_end>"))
    assert r.fallback and r.call["action"] == "ASK_CLARIFY"  # 규칙 파서가 시간을 되묻는다


def test_resolve_without_llm_is_rule_parser() -> None:
    r = resolve("후드 켜 줘.", CTX)
    assert r.call == {"action": "TURN_ON", "target": "hood"}
    assert (r.raw_text, r.valid, r.fallback, r.tokens) == ("후드 켜 줘.", True, True, 0)


def test_wake_word_only_is_not_sent_to_llm() -> None:
    llm = FakeLLM("<jarvis_1>(target=hood)<jarvis_end>")
    r = resolve(".", CTX, llm)
    assert llm.seen == [] and r.call == {"action": "ASK_CLARIFY", "for_action": None, "missing": []}
