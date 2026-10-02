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
