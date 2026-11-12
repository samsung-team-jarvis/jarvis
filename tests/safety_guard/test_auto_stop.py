import pytest

from common.bus import MemoryBus
from common.messages import Envelope
from services.fusion_svc.service import FusionService
from services.kitchen_gw.fake_kitchen import FakeKitchen
from services.kitchen_gw.service import KitchenGateway
from services.safety_guard.auto_stop import RESEND_S, STOP_ABSENT_S, AutoStop
from services.safety_guard.service import SafetyGuard


def state(absent_s: float = 0.0, **heaters: tuple[int, float | None]) -> dict:
    """heaters: 장치=(세기, 온도). 적지 않은 장치는 꺼짐·실온."""
    out = {
        h: {"on": False, "level": 0, "temperature_c": 25.0}
        for h in ("burner_1", "burner_2", "fryer")
    }
    for name, (level, temp) in heaters.items():
        out[name] = {"on": level > 0, "level": level, "temperature_c": temp}
    evidence = {
        "heaters": out,
        "person": True,
        "absent_s": absent_s,
        "safe_stop": None,
        "stale": [],
    }
    return {"state": "COOKING", "prev_state": "COOKING", "evidence": evidence, "risk": "none"}


def test_overheat_stops_only_the_hot_heater() -> None:
    stops = AutoStop().check(state(burner_1=(3, 240.0), burner_2=(2, 180.0)), now=0)
    assert stops == [("burner_1", "자동 차단: 과열 (1번 화구 240°C)")]


@pytest.mark.parametrize("temp", [239.9, None])
def test_no_overheat_stop_below_240_or_unknown_temperature(temp) -> None:
    assert AutoStop().check(state(burner_1=(3, temp)), now=0) == []


def test_hot_heater_already_off_is_left_alone() -> None:
    assert AutoStop().check(state(burner_1=(0, 250.0)), now=0) == []


def test_unattended_stops_all_heaters_that_are_on_after_grace() -> None:
    auto = AutoStop()
    on = {"burner_1": (2, 170.0), "fryer": (1, 110.0)}
    assert auto.check(state(absent_s=STOP_ABSENT_S - 0.1, **on), now=0) == []  # 유예 중
    stops = auto.check(state(absent_s=STOP_ABSENT_S, **on), now=1)
    assert [t for t, _ in stops] == ["burner_1", "fryer"]  # 후드 등은 끄지 않는다
    assert stops[0][1] == "자동 차단: 방치 (사람 없음 60초)"


def test_resends_only_if_still_on_after_a_while() -> None:
    auto = AutoStop()
    hot = state(burner_1=(3, 250.0))
    assert len(auto.check(hot, now=0)) == 1
    assert (
        auto.check(hot, now=RESEND_S - 0.1) == []
    )  # 1초마다 오는 fusion/state에 매번 보내지 않는다
    assert len(auto.check(hot, now=RESEND_S)) == 1  # 아직 켜져 있으면 다시
    auto.check(state(burner_1=(0, 250.0)), now=4)  # 꺼졌다
    assert len(auto.check(hot, now=4.5)) == 1  # 다시 켜져 과열이면 바로


class Kitchen:
    """한 버스 위의 가짜 가상 주방 + kitchen_gw + fusion_svc + safety_guard. 시간은 손으로."""

    def __init__(self) -> None:
        self.now = 1000.0
        clock = lambda: self.now  # noqa: E731
        self.bus = MemoryBus()
        self.decisions: list[Envelope] = []
        self.bus.subscribe("guard/decision", self.decisions.append)
        self.gw = KitchenGateway(self.bus, "s_gw", clock=clock)
        self.gw.start()
        self.kitchen = FakeKitchen(self.bus, clock=clock)
        self.kitchen.start()
        self.fusion = FusionService(self.bus, "s_fusion", clock=clock)
        self.fusion.start()
        self.guard = SafetyGuard(self.bus, "s_guard", clock=clock, seq_start=0)
        self.guard.start()
        self.person = True

    def say(self, call: dict) -> None:
        payload = {"call": call, "raw_text": "", "valid": True, "fallback": True}
        self.bus.publish(
            Envelope.new("llm/function_call", "test", {**payload, "gen_ms": 0, "tokens": 0}, "s_v")
        )

    def run(self, seconds: int) -> None:
        for _ in range(seconds):
            self.now += 1.0
            self.gw.heartbeat()
            self.gw.poll()
            self.kitchen.tick()
            objects = [{"cls": "person", "conf": 0.9, "bbox": [0, 0, 1, 1]}] if self.person else []
            frame = {"objects": objects, "frame_id": 0, "pre_ms": 0, "npu_ms": 0, "post_ms": 0}
            self.bus.publish(Envelope.new("vision/objects", "test", frame, "s_vis"))
            self.fusion.tick()

    def auto(self) -> list[dict]:
        return [d.payload for d in self.decisions if d.payload["reason"].startswith("자동 차단")]


def test_overheating_burner_is_turned_off_before_the_kitchen_hard_limit() -> None:
    k = Kitchen()
    k.run(1)
    k.say({"action": "TURN_ON", "target": "burner_1"})
    k.say({"action": "SET_LEVEL", "target": "burner_1", "level": 3})
    k.say({"action": "TURN_ON", "target": "hood"})
    assert k.kitchen.devices["burner_1"] == {"on": True, "level": 3}
    k.run(60)

    assert [(a["call"], a["decision"]) for a in k.auto()] == [
        ({"action": "TURN_OFF", "target": "burner_1"}, "ALLOW")
    ]
    assert k.kitchen.devices["burner_1"]["on"] is False
    assert k.kitchen.devices["hood"]["on"] is True  # 후드는 그대로
    assert k.kitchen.safe_stop is False  # 265°C 자체 차단(L0)까지 가지 않았다
    assert max(k.kitchen.temps.values()) < 265


def test_unattended_burner_is_turned_off_after_grace_unless_someone_returns() -> None:
    k = Kitchen()
    k.run(1)
    k.say({"action": "TURN_ON", "target": "burner_2"})  # 세기 1: 120°C까지만
    k.person = False
    k.run(45)  # 방치(30초) + 경고 뒤 15초
    assert k.fusion.machine.state(k.now) == "UNATTENDED" and k.auto() == []
    k.person = True  # 돌아옴 → 취소
    k.run(2)
    k.person = False
    k.run(60)  # 사람 없는 첫 화면부터 59초
    assert k.auto() == [] and k.kitchen.devices["burner_2"]["on"] is True  # 다시 센다
    k.run(1)
    assert [a["call"]["target"] for a in k.auto()] == ["burner_2"]
    assert k.kitchen.devices["burner_2"]["on"] is False
