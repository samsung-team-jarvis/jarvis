import json
import pathlib
import re

import pytest

from common import kitchen_link as link
from common.kitchen_link import LinkError

DOC = pathlib.Path(__file__).parents[2] / "docs/architecture/interfaces.md"


def doc_examples() -> list[tuple[str, str]]:
    """interfaces.md §4.2 표의 (토픽, 예시 JSON). 문서와 코드가 어긋나면 깨진다."""
    section = DOC.read_text(encoding="utf-8").split("### 4.2", 1)[1].split("###", 1)[0]
    rows = []
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        match = re.fullmatch(r"`(\{.*\})`", cells[-1]) if len(cells) >= 4 else None
        if match and cells[0].startswith("`kitchen/"):
            rows.append((cells[0].strip("`"), match.group(1)))
    return rows


def test_doc_examples_follow_the_rules() -> None:
    decoders = {
        link.TOPIC_CMD: link.decode_command,
        link.TOPIC_ACK: link.decode_ack,
        link.TOPIC_TEMP: link.decode_temp,
        link.TOPIC_STATE: link.decode_state,
        link.TOPIC_HEARTBEAT: json.loads,
    }
    examples = doc_examples()
    assert {topic for topic, _ in examples} == set(decoders)
    for topic, example in examples:
        decoders[topic](example)


@pytest.mark.parametrize(
    "payload",
    [
        {"seq": 1, "cmd": "ON", "target": "hood", "value": 1},
        {"seq": 0, "cmd": "OFF", "target": "all", "value": 0},
        {"seq": 7, "cmd": "LEVEL", "target": "burner_2", "value": 3},
    ],
)
def test_valid_commands(payload: dict) -> None:
    link.validate_command(payload)
    assert link.decode_command(link.encode(payload)) == payload


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"seq": -1, "cmd": "ON", "target": "hood", "value": 1}, "seq"),
        ({"seq": True, "cmd": "ON", "target": "hood", "value": 1}, "seq"),
        ({"seq": 1, "cmd": "TOGGLE", "target": "hood", "value": 1}, "cmd"),
        ({"seq": 1, "cmd": "ON", "target": "fridge", "value": 1}, "target"),
        ({"seq": 1, "cmd": "ON", "target": "all", "value": 1}, "all"),
        ({"seq": 1, "cmd": "LEVEL", "target": "all", "value": 2}, "all"),
        ({"seq": 1, "cmd": "LEVEL", "target": "hood", "value": 4}, "value"),
        ({"seq": 1, "cmd": "OFF", "target": "hood", "value": 1}, "value"),
        ({"seq": 1, "cmd": "ON", "target": "hood"}, "value"),
    ],
)
def test_invalid_commands(payload: dict, error: str) -> None:
    with pytest.raises(LinkError, match=error):
        link.validate_command(payload)


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        ({"action": "TURN_ON", "target": "hood"}, ("ON", "hood", 1)),
        ({"action": "TURN_OFF", "target": "all"}, ("OFF", "all", 0)),
        ({"action": "SET_LEVEL", "target": "burner_1", "level": 2}, ("LEVEL", "burner_1", 2)),
        ({"action": "EMERGENCY_STOP", "target": "all"}, ("OFF", "all", 0)),
    ],
)
def test_command_for_device_actions(call: dict, expected: tuple) -> None:
    command = link.command_for(call, seq=5)
    assert command is not None and command["seq"] == 5
    assert (command["cmd"], command["target"], command["value"]) == expected


@pytest.mark.parametrize(
    "call",
    [
        {"action": "CHECK_STATUS"},
        {"action": "SET_TIMER", "duration_s": 180, "target": "burner_1"},
        {"action": "ASK_CLARIFY", "for_action": "TURN_ON", "missing": ["target"]},
        {"action": "UNSUPPORTED"},
    ],
)
def test_command_for_returns_none_when_no_device_changes(call: dict) -> None:
    assert link.command_for(call, seq=1) is None


def test_decode_ack() -> None:
    assert link.decode_ack(b'{"seq":3,"ok":true}') == {"seq": 3, "ok": True}
    refused = link.decode_ack('{"seq":3,"ok":false,"reason":"unknown_target"}')
    assert refused["ok"] is False and refused["reason"] == "unknown_target"
    for bad in (b"not json", b"[1]", b'{"seq":"3","ok":true}', b'{"seq":3,"ok":1}'):
        with pytest.raises(LinkError):
            link.decode_ack(bad)


def test_decode_temp() -> None:
    assert (
        link.decode_temp('{"device_id":"burner_1","temperature_c":175.2}')["temperature_c"] == 175.2
    )
    for bad in (
        '{"device_id":"","temperature_c":1}',
        '{"device_id":"b","temperature_c":"hot"}',
        '{"device_id":"b"}',
    ):
        with pytest.raises(LinkError):
            link.decode_temp(bad)


def test_decode_state() -> None:
    state = {
        "devices": {"hood": {"on": True, "level": 2}, "burner_1": {"on": False, "level": 0}},
        "safe_stop": False,
    }
    assert link.decode_state(link.encode(state)) == state
    for bad in (
        {"devices": {}},
        {"devices": {"hood": {"on": 1, "level": 2}}, "safe_stop": False},
        {"safe_stop": True},
    ):
        with pytest.raises(LinkError):
            link.decode_state(link.encode(bad))


def run(level: int, seconds: int, start: float = link.TARGET_C[0]) -> float:
    temp = start
    for _ in range(seconds):
        temp = link.next_temperature(temp, level)
    return temp


def test_temperature_moves_five_percent_of_the_gap_each_second() -> None:
    assert link.next_temperature(25.0, 3) == pytest.approx(25.0 + (270.0 - 25.0) * 0.05)
    assert link.next_temperature(100.0, 0) == pytest.approx(100.0 - 75.0 * 0.05)


def test_temperature_step_does_not_depend_on_tick_size() -> None:
    two_half_steps = link.next_temperature(link.next_temperature(25.0, 2, dt_s=0.5), 2, dt_s=0.5)
    assert two_half_steps == pytest.approx(link.next_temperature(25.0, 2, dt_s=1.0))


def test_temperature_approaches_target_and_cools_when_off() -> None:
    assert run(2, 60) == pytest.approx(link.TARGET_C[2], abs=10)
    assert run(1, 600) == pytest.approx(link.TARGET_C[1], abs=0.01)
    assert run(0, 120, start=260.0) < 40


def test_only_the_highest_level_reaches_the_hard_limit() -> None:
    assert link.TARGET_C[2] < link.HARD_LIMIT_C < link.TARGET_C[3]
    seconds_to_limit = next(s for s in range(1, 600) if run(3, s) >= link.HARD_LIMIT_C)
    assert 60 < seconds_to_limit < 120


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(LinkError):
        link.next_temperature(25.0, 4)
