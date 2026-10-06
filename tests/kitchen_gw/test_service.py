import json

from common import kitchen_link as link
from common.bus import MemoryBus
from common.messages import Envelope
from services.kitchen_gw.fake_kitchen import FakeKitchen
from services.kitchen_gw.service import KitchenGateway


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Rig:
    """메모리 버스 위의 kitchen_gw (+ 가짜 가상 주방). 시간은 손으로 넘긴다."""

    def __init__(self, with_kitchen: bool = True) -> None:
        self.clock = FakeClock()
        self.bus = MemoryBus()
        self.results: list[Envelope] = []
        self.readings: list[Envelope] = []
        self.sent: list[dict] = []
        self.states: list[dict] = []
        self.bus.subscribe("control/result", self.results.append)
        self.bus.subscribe("sensor/reading", self.readings.append)
        self.bus.subscribe_raw(link.TOPIC_CMD, lambda _t, d: self.sent.append(json.loads(d)))
        self.bus.subscribe_raw(link.TOPIC_STATE, lambda _t, d: self.states.append(json.loads(d)))
        self.gateway = KitchenGateway(self.bus, "s_gw", clock=self.clock)
        self.gateway.start()
        self.kitchen: FakeKitchen | None = None
        if with_kitchen:
            self.add_kitchen()

    def add_kitchen(self) -> None:
        self.kitchen = FakeKitchen(self.bus, clock=self.clock)
        self.kitchen.start()

    def command(
        self, seq: int, cmd: str, target: str, value: int, session: str = "s_voice"
    ) -> None:
        payload = {"seq": seq, "cmd": cmd, "target": target, "value": value}
        self.bus.publish(Envelope.new("control/command", "safety_guard", payload, session))

    def run(self, seconds: int, heartbeat: bool = True) -> None:
        """1초씩 넘기며 보드(생존 신호·재시도 확인)와 가상 주방(온도·안전장치)을 돌린다."""
        for _ in range(seconds):
            self.clock.now += 1.0
            if heartbeat:
                self.gateway.heartbeat()
            self.gateway.poll()
            if self.kitchen:
                self.kitchen.tick()


def test_command_reaches_kitchen_and_result_comes_back() -> None:
    rig = Rig()
    rig.command(1, "ON", "hood", 1, session="s_voice")

    assert rig.kitchen.devices["hood"] == {"on": True, "level": 1}
    assert len(rig.results) == 1
    result = rig.results[0]
    assert result.source == "kitchen_gw"
    assert result.session_id == "s_voice"  # 받은 명령의 세션을 이어 쓴다 (지연 추적)
    assert result.payload == {"seq": 1, "ok": True, "retries": 0, "rtt_ms": 0.0}


def test_level_and_off_all() -> None:
    rig = Rig()
    rig.command(1, "LEVEL", "burner_2", 3)
    rig.command(2, "ON", "hood", 1)
    assert rig.kitchen.devices["burner_2"] == {"on": True, "level": 3}
    rig.command(3, "OFF", "all", 0)
    assert all(d == {"on": False, "level": 0} for d in rig.kitchen.devices.values())
    assert [r.payload["ok"] for r in rig.results] == [True, True, True]


def test_no_ack_resends_once_then_fails() -> None:
    rig = Rig(with_kitchen=False)
    rig.command(7, "ON", "hood", 1)
    assert len(rig.sent) == 1 and rig.results == []

    rig.clock.now += 0.4
    rig.gateway.poll()
    assert len(rig.sent) == 1  # 아직 0.5초가 안 됐다

    rig.clock.now += 0.1
    rig.gateway.poll()
    assert [c["seq"] for c in rig.sent] == [7, 7]  # 같은 seq로 한 번 다시 보낸다
    assert rig.results == []

    rig.clock.now += 0.5
    rig.gateway.poll()
    assert len(rig.sent) == 2
    assert rig.results[0].payload == {
        "seq": 7,
        "ok": False,
        "retries": 1,
        "rtt_ms": 1000.0,
        "reason": "no_ack",
    }
    assert rig.gateway.failed == 1


def test_ack_after_resend_counts_the_retry() -> None:
    rig = Rig(with_kitchen=False)
    rig.command(3, "ON", "hood", 1)
    rig.clock.now += 0.5
    rig.add_kitchen()  # 가상 주방이 늦게 떴다
    rig.gateway.poll()

    assert rig.results[0].payload == {"seq": 3, "ok": True, "retries": 1, "rtt_ms": 500.0}
    assert rig.kitchen.applied == 1


def test_same_seq_is_applied_once_but_acked_again() -> None:
    rig = Rig()
    acks: list[dict] = []
    rig.bus.subscribe_raw(link.TOPIC_ACK, lambda _t, d: acks.append(json.loads(d)))
    command = link.encode({"seq": 4, "cmd": "LEVEL", "target": "hood", "value": 2})

    rig.bus.publish_raw(link.TOPIC_CMD, command)
    rig.bus.publish_raw(link.TOPIC_CMD, command)

    assert rig.kitchen.applied == 1
    assert acks == [{"seq": 4, "ok": True}, {"seq": 4, "ok": True}]


def test_late_ack_is_ignored() -> None:
    rig = Rig(with_kitchen=False)
    rig.command(5, "ON", "hood", 1)
    rig.run(2, heartbeat=False)  # 다시 보내고도 확인이 없어 실패로 끝남
    assert [r.payload["ok"] for r in rig.results] == [False]

    rig.bus.publish_raw(link.TOPIC_ACK, link.encode({"seq": 5, "ok": True}))
    assert len(rig.results) == 1


def test_gateway_rejects_invalid_command_without_sending() -> None:
    rig = Rig()
    rig.command(9, "ON", "fridge", 1)

    assert rig.sent == []
    assert rig.results[0].payload["ok"] is False
    assert rig.results[0].payload["reason"] == "invalid_command"


def test_kitchen_refuses_unknown_target() -> None:
    rig = Rig()
    acks: list[dict] = []
    rig.bus.subscribe_raw(link.TOPIC_ACK, lambda _t, d: acks.append(json.loads(d)))

    rig.bus.publish_raw(link.TOPIC_CMD, b'{"seq":6,"cmd":"ON","target":"fryer","value":1}')
    rig.bus.publish_raw(link.TOPIC_CMD, b"not json")

    assert acks == [{"seq": 6, "ok": False, "reason": "invalid_command"}]
    assert rig.kitchen.applied == 0


def test_temperature_reaches_the_bus_once_a_second() -> None:
    rig = Rig()
    rig.command(1, "LEVEL", "burner_1", 2)
    rig.run(10)

    burner_1 = [
        r.payload["temperature_c"] for r in rig.readings if r.payload["device_id"] == "burner_1"
    ]
    burner_2 = [
        r.payload["temperature_c"] for r in rig.readings if r.payload["device_id"] == "burner_2"
    ]
    assert len(burner_1) == 10 and len(burner_2) == 10
    assert burner_1 == sorted(burner_1) and burner_1[0] > 25.0  # 켜 둔 화구는 계속 오른다
    assert set(burner_2) == {25.0}  # 꺼진 화구는 실온
    assert burner_1[-1] == round(_expected(level=2, seconds=10), 1)
    assert rig.readings[0].session_id == "s_gw" and rig.readings[0].source == "kitchen_gw"


def _expected(level: int, seconds: int) -> float:
    temp = link.TARGET_C[0]
    for _ in range(seconds):
        temp = link.next_temperature(temp, level)
    return temp


def test_heaters_turn_off_when_heartbeat_stops() -> None:
    rig = Rig()
    rig.command(1, "ON", "hood", 1)
    rig.command(2, "LEVEL", "burner_1", 2)
    rig.run(5)
    assert rig.kitchen.devices["burner_1"]["on"] and not rig.kitchen.safe_stop

    rig.run(2, heartbeat=False)
    assert rig.kitchen.devices["burner_1"]["on"]  # 아직 3초가 안 됐다
    rig.run(1, heartbeat=False)

    assert rig.kitchen.devices["burner_1"] == {"on": False, "level": 0}
    assert rig.kitchen.devices["hood"] == {"on": True, "level": 1}  # 후드는 끄지 않는다
    assert rig.kitchen.safe_stop
    assert rig.states[-1]["safe_stop"] is True

    rig.command(3, "ON", "burner_1", 1)  # 생존 신호가 없는 동안 가열 장치는 켜지지 않는다
    assert rig.results[-1].payload["ok"] is False
    assert rig.results[-1].payload["reason"] == "no_heartbeat"
    assert not rig.kitchen.devices["burner_1"]["on"]

    rig.run(1)  # 생존 신호가 돌아왔다
    rig.command(4, "ON", "burner_1", 1)
    assert rig.results[-1].payload["ok"] is True
    assert rig.kitchen.devices["burner_1"]["on"] and not rig.kitchen.safe_stop


def test_heater_turns_itself_off_at_the_hard_limit() -> None:
    rig = Rig()
    rig.command(1, "LEVEL", "burner_1", 3)
    rig.run(75)
    assert rig.kitchen.devices["burner_1"]["on"]

    rig.run(1)  # 76초에 265°C를 넘는다
    assert rig.kitchen.devices["burner_1"] == {"on": False, "level": 0}
    assert rig.kitchen.safe_stop and rig.states[-1]["safe_stop"] is True

    rig.run(120)
    assert rig.kitchen.temps["burner_1"] < 40  # 꺼진 뒤에는 식는다


def test_heartbeat_goes_to_kitchen_and_bus_once_a_second() -> None:
    rig = Rig(with_kitchen=False)
    raw: list[bytes] = []
    system: list[Envelope] = []
    rig.bus.subscribe_raw(link.TOPIC_HEARTBEAT, lambda _t, d: raw.append(d))
    rig.bus.subscribe("system/heartbeat", system.append)

    for _ in range(25):  # 0.1초 간격으로 2.5초
        rig.gateway.heartbeat()
        rig.clock.now += 0.1

    assert len(raw) == 3 and len(system) == 3
    assert json.loads(raw[0]) == {"alive": True}


def test_state_is_published_on_change_and_periodically() -> None:
    rig = Rig()
    assert len(rig.states) == 1  # 시작할 때 한 번
    rig.command(1, "ON", "hood", 1)
    assert rig.states[-1]["devices"]["hood"] == {"on": True, "level": 1}
    count = len(rig.states)
    rig.command(2, "ON", "hood", 1)  # 바뀐 게 없으면 다시 보내지 않는다
    assert len(rig.states) == count
    rig.run(5)
    assert len(rig.states) == count + 1
    link.decode_state(link.encode(rig.states[-1]))
