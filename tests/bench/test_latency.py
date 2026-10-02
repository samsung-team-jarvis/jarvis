import pytest

from bench.latency import link, percentile, summarize
from common.messages import Envelope


def msg(type_: str, mono: float, payload: dict, session: str = "s1") -> Envelope:
    m = Envelope(type=type_, source="t", session_id=session, payload=payload, ts=0.0, mono=mono)
    m.validate()
    return m


def stt(mono: float, wake: bool = True, end: float | None = None, session: str = "s1"):
    payload = {"text": "자비스 후드 켜 줘", "wake": wake, "audio_ms": 1500, "stt_ms": 40,
               "speech_end_mono": mono - 0.6 if end is None else end}  # fmt: skip
    return msg("stt/text", mono, payload, session)


CALL = {"action": "TURN_ON", "target": "hood"}


def call(mono: float, session: str = "s1") -> Envelope:
    payload = {"call": CALL, "raw_text": "후드 켜 줘", "valid": True, "fallback": True,
               "gen_ms": 0.1, "tokens": 0}  # fmt: skip
    return msg("llm/function_call", mono, payload, session)


def full_chain(t: float, seq: int) -> list[Envelope]:
    return [
        stt(t, end=t - 0.6),
        call(t + 0.002),
        msg("guard/decision", t + 0.005, {"call": CALL, "decision": "ALLOW", "reason": ""}),
        msg("control/command", t + 0.006, {"seq": seq, "cmd": 1, "target": 1, "value": 1}),
        msg("control/result", t + 0.056, {"seq": seq, "ok": True, "retries": 0, "rtt_ms": 49}),
    ]


def test_full_chain_segments() -> None:
    [u] = link(full_chain(10.0, seq=7))
    seg = u.segments()
    assert seg["vad_wait"] == pytest.approx(560)  # 600 - stt_ms 40
    assert seg["stt"] == 40
    assert seg["to_call"] == pytest.approx(2)
    assert seg["to_guard"] == pytest.approx(3)
    assert seg["to_command"] == pytest.approx(1)
    assert seg["to_ack"] == pytest.approx(50)
    assert seg["e2e"] == pytest.approx(656)
    assert u.last_stage() == "control/result"


def test_partial_chain_leaves_missing_segments_empty() -> None:
    [u] = link([stt(5.0), call(5.003)])
    seg = u.segments()
    assert seg["to_call"] == pytest.approx(3)
    assert seg["to_guard"] is None and seg["to_ack"] is None
    assert seg["e2e"] == pytest.approx(603)
    assert u.last_stage() == "llm/function_call"


def test_non_wake_and_other_sessions_are_separated() -> None:
    messages = [
        stt(1.0, wake=False),  # 호출어 없음 → 제외
        stt(2.0, session="a"),
        stt(2.1, session="b"),
        call(2.2, session="a"),  # a 세션 발화에 붙어야 한다
    ]
    utterances = link(messages)
    assert [(u.stt.session_id, u.call is not None) for u in utterances] == [
        ("a", True),
        ("b", False),
    ]


def test_two_utterances_in_order_and_seq_matching() -> None:
    messages = full_chain(10.0, seq=1) + full_chain(20.0, seq=2)
    # control/result 순서가 바뀌어 녹화돼도 seq로 맞춘다
    messages[4], messages[9] = (
        msg("control/result", 20.07, {"seq": 2, "ok": True, "retries": 0, "rtt_ms": 60}),
        msg("control/result", 10.07, {"seq": 1, "ok": True, "retries": 0, "rtt_ms": 60}),
    )
    a, b = link(messages)
    assert a.result.payload["seq"] == 1 and b.result.payload["seq"] == 2
    assert a.segments()["to_ack"] == pytest.approx(64)


def test_summary_and_percentile() -> None:
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10
    assert percentile([5], 50) == 5
    utterances = link([stt(1.0), call(1.002), stt(5.0), call(5.004)])
    s = summarize(utterances)
    assert s["to_call"]["n"] == 2
    assert s["to_call"]["mean"] == pytest.approx(3)
    assert "to_guard" not in s
