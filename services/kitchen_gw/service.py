"""kitchen_gw: 버스(봉투)와 가상 주방의 연결 토픽(`kitchen/*`) 사이에서 메시지를 옮긴다.

규격: docs/architecture/interfaces.md §4, 상수·검사: common/kitchen_link.py.
가상 주방(Unity)은 봉투를 모른다. 이 서비스가 받은 순간에 보드 시계로 시각을 찍어 버스에 올린다.

    control/command ─▶ kitchen/cmd          (확인이 없으면 같은 seq로 한 번 다시)
    kitchen/ack     ─▶ control/result       (retries, rtt_ms)
    kitchen/temp    ─▶ sensor/reading
    1초마다         ─▶ kitchen/heartbeat    (끊기면 가상 주방이 가열 장치를 끈다)
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from collections.abc import Callable

from common import kitchen_link as link
from common.bus import Bus
from common.kitchen_link import LinkError
from common.messages import Envelope

SOURCE = "kitchen_gw"
log = logging.getLogger(__name__)


@dataclasses.dataclass
class _Pending:
    command: Envelope
    first_sent: float
    last_sent: float
    retries: int = 0


class KitchenGateway:
    def __init__(
        self,
        bus: Bus,
        session_id: str,
        on_result: Callable[[Envelope], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.bus = bus
        self.session_id = session_id  # 온도·heartbeat용. 결과는 받은 명령의 session_id를 이어 쓴다
        self.on_result = on_result
        self.clock = clock
        self.results = 0
        self.failed = 0  # 확인을 못 받았거나 가상 주방이 거절한 명령
        self.readings = 0
        self._pending: dict[int, _Pending] = {}
        self._lock = threading.Lock()
        self._last_heartbeat: float | None = None

    def start(self) -> None:
        self.bus.subscribe("control/command", self.on_command)
        self.bus.subscribe_raw(link.TOPIC_ACK, self.on_ack)
        self.bus.subscribe_raw(link.TOPIC_TEMP, self.on_temp)

    def on_command(self, msg: Envelope) -> None:
        try:
            link.validate_command(msg.payload)
        except LinkError as exc:  # 가상 주방에 보내지 않고 바로 실패로 끝낸다
            log.warning("규격에 맞지 않는 control/command: %s", exc)
            self._finish(msg, ok=False, retries=0, rtt_ms=0.0, reason="invalid_command")
            return
        now = self.clock()
        with self._lock:
            self._pending[msg.payload["seq"]] = _Pending(msg, first_sent=now, last_sent=now)
        self.bus.publish_raw(link.TOPIC_CMD, link.encode(msg.payload))

    def on_ack(self, topic: str, data: bytes) -> None:
        try:
            ack = link.decode_ack(data)
        except LinkError as exc:
            log.warning("%s", exc)
            return
        with self._lock:
            pending = self._pending.pop(ack["seq"], None)
        if pending is None:  # 이미 끝난 명령의 늦은 확인, 또는 다시 보낸 것에 대한 두 번째 확인
            return
        rtt_ms = round((self.clock() - pending.first_sent) * 1000, 3)
        self._finish(pending.command, ack["ok"], pending.retries, rtt_ms, ack.get("reason"))

    def on_temp(self, topic: str, data: bytes) -> None:
        try:
            temp = link.decode_temp(data)
        except LinkError as exc:
            log.warning("%s", exc)
            return
        payload = {"device_id": temp["device_id"], "temperature_c": temp["temperature_c"]}
        self.bus.publish(Envelope.new("sensor/reading", SOURCE, payload, self.session_id))
        self.readings += 1

    def poll(self) -> None:
        """확인을 기다리는 명령을 살핀다: 0.5초가 지났으면 한 번 다시 보내고, 그래도 없으면 실패."""
        now = self.clock()
        resend: list[Envelope] = []
        give_up: list[_Pending] = []
        with self._lock:
            for seq, pending in list(self._pending.items()):
                if now - pending.last_sent < link.ACK_TIMEOUT_S:
                    continue
                if pending.retries < link.MAX_RETRIES:
                    pending.retries += 1
                    pending.last_sent = now
                    resend.append(pending.command)
                else:
                    give_up.append(self._pending.pop(seq))
        for command in resend:
            self.bus.publish_raw(link.TOPIC_CMD, link.encode(command.payload))
        for pending in give_up:
            rtt_ms = round((now - pending.first_sent) * 1000, 3)
            self._finish(pending.command, False, pending.retries, rtt_ms, reason="no_ack")

    def heartbeat(self) -> None:
        now = self.clock()
        if (
            self._last_heartbeat is not None
            and now - self._last_heartbeat < link.HEARTBEAT_PERIOD_S
        ):
            return
        self._last_heartbeat = now
        self.bus.publish_raw(link.TOPIC_HEARTBEAT, link.encode({"alive": True}))
        self.bus.publish(Envelope.new("system/heartbeat", SOURCE, {"alive": True}, self.session_id))

    def _finish(
        self, command: Envelope, ok: bool, retries: int, rtt_ms: float, reason: str | None = None
    ) -> None:
        payload = {
            "seq": command.payload.get("seq"),
            "ok": ok,
            "retries": retries,
            "rtt_ms": rtt_ms,
        }
        if reason:
            payload["reason"] = reason
        out = Envelope.new("control/result", SOURCE, payload, command.session_id)
        self.bus.publish(out)
        self.results += 1
        if not ok:
            self.failed += 1
        if self.on_result:
            self.on_result(out)
