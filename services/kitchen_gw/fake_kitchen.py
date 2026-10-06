"""가짜 가상 주방: Unity가 없을 때 그 자리를 대신한다 (interfaces.md §4의 기준 동작).

같은 연결 토픽(`kitchen/*`)으로 명령을 받고, 확인·온도·상태를 보낸다. 화면(`kitchen/frame`)은 없다.
보드 쪽 서비스를 Unity 없이 개발·시험하는 데 쓰고, Unity 쪽이 맞춰야 할 동작의 예시이기도 하다.

    python -m services.kitchen_gw.fake_kitchen                 # 버스는 JARVIS_BUS (기본 MQTT)
"""

from __future__ import annotations

import argparse
import collections
import json
import signal
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

from common import kitchen_link as link
from common.bus import Bus, connect
from common.function_call import DEVICES
from common.kitchen_link import LinkError

STATE_PERIOD_S = 5.0
REMEMBERED_SEQS = 64


class FakeKitchen:
    def __init__(self, bus: Bus, clock: Callable[[], float] = time.monotonic) -> None:
        self.bus = bus
        self.clock = clock
        self.devices: dict[str, dict[str, Any]] = {d: {"on": False, "level": 0} for d in DEVICES}
        self.temps: dict[str, float] = {h: link.TARGET_C[0] for h in link.HEATERS}
        self.safe_stop = False
        self.applied = 0  # 실제로 장치를 바꾼 명령 수 (같은 seq 재전송은 세지 않는다)
        now = clock()
        self._last_heartbeat = now  # 시작 직후 3초는 생존 신호를 기다린다
        self._last_tick = now
        self._last_temp = now
        self._last_state = now
        self._acks: collections.OrderedDict[int, dict[str, Any]] = collections.OrderedDict()
        self._lock = threading.Lock()

    def start(self) -> None:
        self.bus.subscribe_raw(link.TOPIC_CMD, self.on_cmd)
        self.bus.subscribe_raw(link.TOPIC_HEARTBEAT, self.on_heartbeat)
        self._publish_state()

    def on_heartbeat(self, topic: str, data: bytes) -> None:
        with self._lock:
            self._last_heartbeat = self.clock()

    def on_cmd(self, topic: str, data: bytes) -> None:
        try:
            command = link.decode_command(data)
        except LinkError:
            self._refuse_invalid(data)
            return
        with self._lock:
            ack = self._acks.get(command["seq"])
            changed = False
            if ack is None:  # 처음 받은 seq만 실행한다
                ack, changed = self._apply(command)
                self._acks[command["seq"]] = ack
                while len(self._acks) > REMEMBERED_SEQS:
                    self._acks.popitem(last=False)
        if changed:
            self._publish_state()
        self.bus.publish_raw(link.TOPIC_ACK, link.encode(ack))

    def tick(self) -> None:
        """시간이 흐른 만큼 온도를 바꾸고, 안전장치를 살피고, 주기가 된 메시지를 보낸다."""
        now = self.clock()
        changed = False
        with self._lock:
            dt, self._last_tick = now - self._last_tick, now
            for heater in link.HEATERS:
                level = self.devices[heater]["level"]
                self.temps[heater] = link.next_temperature(self.temps[heater], level, dt)
                if self.devices[heater]["on"] and self.temps[heater] >= link.HARD_LIMIT_C:
                    changed |= self._turn_off(heater)
                    self.safe_stop = True
            if not self._heartbeat_alive(now):
                for heater in link.HEATERS:
                    if self._turn_off(heater):
                        changed = True
                        self.safe_stop = True
            send_temp = now - self._last_temp >= link.TEMP_PERIOD_S
            if send_temp:
                self._last_temp = now
            send_state = changed or now - self._last_state >= STATE_PERIOD_S
        if send_temp:
            for heater in link.HEATERS:
                reading = {"device_id": heater, "temperature_c": round(self.temps[heater], 1)}
                self.bus.publish_raw(link.TOPIC_TEMP, link.encode(reading))
        if send_state:
            self._publish_state()

    def _heartbeat_alive(self, now: float) -> bool:
        return now - self._last_heartbeat < link.HEARTBEAT_TIMEOUT_S

    def _apply(self, command: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        seq, cmd, target, value = (command[k] for k in ("seq", "cmd", "target", "value"))
        if cmd != "OFF" and target in link.HEATERS and not self._heartbeat_alive(self.clock()):
            return {"seq": seq, "ok": False, "reason": "no_heartbeat"}, False
        changed = False
        if cmd == "OFF":
            for name in DEVICES if target == "all" else (target,):
                changed |= self._turn_off(name)
        else:  # ON은 세기 1, LEVEL은 꺼져 있으면 켜면서 세기를 맞춘다
            new = {"on": True, "level": value}
            changed = self.devices[target] != new
            self.devices[target] = new
        self.safe_stop = False
        self.applied += 1
        return {"seq": seq, "ok": True}, changed

    def _turn_off(self, name: str) -> bool:
        was_on = self.devices[name]["on"]
        self.devices[name] = {"on": False, "level": 0}
        return was_on

    def _refuse_invalid(self, data: bytes) -> None:
        """규격에 안 맞는 명령: seq를 읽을 수 있으면 실행하지 않았다고 알린다 (모르는 target 등)."""
        try:
            seq = json.loads(data).get("seq")
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            return
        if isinstance(seq, int) and not isinstance(seq, bool):
            ack = {"seq": seq, "ok": False, "reason": "invalid_command"}
            self.bus.publish_raw(link.TOPIC_ACK, link.encode(ack))

    def _publish_state(self) -> None:
        with self._lock:
            state = {"devices": {k: dict(v) for k, v in self.devices.items()}}
            state["safe_stop"] = self.safe_stop
            self._last_state = self.clock()
        self.bus.publish_raw(link.TOPIC_STATE, link.encode(state))


def main() -> int:
    parser = argparse.ArgumentParser(description="Unity 대신 연결 토픽에 답하는 가짜 가상 주방")
    parser.add_argument("--bus", default=None, help="생략 시 JARVIS_BUS 환경변수 (기본 MQTT)")
    parser.add_argument("--quiet", action="store_true", help="장치 상태를 출력하지 않음")
    args = parser.parse_args()

    bus = connect(args.bus, client_id="fake_kitchen")
    kitchen = FakeKitchen(bus)
    if not args.quiet:
        bus.subscribe_raw(
            link.TOPIC_STATE, lambda _t, data: print(f"[kitchen/state] {data.decode()}")
        )
    kitchen.start()
    print("가짜 가상 주방 시작: kitchen/cmd 구독 중 (Ctrl+C로 종료)")

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(0.1):
            kitchen.tick()
    except KeyboardInterrupt:
        pass
    bus.close()
    print(f"OK: 명령 {kitchen.applied}건 적용")
    return 0


if __name__ == "__main__":
    sys.exit(main())
