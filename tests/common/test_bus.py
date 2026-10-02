import os
import threading
import time

import pytest

from common.bus import MemoryBus, connect, topic_matches
from common.messages import Envelope


def heartbeat(source: str = "test") -> Envelope:
    return Envelope.new("system/heartbeat", source, {"alive": True}, "s_test")


@pytest.mark.parametrize(
    ("pattern", "topic", "expected"),
    [
        ("stt/text", "stt/text", True),
        ("stt/text", "stt/other", False),
        ("stt/+", "stt/text", True),
        ("+/text", "stt/text", True),
        ("stt/#", "stt/text", True),
        ("stt/#", "stt", True),
        ("#", "control/command", True),
        ("stt/+", "stt/text/extra", False),
        ("stt", "stt/text", False),
    ],
)
def test_topic_matches(pattern: str, topic: str, expected: bool) -> None:
    assert topic_matches(pattern, topic) is expected


def test_memory_bus_delivers_to_matching_subscribers_only() -> None:
    bus = MemoryBus()
    system, stt = [], []
    bus.subscribe("system/#", system.append)
    bus.subscribe("stt/#", stt.append)
    bus.publish(heartbeat())
    assert len(system) == 1 and stt == []


def test_failing_handler_does_not_block_others() -> None:
    bus = MemoryBus()
    received = []

    def broken(msg: Envelope) -> None:
        raise RuntimeError("boom")

    bus.subscribe("#", broken)
    bus.subscribe("#", received.append)
    bus.publish(heartbeat())
    assert len(received) == 1


def test_connect_parses_urls() -> None:
    assert isinstance(connect("memory://"), MemoryBus)
    with pytest.raises(ValueError):
        connect("redis://localhost")


@pytest.mark.skipif(not os.environ.get("JARVIS_TEST_MQTT"), reason="JARVIS_TEST_MQTT 브로커 없음")
def test_mqtt_round_trip() -> None:
    """JARVIS_TEST_MQTT=mqtt://localhost:1883 처럼 브로커가 있을 때만 실행."""
    url = os.environ["JARVIS_TEST_MQTT"]
    sub, pub = connect(url, client_id="test_sub"), connect(url, client_id="test_pub")
    got = threading.Event()
    received = []

    def on_message(msg: Envelope) -> None:
        received.append(msg)
        got.set()

    sub.subscribe("system/heartbeat", on_message)
    time.sleep(0.3)
    sent = heartbeat("mqtt_test")
    pub.publish(sent)
    assert got.wait(timeout=5)
    assert received[0] == sent
    sub.close()
    pub.close()


@pytest.mark.skipif(not os.environ.get("JARVIS_TEST_MQTT"), reason="JARVIS_TEST_MQTT 브로커 없음")
def test_mqtt_publish_inside_handler_does_not_block() -> None:
    """받고 → 다시 보내는 서비스: 핸들러 안에서 발행해도 멈추지 않아야 한다 (고치기 전 약 5초)."""
    url = os.environ["JARVIS_TEST_MQTT"]
    relay, src = connect(url, client_id="test_relay"), connect(url, client_id="test_src")
    took: list[float] = []
    relayed = []
    done = threading.Event()

    def on_stt(msg: Envelope) -> None:
        start = time.monotonic()
        relay.publish(heartbeat("relay_test"))
        took.append(time.monotonic() - start)

    def on_heartbeat(msg: Envelope) -> None:
        if msg.source == "relay_test":
            relayed.append(msg)
            if len(relayed) == 2:
                done.set()

    relay.subscribe("stt/text", on_stt)
    src.subscribe("system/heartbeat", on_heartbeat)
    time.sleep(0.3)
    payload = {"text": "x", "wake": True, "audio_ms": 1, "stt_ms": 1, "speech_end_mono": 0.0}
    for _ in range(2):
        src.publish(Envelope.new("stt/text", "test", payload, "relay_test"))
    assert done.wait(timeout=5)
    assert max(took) < 1.0
    relay.close()
    src.close()
