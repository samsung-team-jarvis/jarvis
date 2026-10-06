import json

import pytest

from common.messages import TOPIC_REQUIRED_FIELDS, Envelope, MessageError


def heartbeat() -> Envelope:
    return Envelope.new("system/heartbeat", "test", {"alive": True}, "s_test")


def test_new_sets_clock_fields_and_version() -> None:
    msg = heartbeat()
    assert msg.v == 1
    assert msg.ts > 0 and msg.mono > 0


def test_json_round_trip() -> None:
    msg = heartbeat()
    assert Envelope.from_json(msg.to_json()) == msg


def test_json_keeps_korean_text() -> None:
    payload = {"text": "자비스", "wake": True, "audio_ms": 1, "stt_ms": 1, "speech_end_mono": 1}
    msg = Envelope.new("stt/text", "test", payload, "s_test")
    assert "자비스" in msg.to_json()


@pytest.mark.parametrize(
    ("type_", "payload", "error"),
    [
        ("unknown/topic", {}, "없는 토픽"),
        ("system/heartbeat", {}, "필수 필드"),
        ("sensor/reading", {"device_id": "x"}, "temperature_c"),
    ],
)
def test_rejects_invalid_payload(type_: str, payload: dict, error: str) -> None:
    with pytest.raises(MessageError, match=error):
        Envelope.new(type_, "test", payload, "s_test")


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        json.dumps({"type": "system/heartbeat"}),
        json.dumps(
            {
                "v": 2,
                "type": "system/heartbeat",
                "source": "x",
                "session_id": "s",
                "payload": {"alive": True},
                "ts": 1,
                "mono": 1,
            }
        ),
    ],
)
def test_from_json_rejects_bad_envelopes(raw: str) -> None:
    with pytest.raises(MessageError):
        Envelope.from_json(raw)


def test_every_documented_topic_has_required_fields() -> None:
    assert all(TOPIC_REQUIRED_FIELDS.values())
