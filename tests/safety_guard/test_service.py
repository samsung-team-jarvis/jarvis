from common.bus import MemoryBus
from common.kitchen_link import validate_command
from common.messages import Envelope
from services.safety_guard.service import CONFIRM_TIMEOUT_S, EMERGENCY_DEDUP_S, SafetyGuard


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def setup(assume_state: str | None = None):
    bus, clock = MemoryBus(), FakeClock()
    got: dict[str, list[Envelope]] = {"guard/decision": [], "control/command": []}
    for topic, msgs in got.items():
        bus.subscribe(topic, msgs.append)
    guard = SafetyGuard(bus, "s_guard", assume_state=assume_state, clock=clock)
    guard.start()
    return bus, guard, got, clock


def call_msg(call: dict, session: str = "s_voice") -> Envelope:
    payload = {"call": call, "raw_text": "", "valid": True, "fallback": True, "gen_ms": 0.1,
               "tokens": 0}  # fmt: skip
    return Envelope.new("llm/function_call", "llm_svc", payload, session)


def state_msg(state: str) -> Envelope:
    payload = {"state": state, "prev_state": "IDLE", "evidence": {}, "risk": "none"}
    return Envelope.new("fusion/state", "fusion_svc", payload, "s_fusion")


def stt_msg(text: str, wake: bool) -> Envelope:
    payload = {"text": text, "wake": wake, "audio_ms": 800, "stt_ms": 50, "speech_end_mono": 1.0}
    return Envelope.new("stt/text", "audio_svc", payload, "s_voice")


def test_hood_on_allowed_and_commanded_even_without_state() -> None:
    """Gate 2: "자비스, 후드 켜줘" → 허용 → control/command (상황 인식이 없어도)."""
    bus, _, got, _ = setup()
    bus.publish(call_msg({"action": "TURN_ON", "target": "hood"}))

    d = got["guard/decision"][0]
    assert d.payload == {"call": {"action": "TURN_ON", "target": "hood"}, "decision": "ALLOW",
                         "reason": ""}  # fmt: skip
    assert d.session_id == "s_voice" and d.source == "safety_guard"
    c = got["control/command"][0]
    assert c.payload == {"seq": 1, "cmd": "ON", "target": "hood", "value": 1}
    assert c.session_id == "s_voice"


def test_burner_on_follows_latest_state() -> None:
    bus, _, got, _ = setup()
    burner = {"action": "TURN_ON", "target": "burner_1"}

    bus.publish(call_msg(burner))  # 상태 모름 → 거부
    bus.publish(state_msg("COOKING"))
    bus.publish(call_msg(burner))  # 조리 중 → 허용
    bus.publish(state_msg("DANGER"))
    bus.publish(call_msg(burner))  # 위험 → 거부

    assert [m.payload["decision"] for m in got["guard/decision"]] == ["REJECT", "ALLOW", "REJECT"]
    assert len(got["control/command"]) == 1  # 거부된 명령은 장치로 가지 않는다


def test_assume_state_for_development() -> None:
    bus, _, got, _ = setup(assume_state="COOKING")
    bus.publish(call_msg({"action": "SET_LEVEL", "target": "burner_2", "level": 2}))
    assert got["control/command"][0].payload == {"seq": 1, "cmd": "LEVEL",
                                                 "target": "burner_2", "value": 2}  # fmt: skip


def test_unknown_state_name_is_ignored() -> None:
    bus, guard, _, _ = setup(assume_state="COOKING")
    bus.publish(state_msg("ON_FIRE"))
    assert guard.state == "COOKING"


def test_non_control_actions_are_decided_but_not_commanded() -> None:
    bus, _, got, _ = setup()
    for call in ({"action": "CHECK_RISK"}, {"action": "UNSUPPORTED"},
                 {"action": "SET_TIMER", "duration_s": 60}):  # fmt: skip
        bus.publish(call_msg(call))
    assert [m.payload["decision"] for m in got["guard/decision"]] == ["ALLOW"] * 3
    assert got["control/command"] == []


def test_invalid_call_rejected() -> None:
    bus, _, got, _ = setup(assume_state="COOKING")
    bus.publish(call_msg({"action": "TURN_ON", "target": "oven"}))
    assert got["guard/decision"][0].payload["decision"] == "REJECT"
    assert got["control/command"] == []


def test_emergency_fast_path_skips_command_interpretation() -> None:
    bus, guard, got, _ = setup()
    bus.publish(stt_msg("멈춰!", wake=False))

    assert got["guard/decision"][0].payload["call"] == {"action": "EMERGENCY_STOP", "target": "all"}
    assert got["control/command"][0].payload == {"seq": 1, "cmd": "OFF",
                                                 "target": "all", "value": 0}  # fmt: skip
    assert guard.counts["fast_path"] == 1


def test_emergency_from_interpreter_after_fast_path_is_not_repeated() -> None:
    bus, guard, got, clock = setup()
    bus.publish(stt_msg("자비스 멈춰", wake=True))  # 빠른 경로
    clock.now += 0.5
    bus.publish(call_msg({"action": "EMERGENCY_STOP", "target": "all"}))  # 같은 말을 해석한 결과

    assert len(got["control/command"]) == 1 and guard.counts["duplicate"] == 1

    clock.now += EMERGENCY_DEDUP_S + 1  # 한참 뒤 다시 말하면 새 요청
    bus.publish(call_msg({"action": "EMERGENCY_STOP", "target": "all"}))
    assert len(got["control/command"]) == 2


def test_ordinary_speech_does_not_trigger_fast_path() -> None:
    bus, _, got, _ = setup()
    bus.publish(stt_msg("자비스 후드 켜 줘", wake=True))
    assert got["guard/decision"] == []  # 일반 명령은 명령 해석 결과(llm/function_call)를 기다린다


def test_voice_to_control_with_llm_svc() -> None:
    """Gate 2 경로 중 보드 안쪽: stt/text → llm_svc(규칙 파서) → safety_guard → control/command."""
    from services.llm_svc.service import LlmService

    bus, _, got, _ = setup()
    LlmService(bus, "s_llm").start()

    bus.publish(stt_msg("자비스, 후드 켜 줘.", wake=True))
    bus.publish(stt_msg("자비스 1번 화구 켜 줘", wake=True))  # 상태 모름 → 거부

    assert [m.payload["decision"] for m in got["guard/decision"]] == ["ALLOW", "REJECT"]
    assert [m.payload["target"] for m in got["control/command"]] == ["hood"]


def test_seq_increases_per_command() -> None:
    bus, _, got, _ = setup()
    bus.publish(call_msg({"action": "TURN_ON", "target": "hood"}))
    bus.publish(call_msg({"action": "TURN_OFF", "target": "hood"}))
    assert [m.payload["seq"] for m in got["control/command"]] == [1, 2]


def test_control_command_follows_kitchen_link_spec() -> None:
    """control/command는 kitchen_gw가 받는 규격(interfaces §2, HW-14)이어야 한다."""
    bus, _, got, _ = setup(assume_state="COOKING")
    for call in ({"action": "TURN_ON", "target": "fryer"},
                 {"action": "SET_LEVEL", "target": "light", "level": 1},
                 {"action": "TURN_OFF", "target": "all"},
                 {"action": "EMERGENCY_STOP", "target": "all"}):  # fmt: skip
        bus.publish(call_msg(call))
    for m in got["control/command"]:
        validate_command(m.payload)
    assert [m.payload["cmd"] for m in got["control/command"]] == ["ON", "LEVEL", "OFF", "OFF"]


def test_fryer_rejected_in_danger() -> None:
    bus, _, got, _ = setup()
    bus.publish(state_msg("DANGER"))
    bus.publish(call_msg({"action": "TURN_ON", "target": "fryer"}))
    assert got["guard/decision"][0].payload["decision"] == "REJECT"
    assert got["control/command"] == []


PAY = {"action": "REQUEST_PAYMENT"}


def test_payment_asks_then_confirm_allows() -> None:
    bus, guard, got, clock = setup()
    bus.publish(call_msg(PAY))
    assert got["guard/decision"][0].payload["decision"] == "ASK"

    clock.now += 2
    bus.publish(call_msg({"action": "CONFIRM"}))
    d = got["guard/decision"][1].payload
    assert (d["call"], d["decision"]) == (PAY, "ALLOW")  # 응답: "결제를 요청했습니다."
    assert got["control/command"] == []  # 결제 실행 연결은 HW-23
    assert guard.pending is None


def test_payment_deny_cancels() -> None:
    bus, _, got, _ = setup()
    bus.publish(call_msg(PAY))
    bus.publish(call_msg({"action": "DENY"}))
    d = got["guard/decision"][1].payload
    assert (d["call"], d["decision"]) == (
        {"action": "DENY"},
        "ALLOW",
    )  # "알겠습니다. 취소했습니다."
    bus.publish(call_msg({"action": "CONFIRM"}))  # 이미 끝난 질문
    assert got["guard/decision"][2].payload["decision"] == "REJECT"


def test_confirm_after_timeout_is_rejected() -> None:
    bus, _, got, clock = setup()
    bus.publish(call_msg(PAY))
    clock.now += CONFIRM_TIMEOUT_S + 0.1
    bus.publish(call_msg({"action": "CONFIRM"}))
    assert [m.payload["decision"] for m in got["guard/decision"]] == ["ASK", "REJECT"]


def test_other_command_drops_pending_question() -> None:
    bus, guard, got, _ = setup()
    bus.publish(call_msg(PAY))
    bus.publish(call_msg({"action": "TURN_ON", "target": "hood"}))
    assert guard.pending is None
    bus.publish(call_msg({"action": "CONFIRM"}))
    assert got["guard/decision"][-1].payload["decision"] == "REJECT"


def test_reply_without_wake_word_while_waiting() -> None:
    bus, _, got, _ = setup()
    bus.publish(stt_msg("네.", wake=False))  # 기다리는 질문이 없으면 그냥 대화
    assert got["guard/decision"] == []

    bus.publish(call_msg(PAY))
    bus.publish(stt_msg("오늘 손님 많네", wake=False))  # 대답이 아닌 말은 무시하고 계속 기다린다
    assert len(got["guard/decision"]) == 1
    bus.publish(stt_msg("네!", wake=False))
    d = got["guard/decision"][1].payload
    assert (d["call"], d["decision"]) == (PAY, "ALLOW")


def test_emergency_drops_pending_payment() -> None:
    bus, guard, got, _ = setup()
    bus.publish(call_msg(PAY))
    bus.publish(stt_msg("멈춰!", wake=False))
    assert guard.pending is None
    bus.publish(stt_msg("네", wake=False))
    assert [m.payload["decision"] for m in got["guard/decision"]] == ["ASK", "ALLOW"]


def test_payment_voice_flow_with_llm_svc() -> None:
    """자비스 결제해 줘 → ASK → 자비스 네 → 결제 허용 (호출어 있는 대답은 명령 해석을 거친다)."""
    from services.llm_svc.service import LlmService

    bus, _, got, _ = setup()
    LlmService(bus, "s_llm").start()
    bus.publish(stt_msg("자비스 결제해 줘", wake=True))
    bus.publish(stt_msg("자비스 네", wake=True))
    decided = [(m.payload["call"]["action"], m.payload["decision"]) for m in got["guard/decision"]]
    assert decided == [("REQUEST_PAYMENT", "ASK"), ("REQUEST_PAYMENT", "ALLOW")]
