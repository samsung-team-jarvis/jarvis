from bench.fusion_eval import SCENARIO_DIR
from common.bus import MemoryBus
from common.messages import Envelope
from services.fusion_svc.service import FusionService
from services.safety_guard.service import SafetyGuard
from services.simulator.runner import play
from services.simulator.scenario import load


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class Rig:
    def __init__(self) -> None:
        self.clock = FakeClock()
        self.bus = MemoryBus()
        self.states: list[Envelope] = []
        self.bus.subscribe("fusion/state", self.states.append)
        self.svc = FusionService(self.bus, "s_fusion", clock=self.clock)
        self.svc.start()

    def send(self, topic: str, payload: dict) -> None:
        self.bus.publish(Envelope.new(topic, "test", payload, "s_in"))

    def devices(self, **levels: int) -> None:
        out = {h: {"on": False, "level": 0} for h in ("burner_1", "burner_2", "fryer")}
        for name, level in levels.items():
            out[name] = {"on": level > 0, "level": level}
        self.send("device/state", {"devices": out, "safe_stop": False})

    def temp(self, device: str, value: float) -> None:
        self.send("sensor/reading", {"device_id": device, "temperature_c": value})

    def wait(self, seconds: float) -> None:
        self.clock.now += seconds
        self.svc.tick()


def test_publishes_on_change_with_prev_state() -> None:
    rig = Rig()
    rig.svc.tick()
    assert rig.states[-1].payload["state"] == "IDLE"
    assert rig.states[-1].payload["prev_state"] == "IDLE"  # 시작한 뒤 바뀐 적 없음
    assert rig.states[-1].source == "fusion_svc" and rig.states[-1].session_id == "s_fusion"

    rig.devices(burner_1=2)  # 바뀌면 1초를 기다리지 않고 바로
    assert [s.payload["state"] for s in rig.states] == ["IDLE", "PREHEAT"]
    assert rig.states[-1].payload["prev_state"] == "IDLE"
    assert rig.states[-1].payload["evidence"]["heaters"]["burner_1"]["on"] is True


def test_publishes_every_second_otherwise() -> None:
    rig = Rig()
    rig.svc.tick()
    rig.wait(0.5)
    assert len(rig.states) == 1
    rig.wait(0.5)
    assert len(rig.states) == 2
    rig.devices(burner_1=1)
    rig.temp("burner_1", 120.0)
    rig.wait(1.0)
    assert rig.states[-1].payload["state"] == "COOKING"
    assert rig.states[-1].payload["prev_state"] == "PREHEAT"  # 반복 발행에도 직전 State 유지


def test_risk_change_is_published_immediately() -> None:
    rig = Rig()
    rig.devices(burner_1=3)
    rig.temp("burner_1", 150.0)
    count = len(rig.states)
    rig.temp("burner_1", 201.0)
    assert len(rig.states) == count + 1
    assert rig.states[-1].payload["risk"] == "warn"


def test_bad_evidence_is_logged_and_dropped(caplog) -> None:
    rig = Rig()
    rig.svc.tick()
    rig.send(
        "vision/objects", {"objects": None, "frame_id": 0, "pre_ms": 0, "npu_ms": 0, "post_ms": 0}
    )
    assert any(r.levelname == "WARNING" for r in caplog.records)
    rig.devices(burner_1=1)  # 서비스는 계속 판정한다
    assert rig.states[-1].payload["state"] == "PREHEAT"


def test_guard_allows_heating_once_fusion_reports_state() -> None:
    """상태를 모르던 Safety Guard가 fusion/state를 받으면 화구 켜기를 허용한다 (#139 목적)."""
    rig = Rig()
    decisions: list[Envelope] = []
    rig.bus.subscribe("guard/decision", decisions.append)
    guard = SafetyGuard(rig.bus, "s_guard", seq_start=0)
    guard.start()
    call = {"action": "TURN_ON", "target": "burner_1"}
    fc = {"call": call, "raw_text": "", "valid": True, "fallback": True, "gen_ms": 0, "tokens": 0}

    rig.send("llm/function_call", fc)
    assert decisions[-1].payload["decision"] == "REJECT"  # 상태 모름
    rig.svc.tick()
    rig.send("llm/function_call", fc)
    assert decisions[-1].payload["decision"] == "ALLOW"  # IDLE


def test_scenario_replayed_on_the_bus_gives_expected_transitions() -> None:
    """simulator → 버스 → fusion_svc: 시나리오를 실제 속도(가짜 시계)로 흘려 State 흐름을 본다."""
    rig = Rig()
    start = rig.clock.now
    seen: list[tuple[float, str]] = []  # (시나리오 초, State) — 바뀔 때만
    rig.bus.subscribe(
        "fusion/state",
        lambda m: (
            seen.append((rig.clock.now - start, m.payload["state"]))
            if not seen or seen[-1][1] != m.payload["state"]
            else None
        ),
    )
    sc = load(SCENARIO_DIR / "overheat_emergency.yaml")
    play(sc, rig.bus, "s_sim", speed=1.0, clock=rig.clock, sleep=rig.wait)

    assert seen == sc.expected
