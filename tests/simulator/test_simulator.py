import pathlib

import pytest

from common import kitchen_link as link
from common.bus import MemoryBus
from common.messages import Envelope
from services.simulator.runner import (
    STATE_PERIOD_S,
    build_events,
    device_states,
    heater_readings,
    play,
)
from services.simulator.scenario import ScenarioError, expected_at, interpolate, load, parse

SCENARIO_DIR = pathlib.Path(__file__).parents[2] / "services/simulator/scenarios"
SCENARIOS = sorted(SCENARIO_DIR.glob("*.yaml"))


def minimal(**extra) -> dict:
    return {"name": "t", "duration_s": 10, **extra}


@pytest.mark.parametrize(("t", "expected"), [(-1, 25), (0, 25), (5, 100), (10, 175), (15, 175)])
def test_interpolate_linear_and_clamped(t: float, expected: float) -> None:
    assert interpolate([(0, 25), (10, 175)], t) == pytest.approx(expected)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_bundled_scenarios_produce_valid_messages(path: pathlib.Path) -> None:
    sc = load(path)
    bus, received = MemoryBus(), []
    bus.subscribe("#", received.append)
    count = play(sc, bus, "s_test", speed=0)
    assert count == len(received) > 0
    for msg in received:
        msg.validate()  # interfaces.md 필수 필드
        assert msg.session_id == "s_test"


def test_events_are_time_ordered_and_rates_match() -> None:
    sc = parse(
        minimal(
            sensor={"hz": 2, "temperature_c": [[0, 20], [10, 120]]},
            vision={"fps": 1, "objects": [[0, ["pan"]], [5, ["pan", "person"]]]},
            stt=[[3, "자비스 후드 켜줘"], [4, "그냥 혼잣말"]],
        )
    )
    events = build_events(sc)
    times = [e.t for e in events]
    assert times == sorted(times)
    by_type = {t: [e for e in events if e.type == t] for t in {e.type for e in events}}
    assert len(by_type["sensor/reading"]) == 21  # 0~10초, 2Hz
    assert len(by_type["vision/objects"]) == 11
    assert len(by_type["system/heartbeat"]) == 11
    stt = [e.payload_fn() for e in by_type["stt/text"]]
    assert [s["wake"] for s in stt] == [True, False]
    frame6 = by_type["vision/objects"][6].payload_fn()
    assert [o["cls"] for o in frame6["objects"]] == ["pan", "person"]


def test_play_waits_according_to_speed() -> None:
    sc = parse(minimal(duration_s=4, heartbeat_hz=1))
    now = [0.0]
    waits: list[float] = []

    def sleep(seconds: float) -> None:
        waits.append(round(seconds, 6))
        now[0] += seconds

    play(sc, MemoryBus(), "s", speed=2, clock=lambda: now[0], sleep=sleep)
    assert waits == [0.5, 0.5, 0.5, 0.5]  # 1초 간격을 2배속으로


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"duration_s": 10}, "필수"),
        (minimal(typo_key=1), "알 수 없는 키"),
        (minimal(duration_s=0), "0보다"),
        (minimal(sensor={"temperature_c": "hot"}), "sensor.temperature_c"),
        (minimal(vision={"objects": [[0, "pan"]]}), "vision.objects"),
        (minimal(stt=[["자비스"]]), "stt 항목"),
        (minimal(heaters={"hood": [[0, 1]]}), "가열 장치"),
        (minimal(heaters={"burner_1": [[0, 4]]}), "세기 0~3"),
        (minimal(heaters={"burner_1": [[0, 1]]}, sensor={"temperature_c": [[0, 25]]}), "함께"),
        (minimal(expected=[[0, "COOK"]]), "expected"),
        (minimal(expected=[[5, "IDLE"]]), "0초부터"),
        (minimal(expected=[[0, "IDLE"], [0, "PREHEAT"]]), "늘어나야"),
    ],
)
def test_invalid_scenarios_explain_the_problem(raw: dict, message: str) -> None:
    with pytest.raises(ScenarioError, match=message):
        parse(raw)


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: p.stem)
def test_bundled_scenarios_have_heaters_and_expected_states(path: pathlib.Path) -> None:
    """FUS-05: 시나리오마다 가열 장치 시간표와 정답 State가 있다 (FUS-07 State F1 계산용)."""
    sc = load(path)
    assert sc.heaters is not None and sc.expected
    assert expected_at(sc, 0) == "IDLE"  # 가상 주방은 모두 꺼진 채 시작한다 (§4.4)
    assert all(t <= sc.duration_s for t, _ in sc.expected)


def test_heater_temperature_follows_virtual_kitchen_rule() -> None:
    sc = parse(minimal(duration_s=5, heaters={"burner_1": [[0, 0], [2, 2]]}))
    readings = heater_readings(sc.heaters, sc.duration_s)
    temp = link.TARGET_C[0]
    for t, temps in readings:
        assert temps["burner_1"] == round(temp, 1)
        assert temps["burner_2"] == temps["fryer"] == link.TARGET_C[0]  # 시간표에 없으면 꺼짐
        temp = link.next_temperature(temp, 2 if t >= 2 else 0)
    events = [e for e in build_events(sc) if e.type == "sensor/reading"]
    assert len(events) == 6 * len(link.HEATERS)  # 0~5초, 가열 장치마다 1초에 1번


def test_heater_turns_itself_off_at_hard_limit_until_next_command() -> None:
    sc = parse(minimal(duration_s=200, heaters={"burner_1": [[0, 3], [150, 3]]}))
    temps = [r["burner_1"] for _, r in heater_readings(sc.heaters, sc.duration_s)]
    peak = temps.index(max(temps[:150]))
    assert link.HARD_LIMIT_C <= temps[peak] < link.TARGET_C[3]  # 265°C에서 꺼져 270°C까지 못 간다
    assert temps[peak + 1] < temps[peak]  # 꺼진 뒤 식는다
    assert temps[160] > temps[150]  # 새 세기 명령을 받으면 다시 데워진다


def test_expected_at_returns_current_label() -> None:
    sc = parse(minimal(expected=[[0, "IDLE"], [3, "PREHEAT"]]))
    assert [expected_at(sc, t) for t in (0, 2.9, 3, 9)] == ["IDLE", "IDLE", "PREHEAT", "PREHEAT"]
    assert expected_at(parse(minimal()), 0) is None


def test_device_state_follows_heater_schedule_and_self_shutoff() -> None:
    sc = parse(minimal(duration_s=120, heaters={"burner_1": [[0, 0], [3, 3]], "fryer": [[0, 2]]}))
    states = device_states(sc.heaters, sc.duration_s)
    assert states[0] == (
        0.0,
        {
            "devices": {
                "burner_1": {"on": False, "level": 0},
                "burner_2": {"on": False, "level": 0},
                "fryer": {"on": True, "level": 2},
            },
            "safe_stop": False,
        },
    )
    assert states[1][0] == 3.0 and states[1][1]["devices"]["burner_1"] == {"on": True, "level": 3}
    assert all(
        b - a <= STATE_PERIOD_S for (a, _), (b, _) in zip(states, states[1:], strict=False)
    )  # 5초마다
    # 265°C 자체 차단: 그 다음 시각에 꺼짐 + safe_stop (온도가 265°C를 넘은 첫 값과 같은 시각)
    tripped = next((t, p) for t, p in states if p["safe_stop"])
    temps = dict(heater_readings(sc.heaters, sc.duration_s))
    assert temps[tripped[0]]["burner_1"] >= link.HARD_LIMIT_C
    assert temps[tripped[0] - 1]["burner_1"] < link.HARD_LIMIT_C
    assert tripped[1]["devices"]["burner_1"] == {"on": False, "level": 0}
    assert tripped[1]["devices"]["fryer"] == {"on": True, "level": 2}  # 다른 장치는 그대로
    for _, payload in states:
        Envelope.new("device/state", "simulator", payload, "s")  # 버스 규격에 맞는다
    assert sum(e.type == "device/state" for e in build_events(sc)) == len(states)
