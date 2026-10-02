"""메시지 버스 — 서비스 간 통신 방식은 이 파일에만 둔다 (decision: 2026-10-02-message-bus-mqtt).

서비스 코드는 `connect()`로 버스를 얻고 `publish` / `subscribe`만 쓴다.
    bus = connect()                       # JARVIS_BUS 환경변수, 기본 mqtt://localhost:1883
    bus.subscribe("stt/#", handler)       # MQTT 와일드카드: + 한 단계, # 이하 전부
    bus.publish(Envelope.new(...))

- memory://           같은 프로세스 안에서만 전달 (테스트, 하드웨어 없는 개발)
- mqtt://host:port    MQTT 브로커(mosquitto) 경유, 프로세스 간 전달
"""

from __future__ import annotations

import logging
import os
import threading
import urllib.parse
from collections.abc import Callable
from typing import Protocol

from common.messages import Envelope, MessageError

DEFAULT_BUS_URL = "mqtt://localhost:1883"
Handler = Callable[[Envelope], None]
log = logging.getLogger(__name__)


def topic_matches(pattern: str, topic: str) -> bool:
    """MQTT 규칙의 토픽 매칭: `+`는 한 단계, `#`은 마지막에서 나머지 전부."""
    p_parts, t_parts = pattern.split("/"), topic.split("/")
    for i, part in enumerate(p_parts):
        if part == "#":
            return i == len(p_parts) - 1
        if i >= len(t_parts) or (part != "+" and part != t_parts[i]):
            return False
    return len(p_parts) == len(t_parts)


class Bus(Protocol):
    def publish(self, msg: Envelope) -> None: ...
    def subscribe(self, pattern: str, handler: Handler) -> None: ...
    def close(self) -> None: ...


def _dispatch(handler: Handler, msg: Envelope) -> None:
    """핸들러 하나가 예외를 내도 다른 구독자와 버스는 계속 동작해야 한다."""
    try:
        handler(msg)
    except Exception:
        log.exception("handler failed for %s", msg.type)


class MemoryBus:
    """같은 프로세스 안의 구독자에게 동기적으로 전달한다."""

    def __init__(self) -> None:
        self._subs: list[tuple[str, Handler]] = []
        self._lock = threading.Lock()

    def publish(self, msg: Envelope) -> None:
        msg.validate()
        with self._lock:
            targets = [h for p, h in self._subs if topic_matches(p, msg.type)]
        for handler in targets:
            _dispatch(handler, msg)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))

    def close(self) -> None:
        with self._lock:
            self._subs.clear()


class MqttBus:
    """MQTT 브로커 경유. 메시지 본문은 Envelope JSON, MQTT 토픽은 Envelope.type."""

    def __init__(self, host: str, port: int, client_id: str = "") -> None:
        import paho.mqtt.client as mqtt

        self._subs: list[tuple[str, Handler]] = []
        self._lock = threading.Lock()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_message = self._on_message
        self._client.on_connect = self._on_connect
        self._network_thread: int | None = None  # paho 네트워크 스레드 (콜백이 도는 곳)
        self._client.connect(host, port)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        # 재접속 시 구독을 다시 건다
        with self._lock:
            patterns = {p for p, _ in self._subs}
        for pattern in patterns:
            client.subscribe(pattern, qos=1)

    def _on_message(self, client, userdata, mqtt_msg) -> None:
        self._network_thread = threading.get_ident()
        try:
            msg = Envelope.from_json(mqtt_msg.payload)
        except MessageError:
            log.warning("규격에 맞지 않는 메시지 무시: topic=%s", mqtt_msg.topic)
            return
        with self._lock:
            targets = [h for p, h in self._subs if topic_matches(p, mqtt_msg.topic)]
        for handler in targets:
            _dispatch(handler, msg)

    def publish(self, msg: Envelope) -> None:
        msg.validate()
        info = self._client.publish(msg.type, msg.to_json(), qos=1)
        # 구독 핸들러 안(네트워크 스레드)에서 발행하면 PUBACK을 처리할 스레드가 자기 자신이라
        # 기다리면 timeout까지 멈춘다. 그때는 기다리지 않는다 (QoS 1 재전송은 paho가 맡는다).
        if threading.get_ident() != self._network_thread:
            info.wait_for_publish(timeout=5)

    def subscribe(self, pattern: str, handler: Handler) -> None:
        with self._lock:
            self._subs.append((pattern, handler))
        self._client.subscribe(pattern, qos=1)

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


def connect(url: str | None = None, client_id: str = "") -> Bus:
    """버스 URL(`memory://`, `mqtt://host:port`)로 버스를 만든다. 생략 시 JARVIS_BUS 환경변수."""
    url = url or os.environ.get("JARVIS_BUS", DEFAULT_BUS_URL)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "memory":
        return MemoryBus()
    if parsed.scheme == "mqtt":
        return MqttBus(parsed.hostname or "localhost", parsed.port or 1883, client_id=client_id)
    raise ValueError(f"지원하지 않는 버스 URL: {url} (memory:// 또는 mqtt://host:port)")
