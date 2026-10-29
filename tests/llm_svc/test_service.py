import threading

from common.bus import MemoryBus
from common.messages import Envelope
from services.llm_svc.service import LlmService


def stt(text: str, wake: bool, session: str = "s_test") -> Envelope:
    payload = {"text": text, "wake": wake, "audio_ms": 1000, "stt_ms": 40, "speech_end_mono": 1.0}
    return Envelope.new("stt/text", "audio_svc", payload, session)


def test_wake_utterance_becomes_function_call() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    service = LlmService(bus, "s_llm")
    service.start()

    bus.publish(stt("자비 스야 후드 켜 줘.", wake=True, session="s_voice"))

    assert len(got) == 1
    msg = got[0]
    assert msg.source == "llm_svc"
    assert msg.session_id == "s_voice"  # 받은 발화의 세션을 이어 쓴다 (지연 추적)
    p = msg.payload
    assert p["call"] == {"action": "TURN_ON", "target": "hood"}
    assert p["raw_text"] == "후드 켜 줘."  # 호출어를 뺀, 파서에 넣은 문장
    assert (p["valid"], p["fallback"], p["tokens"]) == (True, True, 0)
    assert p["gen_ms"] >= 0


def test_non_wake_utterance_is_ignored() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    service = LlmService(bus, "s_llm")
    service.start()

    bus.publish(stt("오늘 저녁 뭐 먹지?", wake=False))

    assert got == [] and service.ignored == 1


def test_wake_only_asks_back() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    LlmService(bus, "s_llm").start()

    bus.publish(stt("자비스.", wake=True))

    assert got[0].payload["call"] == {"action": "ASK_CLARIFY", "for_action": None, "missing": []}


def test_stt_fixes_applied_before_parsing() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    LlmService(bus, "s_llm").start()

    bus.publish(stt("자비스 타임머 취소해줘.", wake=True))

    assert got[0].payload["call"] == {"action": "CANCEL_TIMER"}
    assert got[0].payload["raw_text"] == "타이머 취소해줘."  # 파서가 본 문장 (원문은 stt/text에)


def state(name: str) -> Envelope:
    payload = {"state": name, "prev_state": "IDLE", "evidence": {}, "risk": "none"}
    return Envelope.new("fusion/state", "fusion_svc", payload, "s_fusion")


def test_llm_output_is_published_with_latest_state_as_context() -> None:
    bus, got, seen = MemoryBus(), [], []

    def llm(text: str, context: dict) -> tuple[str, int]:
        seen.append((text, context))
        return "<jarvis_3>(target=burner_1, level=1)<jarvis_end>", 9

    bus.subscribe("llm/function_call", got.append)
    LlmService(bus, "s_llm", generate=llm).start()
    bus.publish(state("COOKING"))

    bus.publish(stt("자비스 일번 불 약하게.", wake=True))

    assert seen == [("일번 불 약하게", {"state": "COOKING", "last_target": None})]
    p = got[0].payload
    assert p["call"] == {"action": "SET_LEVEL", "target": "burner_1", "level": 1}
    assert p["raw_text"] == "<jarvis_3>(target=burner_1, level=1)<jarvis_end>"  # LLM 출력
    assert (p["valid"], p["fallback"], p["tokens"]) == (True, False, 9)


def test_invalid_llm_output_falls_back_to_rule_parser() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    service = LlmService(
        bus, "s_llm", generate=lambda t, c: ("<jarvis_1>(target=sonar)<jarvis_end>", 8)
    )
    service.start()

    bus.publish(stt("자비스 후드 켜 줘.", wake=True))

    p = got[0].payload
    assert p["call"] == {"action": "TURN_ON", "target": "hood"}
    assert p["raw_text"] == "후드 켜 줘."  # 규칙 파서에 넣은 문장
    assert (p["valid"], p["fallback"], p["tokens"]) == (False, True, 8)
    assert service.fallbacks == 1


def test_state_defaults_to_idle_before_any_fusion_state() -> None:
    bus, seen = MemoryBus(), []
    LlmService(bus, "s_llm", generate=lambda t, c: (seen.append(c) or "", 0)).start()
    bus.publish(stt("자비스 후드 켜 줘.", wake=True))
    assert seen == [{"state": "IDLE", "last_target": None}]


def test_background_worker_keeps_the_subscriber_free() -> None:
    bus, got = MemoryBus(), []
    bus.subscribe("llm/function_call", got.append)
    release = threading.Event()

    def slow_llm(text, context):
        release.wait(5)  # 생성 중
        return "<jarvis_1>(target=hood)<jarvis_end>", 7

    service = LlmService(bus, "s_llm", generate=slow_llm, background=True)
    service.start()

    # 구독 핸들러는 생성을 기다리지 않고 바로 돌아온다
    bus.publish(stt("자비스 후드 켜 줘.", wake=True))
    bus.publish(stt("자비스 후드 켜 줘.", wake=True))
    assert got == []
    release.set()
    service.wait_idle()

    assert [m.payload["call"] for m in got] == [{"action": "TURN_ON", "target": "hood"}] * 2
    assert service.published == 2
