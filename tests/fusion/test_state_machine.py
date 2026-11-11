import pytest

from bench import fusion_eval as fe
from services.fusion_svc import state_machine as sm
from services.fusion_svc.state_machine import StateMachine
from services.simulator.scenario import load

OFF = {"on": False, "level": 0}


def devices(safe_stop: bool = False, **levels: int) -> dict:
    out = {h: dict(OFF) for h in ("burner_1", "burner_2", "fryer")}
    for name, level in levels.items():
        out[name] = {"on": level > 0, "level": level}
    return {"devices": out, "safe_stop": safe_stop}


def reading(device: str, temp: float) -> dict:
    return {"device_id": device, "temperature_c": temp}


def frame(*classes: str) -> dict:
    objects = [{"cls": c, "conf": 0.9, "bbox": [0, 0, 1, 1]} for c in classes]
    return {"objects": objects, "frame_id": 0, "pre_ms": 0, "npu_ms": 0, "post_ms": 0}


class Feed:
    """1초마다 근거를 넣는다: 장치 상태는 바뀔 때, 온도는 모든 가열 장치, 화면은 1장."""

    def __init__(self) -> None:
        self.m = StateMachine()
        self.t = 0.0
        self.temps = {"burner_1": 25.0, "burner_2": 25.0, "fryer": 25.0}

    def step(self, seconds: int = 1, person: bool | None = True, temps: bool = True) -> None:
        for _ in range(seconds):
            self.t += 1
            if temps:
                for name, value in self.temps.items():
                    self.m.update(self.t, "sensor/reading", reading(name, value))
            if person is not None:
                self.m.update(self.t, "vision/objects", frame(*(["person"] if person else [])))

    def devices(self, **kw) -> None:
        self.m.update(self.t, "device/state", devices(**kw))

    def state(self) -> str:
        return self.m.state(self.t)


@pytest.mark.parametrize("name", fe.split_names("all"))
def test_matches_expected_state_of_every_scenario(name: str) -> None:
    """시나리오 정답(expected)과 1초마다 같다. 판정 기준·시나리오를 고치면 이 테스트가 잡는다."""
    sc = load(fe.SCENARIO_DIR / f"{name}.yaml")
    wrong = [(k.t, k.truth, k.pred) for k in fe.run(sc, StateMachine()) if k.truth != k.pred]
    assert wrong == []


def test_state_is_read_only() -> None:
    """같은 근거·시각이면 state()를 몇 번, 언제 불러도 답이 같다 (DANGER 해제 기준 포함)."""
    f = Feed()
    f.devices(burner_1=3)
    f.temps["burner_1"] = 245.0
    f.step()
    f.temps["burner_1"] = 235.0  # 230°C 위: 아직 DANGER
    f.step()
    assert [f.state() for _ in range(3)] == ["DANGER"] * 3
    assert f.m.state(f.t - 0.5) == f.m.state(f.t + 0.5) == "DANGER"


def test_danger_releases_below_230() -> None:
    f = Feed()
    f.devices(burner_1=3)
    for temp, want in (
        (239.0, "COOKING"),
        (240.0, "DANGER"),
        (231.0, "DANGER"),
        (229.9, "COOKING"),
    ):
        f.temps["burner_1"] = temp
        f.step()
        assert f.state() == want, temp


def test_preheat_cooking_idle_by_device_state_and_temperature() -> None:
    f = Feed()
    f.step()
    assert f.state() == "IDLE"
    f.devices(burner_2=2)
    assert f.state() == "PREHEAT"
    f.temps["burner_2"] = 100.0
    f.step()
    assert f.state() == "COOKING"
    f.devices()  # 끔: 아직 뜨거워도 IDLE
    assert f.state() == "IDLE"


def test_unattended_counts_from_when_heating_started() -> None:
    f = Feed()
    f.step(20, person=False)  # 가열 없이 사람 없음: 방치 아님
    assert f.state() == "IDLE" and f.m.absent_s(f.t) == 0
    f.devices(burner_1=1)
    f.step(9, person=False)
    assert f.m.risk(f.t) == "none"
    f.step(1, person=False)
    assert f.m.risk(f.t) == "warn"  # 켜진 뒤 10초
    f.step(19, person=False)
    assert f.state() == "PREHEAT"
    f.step(1, person=False)
    assert f.state() == "UNATTENDED" and f.m.risk(f.t) == "danger"
    f.step(1, person=True)
    assert f.state() == "PREHEAT" and f.m.absent_s(f.t) == 0


def test_lost_camera_counts_as_nobody_from_the_last_frame() -> None:
    """화면이 끊기면 마지막 화면을 계속 믿지 않는다 — 사람이 없는 것으로 보고 방치를 센다."""
    f = Feed()
    f.devices(burner_1=2)
    f.step(5, person=True)
    last_frame = f.t
    f.step(2, person=None)
    assert f.m.person(f.t) is True  # 2초까지는 마지막 화면을 믿는다
    f.step(1, person=None)
    assert f.m.person(f.t) is None and "vision" in f.m.stale(f.t)
    f.step(27, person=None)
    assert f.t - last_frame == 30 and f.state() == "UNATTENDED"
    assert f.m.evidence(f.t)["person"] is None


def test_lost_temperature_is_not_trusted() -> None:
    f = Feed()
    f.devices(burner_1=3)
    f.temps["burner_1"] = 250.0
    f.step()
    assert f.state() == "DANGER"
    f.step(4, temps=False)  # 온도가 3초 넘게 안 옴
    assert f.m.evidence(f.t)["heaters"]["burner_1"]["temperature_c"] is None
    assert "burner_1" in f.m.stale(f.t)
    assert f.state() == "PREHEAT"  # 모르는 온도로 DANGER·COOKING을 판정하지 않는다
    assert f.m.risk(f.t) == "warn"  # 켜진 장치의 온도를 모른다


def test_kitchen_safe_stop_holds_until_all_off_and_cool() -> None:
    f = Feed()
    f.devices(burner_1=3)
    f.temps["burner_1"] = 265.0
    f.step()
    f.devices(safe_stop=True)  # 가상 주방이 스스로 끔 (보드 명령 없음)
    assert f.state() == "SAFE_STOP" and f.m.evidence(f.t)["safe_stop"] == "kitchen"
    f.temps["burner_1"] = 100.0
    f.step()
    assert f.state() == "SAFE_STOP"
    f.temps["burner_1"] = 99.9
    f.step()
    assert f.state() == "IDLE"
    f.devices(safe_stop=True)  # safe_stop은 새 명령까지 true로 남는다 — 다시 들어가지 않는다
    f.step(5)
    assert f.state() == "IDLE"


def test_safe_stop_waits_while_a_temperature_is_unknown() -> None:
    f = Feed()
    f.devices(burner_1=3)
    f.temps["burner_1"] = 150.0
    f.step()
    f.m.update(f.t, "stt/text", {"text": "자비스 멈춰", "wake": True})
    f.devices()
    f.step(5, temps=False)
    assert f.state() == "SAFE_STOP"  # 식었는지 확인할 수 없다
    f.temps["burner_1"] = 90.0
    f.step()
    assert f.state() == "IDLE"


@pytest.mark.parametrize(
    ("topic", "payload", "want"),
    [
        ("stt/text", {"text": "자비스 멈춰", "wake": True}, "SAFE_STOP"),
        ("stt/text", {"text": "멈춰!", "wake": False}, "SAFE_STOP"),
        ("stt/text", {"text": "자비스 음악 멈춰", "wake": True}, "COOKING"),
        ("stt/text", {"text": "자비스 타이머 정지", "wake": True}, "COOKING"),
        (
            "guard/decision",
            {"call": {"action": "EMERGENCY_STOP", "target": "all"}, "decision": "ALLOW"},
            "SAFE_STOP",
        ),
        (
            "guard/decision",
            {"call": {"action": "TURN_OFF", "target": "all"}, "decision": "ALLOW"},
            "COOKING",
        ),
    ],
)
def test_emergency_stop_evidence(topic: str, payload: dict, want: str) -> None:
    f = Feed()
    f.devices(burner_1=2)
    f.temps["burner_1"] = 150.0
    f.step()
    f.m.update(f.t, topic, payload)
    assert f.state() == want


def test_most_dangerous_heater_decides() -> None:
    f = Feed()
    f.devices(burner_1=1, fryer=3)
    f.temps.update(burner_1=110.0, fryer=241.0)
    f.step()
    assert f.state() == "DANGER"
    f.temps["fryer"] = 205.0
    f.step()
    assert f.state() == "COOKING" and f.m.risk(f.t) == "warn"


def test_evidence_shape() -> None:
    f = Feed()
    f.devices(burner_1=2)
    f.temps["burner_1"] = 123.45
    f.step()
    e = f.m.evidence(f.t)
    assert e == {
        "heaters": {
            "burner_1": {"on": True, "level": 2, "temperature_c": 123.5},
            "burner_2": {"on": False, "level": 0, "temperature_c": 25.0},
            "fryer": {"on": False, "level": 0, "temperature_c": 25.0},
        },
        "person": True,
        "absent_s": 0.0,
        "safe_stop": None,
        "stale": [],
    }


def test_thresholds_follow_the_decision() -> None:
    assert (sm.DANGER_C, sm.DANGER_EXIT_C, sm.WARN_C, sm.COOK_C) == (240, 230, 200, 100)
    assert (sm.UNATTENDED_S, sm.UNATTENDED_WARN_S) == (30, 10)
