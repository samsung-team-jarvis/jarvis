import pathlib

import pytest

from common.bus import MemoryBus
from services.simulator.runner import build_events, play
from services.simulator.scenario import ScenarioError, interpolate, load, parse

SCENARIO_DIR = pathlib.Path(__file__).parents[2] / "services/simulator/scenarios"
SCENARIOS = sorted(SCENARIO_DIR.rglob("*.yaml"))  # temp/ 하위 폴더(FUS-05) 포함


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
        (minimal(category="fire"), "category"),
        (minimal(expect=[[0, "BURNING"]]), "expect 항목"),
        (minimal(expect=[[5, "IDLE"]]), "0초부터"),
        (minimal(expect=[[0, "IDLE"], [9, "COOKING"], [3, "IDLE"]]), "시각 순"),
    ],
)
def test_invalid_scenarios_explain_the_problem(raw: dict, message: str) -> None:
    with pytest.raises(ScenarioError, match=message):
        parse(raw)


def test_expect_gives_state_at_time() -> None:
    sc = parse(
        minimal(category="overheat", expect=[[0, "PREHEAT"], [8, "COOKING"], [41, "DANGER"]])
    )
    assert [sc.state_at(t) for t in (0, 7.9, 8, 40, 41, 99)] == [
        "PREHEAT", "PREHEAT", "COOKING", "COOKING", "DANGER", "DANGER",
    ]  # fmt: skip
    assert parse(minimal()).state_at(3) is None
