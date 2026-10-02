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
